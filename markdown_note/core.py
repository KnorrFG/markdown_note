import os
import pickle
import re
import subprocess as sp
import sys
import time
from datetime import datetime
from functools import lru_cache, reduce
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Set, Tuple, Union

import bibtexparser
import markdown
import toolz as t
import yaml
from habanero import cn
from tabulate import tabulate
from yattag import Doc

from . import resources as res
from .tag_string_parser import ParserError, create_predicate_from_tag_str
from .attrdict import AttrDict

PathFunc =  Callable[[], Path]
Index = Dict[str, Set[int]]

config_path = Path.home() / '.mdnrc'
tag_pattern = re.compile(r'\B(@\w+)')
link_pattern = re.compile(r"!?\[.*\]\((.*)\)")
md_file_pattern = re.compile(r"\d+\.md")


special_id_mappings = {
    '_c': 'last_created',
    '_e': 'last_edited',
    '_s': 'last_shown'
}

                    
default_state = {
    'next_index': 0,
    'last_edited': None,
    'last_created': None,
    'last_shown': None
}


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
    try:
        return t.first(key for key, value in ind.items() 
                       if id in value)
    except StopIteration:
        return None


def find_id_in_multi_index(ind: Index, id: int) -> Set[str]:
    return {key for key, val in ind.items() if id in val}


def get_title_author_and_link(bibtex: str):
    info = bibtexparser.loads(bibtex).entries[0]
    title = info["title"]
    author_short = short_description(info["author"])
    year = info["year"]
    link = info["url"]
    return title, f"{author_short} {year}", link


def short_description(authors):
    """gets a short description from a list of authors"""
    authors_list = authors.split(" and ")
    def get_last_name(name): return name.split()[-1]

    l = len(authors_list)
    if l == 0:
        error("Cant parse authors string:\n" + authors)
    elif l == 1:
        return get_last_name(authors_list[0])
    elif l == 2:
        a = get_last_name(authors_list[0])
        b = get_last_name(authors_list[1])
        return f"{a} & {b}"
    else:
        return f"{get_last_name(authors_list[0])} et al."



def load_bibtex_cached(doi, reload_cache=False):
    cache = load_doi_cache()
    if reload_cache or doi not in cache:
        try:
            entry = cn.content_negotiation(ids=doi)
        except Exception as e:
            error("There was a problem contacting crossref:\n", str(e))

        cache[doi] = entry
        store_doi_cache(cache)
    return cache[doi]


def add_to_bib(entry, bib):
    key = get_cite_key(entry)
    if key in bib:
        orig_key = key
        num = 2
        key = key + "_2"
        while key in bib:
            num += 1
            key = orig_key + "_" + str(num)
        entry = entry.replace(orig_key, key)

    return bib + "\n\n" + entry


def get_cite_key(entry):
    start = entry.find("{")
    end = entry.find(",")
    return entry[start + 1: end]


def get_bib_path(path):
    if path is not None:
        return Path(path)

    files = list(Path().glob("*.bib"))
    if len(files) > 0:
        return files[0]
    else:
        return None



def multipattern_to_ids(pattern, group, tags, config=None, state=None,
        group_index=None, title_index=None, tags_index=None):
    if len(pattern) == 0:
        pattern = [""]
    if len(pattern) == 1:
        if pattern[0].isnumeric():
            ids = pattern
        else:
            rows = filter_files(pattern[0], group, tags, group_index,
                    title_index, tags_index)
            ids = [row.id for row in rows]
    else:
        ids = []
        config = config or load_config()
        state = state or load_state()
        title_index = title_index or load_title_index()
        for pat in pattern:
            path, int_id = parse_id(pat, Path(config.save_path), 
                                    state, title_index)
            ids.append(int_id)

    return ids


def get_hits(pattern: re.Pattern, body: str, context_len: int = 15):
    """Applies search, and returns a string for every match with some
    additional context"""
    matches = pattern.finditer(body)
    res = []
    for match in matches:
        if match is None:
            continue
        start = max(0, match.start() - context_len)
        end = min(len(body), match.end() + context_len)
        hit = body[start: end].replace("\n", " ")
        first_space = hit.find(" ")
        if first_space > context_len:
            first_space = -1
        last_space = hit.rfind(" ")
        if last_space <= len(hit) - context_len:
            last_space = len(hit)
        last_space = min(70, last_space)
        hit = hit[first_space + 1: last_space]
        res.append(f"... {hit} ...")
    return res


def cat_one(id: str, no_header: bool):
    """Prints the notes source to stdout. Use -n to hide the yaml header"""
    state = load_state()
    # config = load_config()
    path, int_id = parse_id(id, Path(load_config().save_path), state, 
                            load_title_index())
    content = path.read_text().splitlines()
    h_end = 1 + content[1:].index('---')
    content = ("\n".join(content[h_end + 1:] if no_header else
        content).strip())
    print()
    print(adjust_links(content))


def id_to_row(id, config, group_index, title_index):
    file = Path(config.save_path) / "md" / f"{id}.md"
    title_lookup = {id: title 
                    for title, ids in title_index.items() for id in ids}
    group_lookup = {id: group 
                    for group, ids in group_index.items() for id in ids}
    return Row(file.stem, title_lookup[id], group_lookup[id],
            datetime.fromtimestamp(file.stat().st_mtime)
            .replace(microsecond=0))


def adjust_links(s: str):
    matches = list(link_pattern.finditer(s))
    if len(matches) == 0:
        return s

    abs_save_paths = [Path(load_config().save_path, 'assets', m.group(1)) 
                      for m in matches]

    first_segment = s[:matches[0].start(1)]
    segments = [s[m1.end(1):m2.start(1)] 
            for m1, m2 in t.sliding_window(2, matches)]
    last_segment = s[matches[-1].end(1):]
    return "".join(t.interleave([[first_segment] + segments, 
                                  map(str, abs_save_paths)])) + last_segment
        
    


def make_html(md: str) -> str:
    lines = md.splitlines()
    content_start_line = lines[1:].index('---') + 2
    title = yaml.safe_load('\n'.join(lines[1:content_start_line - 1]))\
                .get('title')
    md_code = markdown.markdown('\n'.join(lines[content_start_line:]), 
                                extensions=['extra', 'toc'])
    doc, tag, text, line = Doc().ttl()
    doc.asis('<!DOCTYPE html>')
    with tag('html'):
        with tag('head'):
            line('title', title or 'No Title')
            doc.asis('<meta charset="utf-8">')
            doc.asis('<base href="../assets/">')
            line('style', resources.read_text(res, 'content.css'))
        with tag('body', klass="body"):
            doc.asis(md_code)
    return doc.getvalue()


class Row(NamedTuple):
    id: str
    title: str
    group: str
    ts: datetime


def assert_all_files_valid(files: List[Path]):
    for f in files:
        if md_file_pattern.match(f.name) is None:
            error(f"Found an invalid file in the md folder: {f.name}")


def filter_files(pattern:str, group: str, tags: str, 
                 group_index: Index = None,
                 title_index: Index = None,
                 tags_index: Index = None) -> List[Row]:
    files = list(Path(load_config().save_path, 'md').iterdir())
    assert_all_files_valid(files)
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
             datetime.fromtimestamp(file.stat().st_mtime)
                     .replace(microsecond=0))
            for file in files]
    if group:
        rows = [row for row in rows if group.lower() in row[2].lower()]
    if tags:
        try:
            predicate = create_predicate_from_tag_str(tags.lower())
        except ParserError as e:
            error(f"Couldnt parse the tag string. Problematic bit: {e.reason}"
                    "\nMaybe you missed an @?")
        rows = [row for row in rows if predicate(tags_lookup[row[0]])]
    if pattern:
        pattern = re.compile(".*".join(pattern), re.I)
        rows = [row for row in rows if pattern.search(row[1])]
    return rows


def print_table(rows):
    print(tabulate(list(sorted(rows, key=lambda x: x[3], reverse=True)),
                   'id title group last_edit'.split()))


def get_user_delete_confirmation(rows):
    print("Do you really wanna delete the following files?\n")
    print_table(rows)
    print()
    return query_value("Delete? y/n: ", None, t.identity, 
                       lambda x: x in "yn", "") == 'y'


def md_path(id, config):
    return Path(config.save_path, 'md', f'{id}.md')


def html_path(id, config):
    return Path(config.save_path, 'html', f'{id}.html')


def delete_md(id: str, config: AttrDict):
    file = md_path(id, config)
    if not file.exists():
        error("""The File thats supposed to be deleted does not seem to exist.
                 Please run 'mdn regenerate' and try again""")
    file.unlink()


def update_index_files_as_necessary(title: str, tags: Set[str], 
        group: str, doi: str, id: int):
    group_index = load_group_index()
    title_index = load_title_index()
    tag_index = load_tag_index()
    doi_index = load_doi_index()
    old_title = find_id_in_single_index(title_index, id)
    old_group = find_id_in_single_index(group_index, id)
    old_doi = find_id_in_single_index(doi_index, id)
    old_tags = find_id_in_multi_index(tag_index, id)

    if title != old_title:
        store_title_index(update_single_index(title_index, title,
                                              old_title, id))
    if tags != old_tags:
        store_tag_index(update_multi_index(tag_index, tags, 
                                           old_tags, id))
    if doi != old_doi:
        store_doi_index(update_single_index(doi_index, doi, 
                                            old_doi, id))
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
        new_last_edited = path.stat().st_mtime 
        if new_last_edited > last_edited:
            render_html(path.read_text())
            last_edited = new_last_edited


def remove_index_entry(index: Index , entry: str, id: Union[int, str]) -> Index:
    if entry is None:
        return index
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
    return front_matter.title, tags, front_matter.group,\
            front_matter.get("doi", None)


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
    config = load_config()
    maybe_int = try_cast(int, id)
    if maybe_int is not None:
        int_id = maybe_int 
    elif id in special_id_mappings:
        int_id = state[special_id_mappings[id]]
    else:
        pattern = re.compile(".*".join(id), re.I)
        candidates = list(t.concat([ids for name, ids in title_index.items() 
                                    if pattern.search(name)]))
        if len(candidates) == 0:
            print("No matching notes found", file=sys.stderr)
            exit(1)
        mod_date_pairs = [(md_path(id, config).stat().st_mtime, id) 
                          for id in candidates]
        int_id = max(mod_date_pairs)[1]
    return save_path / 'md' / f'{int_id}.md', int_id


def assert_new_file_does_not_exist(p: Path):
    if p.exists():
        print(strip_lines('''
            The file that is supposed to be created does already exist.
            Please run `mdn regenerate` and try again'''),
            file=sys.stderr)
        exit(1)


@lru_cache(1)
def load_config() -> AttrDict:
    if config_path.exists():
        return AttrDict(yaml.safe_load(config_path.read_text()))
    config = query_config()
    config_path.parent.mkdir(0o755, True, True)
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


def make_path_func(file_name: str, ending: str = ".yaml") -> PathFunc:
    return lambda: Path(load_config().save_path, file_name + ending)


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


def load_doi_cache():
    p = doi_cache_path()
    if not p.exists():
        return {}

    with p.open('rb') as f:
        return pickle.load(f)


def store_doi_cache(cache):
    with doi_cache_path().open('wb') as f:
        return pickle.dump(cache, f)


title_idx_path = make_path_func('title_index')
tag_idx_path = make_path_func('tag_index')
group_idx_path = make_path_func('group_index')
doi_idx_path = make_path_func('doi_index')
doi_cache_path = make_path_func('doi_cache', '.pkl')
state_path = make_path_func('state')
load_title_index = t.partial(load, title_idx_path)
load_tag_index = t.partial(load, tag_idx_path)
load_group_index = t.partial(load, group_idx_path)
load_doi_index = t.partial(load, doi_idx_path)
store_title_index = store(title_idx_path)
store_tag_index = store(tag_idx_path)
store_group_index = store(group_idx_path)
store_doi_index = store(doi_idx_path)
save_state = store(state_path)
load_state = t.partial(load, state_path, 
                       lambda: AttrDict(default_state))
