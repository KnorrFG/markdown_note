import os
import re
import subprocess as sp
import sys
import shutil
from functools import reduce
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Dict, Set, Tuple, NamedTuple, Union
from datetime import datetime
import time
from typing import List

import click
from fuzzywuzzy import process
import markdown
import toolz as t
import yaml
from attrdict import AttrDict
from tqdm import tqdm
from yattag import Doc
from tabulate import tabulate

from . import resources as res
from .tag_string_parser import create_predicate_from_tag_str

Index = Dict[str, Set[int]]
PathFunc =  Callable[[], Path]


config_path = Path.home() / '.mdnrc'
default_state = {
    'next_index': 0,
    'last_edited': None,
    'last_created': None,
    'last_shown': None
}

new_md_template = '''---
title: None
group: None
---
'''

special_id_mappings = {
    '_c': 'last_created',
    '_e': 'last_edited',
    '_s': 'last_shown'
}

tag_pattern = re.compile(r'\B(@\w+)')


def error(msg: str):
    print(strip_lines(msg), file=sys.stderr)
    exit(1)


def strip_lines(s:str)->str:
    return '\n'.join(
        line.strip() for line in s.splitlines()
        if len(line) > 0)


def try_cast(target_type: type, val: Any) -> Any:
    try:
        return target_type(val)
    except ValueError:
        return None


def unlink_if_existing(pf: PathFunc):
    p = pf()
    if p.exists():
        p.unlink()


def find_id_in_single_index(ind: Index, id: int) -> str:
    return t.first(key for key, value in ind.items() 
                   if id in value)


def find_id_in_multi_index(ind: Index, id: int) -> Set[str]:
    return {key for key, val in ind.items() if id in val}
                    

@click.group()
def cli():
    '''Markdown note is a tool to write notes in markdown, which can then be
    viewed in a browser as html.
    
    All Notes are stored as plaintext files in the directory that you provide
    as save-path in the configuration file ~/.mdnrc which will be automatically
    created by your specification uppon first usage.
    
    All Notes must have a yaml front matter with a title and a group.
    Think of a group as a notebook. Notes are identified by IDs therefore
    titles can duplicate. Whenever a command requires an ID as argument you can
    either use the id (which u can acquire via `mdn ls`, a title, which will be
    used within a fuzzy search or one of '_c', '_e', '_s' which are synonyms
    for the file that was last created, last edited or last shown respectively.
    
    All words that start with a @ within a note are considered tags and `mdn
    ls` accepts a filter string allows to filter notes by a logical formula
    describing whether tags should be existing or not, e.g.: "@foo & -@bar" 
    which means the note must have the tag @foo but must not have the tag @bar.

    Information about tags titles and groups are stored in index files. In case
    the index diverges from the correct state (e.g. because the files were
    modified outside of mdn) you can use `mdn regenerate` to recreate the index
    files.
    '''


@cli.command()
def regenerate():
    '''recreates all index files.
    This will parse all notes, and might take some time.'''
    print('Regenerate index, this may take some time...')
    for pf in [title_idx_path, tag_idx_path, group_idx_path]:
        unlink_if_existing(pf)
    tag_idx = {}
    title_idx = {}
    group_idx = {}
    empty_set = set()
    files = list(Path(load_config().save_path, 'md').iterdir())

    for file in tqdm(files):
        title, tags, group = parse_file(file.read_text()) 
        id = int(file.stem)
        title_idx = insert_index_entry(title_idx, title, id)
        tag_idx = update_multi_index(tag_idx, tags, empty_set, id)
        group_idx = insert_index_entry(group_idx, group, id)
    store_group_index(group_idx)
    store_title_index(title_idx)
    store_tag_index(tag_idx)

    t.thread_first(load_state(),
        (t.assoc, 'next_index', 
                  max(map(int, [f.stem for f in files])) + 1),
        save_state)

@cli.command()
def new():
    '''creates a new note'''
    save_path = Path(load_config().save_path)
    state = load_state()
    md_folder = save_path / 'md' 
    md_folder.mkdir(755, True, True)
    new_file_path =  md_folder / f'{state.next_index}.md'
    assert_new_file_does_not_exist(new_file_path)
    new_file_path.write_text(new_md_template)
    t.thread_first(state,
        (t.assoc, 'next_index', state.next_index + 1),
        (t.assoc, 'last_created', state.next_index),
        save_state)
    store_group_index(insert_index_entry(load_group_index(), 
                      'None', state.next_index))
    store_title_index(insert_index_entry(load_title_index(), 
                      'None', state.next_index))
    sp.run('mdn edit', shell=True)


@cli.command()
@click.argument('id', default='_c')
def edit(id: str):
    '''edit a note'''
    state = load_state()
    config = load_config()
    path, int_id = parse_id(id, Path(load_config().save_path), state, 
                            load_title_index())
    html_path = get_html_path(int_id)
    html_path.parent.mkdir(755, True, True)

    def render_html(content):
        html_path.write_text(make_html(content))

    assert_path_exists(path)
    edit_externally(path, config, render_html)
    save_state(t.assoc(state, 'last_edited', int_id))
    content = path.read_text()
    title, tags, group = parse_file(content)
    update_index_files_as_necessary(title, tags, group, int_id)
    render_html(content) 


def show_one(id: str):
    '''Display the html version of a note'''
    state = load_state()
    config = load_config()
    path, int_id = parse_id(id, Path(load_config().save_path), state, 
                            load_title_index())
    
    html_path = get_html_path(int_id)
    if html_path.stat().st_mtime < path.stat().st_mtime:
        html_path.write_text(make_html(path.read_text()))
    try:
        sp.Popen(config.browser_cmd.format(html_path), shell=True)
        save_state(t.assoc(state, 'last_shown', int_id))
    except sp.CalledProcessError as err:
        error(f' There was a problem with the browser command: {err}')

@cli.command()
@click.argument('ids', nargs=-1)
def show(ids: List[str]):
    '''Display the html version of one or more notes note'''
    if len(ids) == 0:
        show_one('_e')
    else:
        for id in ids:
            show_one(id)


@cli.command()
@click.argument('pattern', default='')
@click.option('--group', '-g', default=None)
@click.option('--tags', '-t', default=None)
def ls (pattern: str, group: str, tags: str):
    '''Show a list of all existing notes.
    Tags can be filtered according to logical formulas.
    - is not, & is and and | is or. Nested paranthesis are supported.
    Eg "@foo & -@bar" will show all notes that contain the @foo tag, but not
    the @bar tag.
    
    If pattern is provided the list will be filtered by whether the pattern is
    contained in the title. Casing is ignored'''
    rows = filter_files(pattern, group, tags)
    print(tabulate(list(sorted(rows, key=lambda x: x.ts, reverse=True)),  # type: ignore
                   'id title group last_edit'.split()))


@cli.command()
@click.argument('pattern', default='')
@click.option('--group', '-g', default=None)
@click.option('--tags', '-t', default=None)
def rm (pattern: str, group: str, tags: str):
    '''Deletes selected files. Takes the same arguments as ls except for when
    the pattern argument is numeric. Then its treated as an id.'''
    group_index = load_group_index()
    title_index = load_title_index()
    tags_index = load_tag_index()
    config = load_config()
    if pattern.isnumeric():
        ids = [pattern]
    else:
        rows = filter_files(pattern, group, tags, group_index, title_index,
                        tags_index)
        ids = [r.id for r in rows]

    if len(ids) > 1 and not get_user_delete_confirmation(rows):
        return

    for id in ids:
        ftitle, ftags, fgroup = parse_file(md_path(id, config).read_text())
        delete_md(id, config)
        html_path(id, config).unlink()
        store_group_index(remove_index_entry(group_index, fgroup, id))
        store_title_index(remove_index_entry(title_index, ftitle, id))
        for tag in ftags:
            tags_index = remove_index_entry(tags_index, tag, id)
        store_tag_index(tags_index)


@cli.command()
@click.argument('target')
@click.argument('save-path')
def aa(target, save_path):
    '''Add Asset
    Coppies target to asset-folder/save-path'''
    abs_save_path = Path(load_config().save_path, 'assets', save_path)
    abs_save_path.parent.mkdir(755, True, True)
    shutil.copyfile(target, abs_save_path)
   

def make_html(md: str) -> str:
    lines = md.splitlines()
    content_start_line = lines[1:].index('---') + 2
    title = yaml.safe_load('\n'.join(lines[1:content_start_line - 1]))\
                .get('title')
    md_code = markdown.markdown('\n'.join(lines[content_start_line:]), 
                                extensions=['extra'])
    doc, tag, text, line = Doc().ttl()
    doc.asis('<!DOCTYPE html>')
    with tag('html'):
        with tag('head'):
            line('title', title or 'No Title')
            doc.asis('<meta charset="utf-8">')
            doc.asis('<base href="../assets/">')
            line('style', resources.read_text(res, 'default.css'))
        with tag('body'):
            doc.asis(md_code)
    return doc.getvalue()


class Row(NamedTuple):
    id: str
    title: str
    group: str
    ts: datetime


def filter_files(pattern:str, group: str, tags: str, 
                 group_index: Index = None,
                 title_index: Index = None,
                 tags_index: Index = None) -> List[Row]:
    files = list(Path(load_config().save_path, 'md').iterdir())
    title_index = title_index or load_title_index()
    title_lookup = {str(id): title 
                    for title, ids in title_index.items() for id in ids}
    group_index = group_index or load_group_index()
    group_lookup = {str(id): group 
                    for group, ids in group_index.items() for id in ids}
    tags_index = tags_index or load_tag_index()
    tags_lookup = {id: find_id_in_multi_index(tags_index, int(id)) 
                   for id in (file.stem for file in files)}
    rows = [Row(file.stem, title_lookup[file.stem], group_lookup[file.stem],
             datetime.fromtimestamp(file.stat().st_mtime))
            for file in files]
    if group:
        rows = [row for row in rows if group.lower() in row[2].lower()]
    if tags:
        predicate = create_predicate_from_tag_str(tags.lower())
        rows = [row for row in rows if predicate(tags_lookup[row[0]])]
    if pattern:
        rows = [row for row in rows if pattern.lower() in row[1].lower()]
    return rows


def get_user_delete_confirmation(rows):
    print("Do you really wanna delete the following files?\n")
    print(tabulate(list(sorted(rows, key=lambda x: x[3], reverse=True)),
                   'id title group last_edit'.split()))
    print()
    return query_value("Delete? y/n: ", None, t.identity, 
                       lambda x: x in "yn", "") == 'y'


def md_path(id, config):
    return Path(config.save_path, 'md', id + '.md')


def html_path(id, config):
    return Path(config.save_path, 'html', id + '.html')


def delete_md(id: str, config: AttrDict):
    file = md_path(id, config)
    if not file.exists():
        error("""The File thats supposed to be deleted does not seem to exist.
                 Please run 'mdn regenerate' and try again""")
    file.unlink()


def update_index_files_as_necessary(title: str, tags: Set[str], 
                                    group: str, id: int):
    group_index = load_group_index()
    title_index = load_title_index()
    tag_index = load_tag_index()
    old_title = find_id_in_single_index(title_index, id)
    old_group = find_id_in_single_index(group_index, id)
    old_tags = find_id_in_multi_index(tag_index, id)

    if title != old_title:
        store_title_index(update_single_index(title_index, title,
                                              old_title, id))
    if tags != old_tags:
        store_tag_index(update_multi_index(tag_index, tags, 
                                           old_tags, id))
    if group != old_group:
        store_group_index(update_single_index(group_index, group, 
                                              old_group, id))


def edit_externally(path: Path, config: AttrDict, render_html:
                Callable[[str], None]) -> None:
    last_edited = path.stat().st_mtime
    try:
        edit_proc = sp.Popen(config.editor_cmd.format(path), shell=True)
    except sp.CalledProcessError as err:
        error(f' There was a problem with the editor command: {err}')
        assert False # mypy
    
    while edit_proc.poll() is None:
        time.sleep(1)
        new_last_edited = path.stat().st_mtime > last_edited
        if new_last_edited:
            render_html(path.read_text())
            last_edited = new_last_edited


def remove_index_entry(index: Index , entry: str, id: Union[int, str]) -> Index:
    try:
        if len(index[entry]) == 1:
            return t.dissoc(index, entry)
        else:
            return t.update_in(index, [entry], lambda x: x - {id})
    except KeyError:
        error('''
            It seems the Index is corrupt. Please run 
            `mdn regenerate` and try again''')
        assert False # just for mypy <3 


def insert_index_entry(index: Index, entry: str, id: int) -> int:
    if entry in index:
        return t.update_in(index, [entry], lambda x: x | {id})
    else:
        return t.assoc(index, entry, {id})


def update_single_index(index: Index, new: str, old: str, id: int) -> Index:
    return t.thread_first(index, 
        (remove_index_entry, old, id), 
        (insert_index_entry, new, id))


def update_multi_index(index: Index, new: Set[str], old: Set[str], id: int)\
        -> Index:
    '''Multi index means that the same id can be member of multiple entries'''
    added_tags = new - old
    removed_tags = old - new
    index_with_new_tags = reduce(t.partial(insert_index_entry, id=id), 
                                 added_tags, index)
    return reduce(t.partial(remove_index_entry, id=id), 
                  removed_tags, index_with_new_tags)


def parse_file(content: str) -> Tuple[str, Set[str], str]:
    lines = content.splitlines()
    if not lines[0] == '---' and lines[1:].count('---') == 1:
        error('''
            The md file must contain exactly 2 lines consisting of
            ---
            The first of which must be the first line.
            Please correct the file by calling `mdn edit _e`''')
    front_matter = AttrDict(yaml.safe_load('\n'.join(
        lines[1:lines[1:].index('---') + 1])))
    assert_front_matter_correct(front_matter)
    tags = t.thread_last(tag_pattern.findall(content),
                       (map, str.lower),
                       (set))
    return front_matter.title, tags, front_matter.group


def assert_front_matter_correct(front_matter: str):
    if not (hasattr(front_matter, 'title')
            and hasattr(front_matter, 'group')):
        error('''The front_matter must contain a title field
              and a group field''')


def assert_path_exists(p: Path):
    if not p.exists():
        error(f'''
            The file corresponding to the id could not be found.
            Please run `mdn regenerate` and try again
            {p}''')
        exit(1)


def parse_id(id: str, save_path: Path, state: AttrDict, 
             title_index: Index) -> Tuple[Path, int]:
    maybe_int = try_cast(int, id)
    if maybe_int is not None:
        int_id = maybe_int 
    elif id in special_id_mappings:
        int_id = state[special_id_mappings[id]]
    else:
        match = process.extractOne(id, title_index.keys())[0]
        int_id = t.first(title_index[match])
    return save_path / 'md' / f'{int_id}.md', int_id


def assert_new_file_does_not_exist(p: Path):
    if p.exists():
        print(strip_lines('''
            The file that is supposed to be created does already exist.
            Please run `mdn regenerate` and try again'''),
            file=sys.stderr)
        exit(1)


def load_config() -> AttrDict:
    if config_path.exists():
        return AttrDict(yaml.safe_load(config_path.read_text()))
    config = query_config()
    config_path.parent.mkdir(755, True, True)
    config_path.write_text(yaml.dump(t.valmap(str, config)))
    return config


def query_config() -> AttrDict:
    save_path = query_value(
        'Where should your notes be stored?',
        '~/.mdn.d',
        lambda x: Path(x).expanduser(),
        lambda x: True,
        'Input must be a Path to a non existing directory')
    editor_cmd = query_value(
        strip_lines('''
            Enter the editor command that should be used to edit the markdown 
            files. The command must contain a '{}' which will be replaced by 
            the filepath'''),
        'code -nw {}' if os.name == 'nt' else 'vim {}',
        t.identity,
        lambda x: '{}' in x,
        'The command does not seem to contain a pair of braces'
    )
    browser_cmd = query_value(
        strip_lines('''
        Enter the browser command that should be used to display the html files.
        The command must contain a '{}' which will be replaced by the filepath.
        The command will be executed through the shell'''),
        '{}' if os.name == 'nt' else 'firefox {}' ,
        t.identity,
        lambda x: '{}' in x,
        'The command does not seem to contain a pair of braces'
    )
    return AttrDict(save_path=save_path, editor_cmd=editor_cmd, 
                    browser_cmd=browser_cmd)


def query_value(msg: str, default: str, transform: Callable, 
                check: Callable[[Any], bool], error_msg: str) -> Any:
    while True:
        try:
            inp = transform(input((msg + f' [{default}]: ') 
                                  if default is not None else msg) 
                            or default)
            if check(inp):
                return inp
            print(error_msg, file=sys.stderr)
        except Exception as e:
            print(e, file=sys.stderr)


def make_path_func(file_name: str) -> PathFunc:
    return lambda: Path(load_config().save_path, file_name + '.yaml')


def load(pf: PathFunc, default: Callable[[], Any] = AttrDict)\
        -> AttrDict:
    idx_path = pf()
    if idx_path.exists():
        return AttrDict(yaml.safe_load(idx_path.read_text()))
    else:
        return default()


@t.curry
def store(pf: PathFunc, index: Index) -> None:
    pf().write_text(yaml.dump(dict(index)))


def get_html_path(id: int) -> Path:
    return Path(load_config().save_path, 'html', f'{id}.html')


title_idx_path = make_path_func('title_index')
tag_idx_path = make_path_func('tag_index')
group_idx_path = make_path_func('group_index')
state_path = make_path_func('state')
load_title_index = t.partial(load, title_idx_path)
load_tag_index = t.partial(load, tag_idx_path)
load_group_index = t.partial(load, group_idx_path)
store_title_index = store(title_idx_path)
store_tag_index = store(tag_idx_path)
store_group_index = store(group_idx_path)
save_state = store(state_path)
load_state = t.partial(load, state_path, 
                       lambda: AttrDict(default_state))
