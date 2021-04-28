import re
import shutil
import subprocess as sp
from pathlib import Path
from typing import List

import click
import toolz as t
from tqdm import tqdm

from . import core as c

lmap = t.compose(list, t.map)

new_md_template = '''---
title: None
group: None
---
'''

doi_template = '''---
title: {}
doi: {}
group: None
---
# {}
<{}>
'''


@click.group()
@click.option("--config-file-path", "-c", type=Path, default=None)
def cli(config_file_path: Path):
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
    if config_file_path is not None:
        global config_path
        config_path = config_file_path
    

@cli.command()
def regenerate():
    '''recreates all index files.
    This will parse all notes, and might take some time.'''
    print('Regenerate index, this may take some time...')
    for pf in [c.title_idx_path, c.tag_idx_path, c.group_idx_path]:
        c.unlink_if_existing(pf)
    tag_idx = {}
    title_idx = {}
    group_idx = {}
    doi_idx = {}
    empty_set = set()
    files = list(Path(c.load_config().save_path, 'md').iterdir())

    for file in tqdm(files):
        title, tags, group, doi = c.parse_file(file.read_text()) 
        id = int(file.stem)
        title_idx = c.insert_index_entry(title_idx, title, id)
        tag_idx = c.update_multi_index(tag_idx, tags, empty_set, id)
        group_idx = c.insert_index_entry(group_idx, group, id)
        if doi is not None:
            doi_idx = c.insert_index_entry(doi_idx, doi, id)
    c.store_group_index(group_idx)
    c.store_title_index(title_idx)
    c.store_tag_index(tag_idx)
    c.store_doi_index(doi_idx)

    t.thread_first(c.load_state(),
        (t.assoc, 'next_index', 
                  max(map(int, [f.stem for f in files])) + 1),
        c.save_state)

@cli.command()
@click.option('--template', '-t', default=None, type=Path)
@click.option('--doi', '-d', default=None)
@click.option('--reload', '-r', is_flag=True, 
              help="specify to reload the doi cache")
def new(template: Path, doi: str, reload: bool):
    '''creates a new note'''
    save_path = Path(c.load_config().save_path)
    state = c.load_state()
    md_folder = save_path / 'md' 
    md_folder.mkdir(755, True, True)
    new_file_path =  md_folder / f'{state.next_index}.md'
    c.assert_new_file_does_not_exist(new_file_path)
    if doi is not None:
        bibtex = c.load_bibtex_cached(doi, reload)
        title, author, link = c.get_title_author_and_link(bibtex)
        template = doi_template.format(author, doi, title, link)
    elif template is not None:
        template = template.read_text()
    else:
        template = new_md_template
    new_file_path.write_text(template)
    t.thread_first(state,
        (t.assoc, 'next_index', state.next_index + 1),
        (t.assoc, 'last_created', state.next_index),
        c.save_state)
    c.store_group_index(c.insert_index_entry(c.load_group_index(), 
                      'None', state.next_index))
    c.store_title_index(c.insert_index_entry(c.load_title_index(), 
                      'None', state.next_index))
    sp.run(f'mdn -c {config_path} edit', shell=True)


@cli.command()
@click.argument('id', default='_c')
def edit(id: str):
    '''edit a note'''
    state = c.load_state()
    config = c.load_config()
    path, int_id = c.parse_id(id, Path(c.load_config().save_path), state, 
                            c.load_title_index())
    htmlpath = c.html_path(int_id, config)
    htmlpath.parent.mkdir(755, True, True)

    def render_html(content):
        htmlpath.write_text(c.make_html(content))

    c.assert_path_exists(path)
    c.edit_externally(path, config, render_html)
    c.save_state(t.assoc(state, 'last_edited', int_id))
    content = path.read_text()
    title, tags, group, doi = c.parse_file(content)
    c.update_index_files_as_necessary(title, tags, group, doi, int_id)
    render_html(content) 


def show_one(id: str):
    '''Display the html version of a note'''
    state = c.load_state()
    config = c.load_config()
    path, int_id = c.parse_id(id, Path(c.load_config().save_path), state, 
                            c.load_title_index())
    
    htmlpath = c.html_path(int_id, config)
    if not htmlpath.exists() or htmlpath.stat().st_mtime < path.stat().st_mtime:
        htmlpath.write_text(c.make_html(path.read_text()))
    try:
        sp.Popen(config.browser_cmd.format(htmlpath), shell=True)
        c.save_state(t.assoc(state, 'last_shown', int_id))
    except sp.CalledProcessError as err:
        c.error(f' There was a problem with the browser command: {err}')

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
    rows = c.filter_files(pattern, group, tags)
    c.print_table(rows)


@cli.command()
def lsg():
    '''Shows a list of all existing groups'''
    print("\t".join([f"'{x}'" if " " in x else x
            for x in t.unique(c.load_group_index())]))


@cli.command()
def lst():
    '''Shows a list of all existing tags'''
    print("\t".join([f"'{x}'" if " " in x else x
            for x in t.unique(c.load_tag_index())]))


@cli.command()
@click.argument('pattern', nargs=-1)
@click.option('--group', '-g', default=None)
@click.option('--tags', '-t', default=None)
def rm(pattern: List[str], group: str, tags: str):
    '''Deletes selected files. Takes the same arguments as ls except for when
    the pattern argument is numeric. Then its treated as an id.'''
    group_index = c.load_group_index()
    title_index = c.load_title_index()
    tags_index = c.load_tag_index()
    doi_index = c.load_doi_index()
    config = c.load_config()

    ids = c.multipattern_to_ids(pattern, group, tags, config, None, 
            group_index, title_index, tags_index)
    rows = [c.id_to_row(int(id), config, group_index, title_index)
            for id in ids]

    if len(ids) > 1 and not c.get_user_delete_confirmation(rows):
        return

    for id in ids:
        ftitle, ftags, fgroup, doi = c.parse_file(
                c.md_path(id, config).read_text())
        c.delete_md(id, config)
        htmlp = c.html_path(id, config)
        if htmlp.exists():
            htmlp.unlink()
        c.store_group_index(c.remove_index_entry(group_index, fgroup, id))
        c.store_title_index(c.remove_index_entry(title_index, ftitle, id))
        if doi is not None:
            c.store_doi_index(c.remove_index_entry(doi_index, doi, id))
        for tag in ftags:
            tags_index = c.remove_index_entry(tags_index, tag, id)
        c.store_tag_index(tags_index)


@cli.command()
@click.argument('target')
@click.argument('save-path')
def aa(target, save_path):
    '''Add Asset
    Coppies target to asset-folder/save-path'''
    abs_save_path = Path(c.load_config().save_path, 'assets', save_path)
    abs_save_path.parent.mkdir(755, True, True)
    shutil.copyfile(target, abs_save_path)
   

@cli.command()
@click.argument('pattern', nargs=-1)
@click.option('--group', '-g', default=None)
@click.option('--tags', '-t', default=None)
@click.option('--no-header', '-n', is_flag=True)
def cat(pattern: str, group: str, tags: str, no_header: bool):
    '''Display the md version of one or more notes note'''
    ids = c.multipattern_to_ids(pattern, group, tags)
    for id in ids:
        c.cat_one(id, no_header)


@cli.command()
@click.argument('pattern', nargs=-1)
@click.option('--bib-file', '-b', default=None)
@click.option('--group', '-g', default=None)
@click.option('--tags', '-t', default=None)
@click.option('--reload', '-r', is_flag=True, 
        help="dont use the cached entry")
def tobib(pattern: str, bib_file: str, group: str, tags: str, reload: bool):
    """Adds bibtex entries for the given notes to a bibtex
    file. If no bibtex file is specified, the first in the current working
    directory is used."""
    bib_path = c.get_bib_path(bib_file)
    if bib_path is None:
        c.error("Couldnt open bib-file. Try specifying one with -b")

    doi_index = c.load_doi_index()
    group_index = c.load_group_index()
    title_index = c.load_title_index()
    tags_index = c.load_tag_index()
    config = c.load_config()
    ids = c.multipattern_to_ids(pattern, group, tags, config, None, group_index, 
                                title_index, tags_index)

    doi_lookup = {str(id): doi 
                  for doi, _ids in doi_index.items() for id in _ids}
    removed_ids, remaining_ids = [], []
    for id in ids:
        if id in doi_lookup:
            remaining_ids.append(id)
        else:
            removed_ids.append(id)

    if len(removed_ids) > 0:
        print("Warning: the following notes were part of the query, but dont "
              "contain a doi and were ignored:")
        removed_rows = [c.id_to_row(int(id), config, group_index, title_index)
                        for id in removed_ids]
        c.print_table(removed_rows)

    if len(remaining_ids) == 0:
        c.error("No files with Doi remaining")

    if bib_path.exists():
        bib = bib_path.read_text()
    else:
        bib = ""

    for id in remaining_ids:
        entry = c.load_bibtex_cached(doi_lookup[id], reload_cache=reload)
        bib = c.add_to_bib(entry, bib)

    bib_path.write_text(bib)


@cli.command()
def pmd():
    '''Prints the path of the directory where the md files are stored.

    Intended usage: cd `mdn pmd` '''
    print(str(Path(c.load_config().save_path, 'md')))



@cli.command()
@click.argument("pattern")
@click.option("--regex", "-r", is_flag=True)
@click.option("--no-wildcard", "-n", is_flag=True)
def fd(pattern: str, regex: bool, no_wildcard: bool):
    """Searches through the content of all Notes. Treats * as wildcard"""
    if regex:
        pattern = re.compile(pattern)
    elif no_wildcard:
        pattern = re.compile(re.escape(pattern), re.IGNORECASE)
    else:
        elems = pattern.split("*")
        pattern = ".*".join(re.escape(elem) for elem in elems)
        pattern = re.compile(pattern, re.IGNORECASE)

    config = c.load_config()
    files = (Path(config.save_path) / "md").iterdir()
    results = {file.stem: hits for file in files
            if (hits := c.get_hits(pattern, file.read_text()))}
    title_lookup = {str(id): title 
                    for title, ids in c.load_title_index().items() for id in ids}
    for (id, hits) in results.items():
        print(f"{id}: {title_lookup[id]}")
        for hit in hits:
            print("\t", hit)


@cli.command()
@click.option("--port", "-p", default=5000, type=int)
def serve(port):
    """launches a webserver on localhost:5000 to read notes"""
    from . import flaskr
    import webbrowser
    webbrowser.open_new(f'http://127.0.0.1:{port}/')
    flaskr.run(port)
