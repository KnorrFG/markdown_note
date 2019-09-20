# MarkdownNote (mdn)

* saves notes as markdown
  * stored somewhere in the filesystem, so that it can be synchornized via
    git/dropbox
* Editor must be configurable
* displays as html
  * html pages are stored in an extra cache dir
* Any word within a note that starts with @ is a tag, and that can be searched by the console interface
* also grep search can be used via console interface
* and creation and editing dates
* Supports notegroups (notebooks) and group-groups. This way notes organization
  can be arbitrarily nested.
* Notes have a yaml front-matter containing groups and title which is not rendered
* config file with following options:
  * Editor call
  * save dir
  * cache dir
  * browser call
  * all of which should be optional

## Open questions:
* Images
* note identifications?
    * A note must be identifiable via cmd, and that must not put restrictions on
      the title
    * simple ID by counter?

## File structure
* one file per note
* one index file
* an extra folder for images
  
## Interface
* `pynote new`  
    creates a new note
* `pynote edit [<id>]`
* `pynote show [<id>]`  
    * special identifiers
        * '_c' for created
        * '_s' for shown
        * '_e' for edited
    * if not number or special id a fuzzy search along the titles will be executedj
    * without id will default to 'last_created'

* `pynote cat [--no-yaml] <id>`
* `pynode ls [-from date] [-to date] [-tag tag] [-group group] [<fuzzy search string>]`:  
searches titles of notes with fuzzy search
displays date, title, id
* `pynode grep [-from date] [-to date] [-tag tag] [-group group] <re>`:  
searches note contents with regular expression
* `pynote ls-group [<fuzzy search str>]`  
lists existing groups that match
* `pynote as-add <file> [<id>]`:  
    Adds asset to the asset folder. Id can be provided. Overwrites existing assets if id already exists.


## Implementation details:
* Assets will be used `/` path in html links. 
* There will be a need for an index file for the groups and tags. It should be possible to regenerate this file.
* When a file is edited in an editor a prev-version needs to be kept, so changes that are relevant for the index files can be determined.