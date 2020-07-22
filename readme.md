# Markdown Note
Markdown note is a command line tool to write notes in markdown using your
favorite text editor, which can then be viewed in a browser as html. The html
also is rendered every time you save while editing the note

All Notes are stored as plaintext files in the directory that you provide
as save-path in the configuration file ~/.mdnrc which will be
automatically created by your specification uppon first usage.
I recomend using a Dropbox path. Sensible defaults are provided for Linux and
Windows.

All Notes must have a yaml front matter with a title and a group. Think of
a group as a notebook. 

All words that start with a @ within a note are considered tags and 
`mdn ls` accepts a filter string allows to filter notes by a logical formula
describing whether tags should be existing or not, e.g.:`"@foo & -@bar"`
which means the note must have the tag @foo but must not have the tag
@bar.

Information about tags titles and groups are stored in index files. In
case the index diverges from the correct state (e.g. because the files
were modified outside of mdn) you can use `mdn regenerate` to recreate the
index files.

## Examples
### Create a new note
```
mdn new
```

### Edit an existing note
```
mdn edit <fuzzy match pattern for the title or id>
```

### Show a note as html in a browser
```
mdn show <fuzzy match pattern for the title or id>
```

## Commands
```
aa          Add Asset. Coppies target to asset-folder/save-path
cat         Prints the notes source to stdout.
edit        edit a note
ls          Show a list of all existing notes.
new         creates a new note
regenerate  recreates all index files.
rm          Deletes selected files.
show        Display the html version of one or more notes note
```
 
## Installation:
mdn is written with python and requires version 3.7
Installation via pip:
```
pip install git+https://github.com/KnorrFG/markdown_note.git
```
