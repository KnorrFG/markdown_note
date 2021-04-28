# Markdown Note
Markdown note is a command line tool to write notes in markdown using your
favorite text editor, which can then be viewed in a browser as html. The html
also is rendered every time you save while editing the note. Additionally it
has some light weight bibliography management features. For more details, read
my [article](https://knorrfg.github.io/mdn)

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

If you are in a situation where you want to switch between notes rapidly, you
can startup a web server, and use the brower via `mdn serve`

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
aa          Add Asset Coppies target to asset-folder/save-path
cat         Display the md version of one or more notes note
edit        edit a note
fd          Searches through the content of all Notes.
ls          Show a list of all existing notes.
lsg         Shows a list of all existing groups
lst         Shows a list of all existing tags
new         creates a new note
pmd         Prints the path of the directory where the md files are...
regenerate  recreates all index files.
rm          Deletes selected files.
serve       launches a webserver on localhost:5000 to read notes
show        Display the html version of one or more notes 
tobib       Adds bibtex entries for the given notes to a bibtex file.
```
 
## Installation:
mdn is written with python and requires version 3.8
Installation via pip:
```
pip install git+https://github.com/KnorrFG/markdown_note.git
```
