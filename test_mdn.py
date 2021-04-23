import pytest

from markdown_note.markdown_note import (insert_index_entry, parse_file,
                                         remove_index_entry, strip_lines,
                                         update_multi_index)
from markdown_note.tag_string_parser import (ParserError,
                                             create_predicate_from_tag_str)


def test_tag_parsing():
    with pytest.raises(ParserError):
        create_predicate_from_tag_str('invalid')
    tags = {'@a', '@b', '@foo'}
    assert create_predicate_from_tag_str('@a')(tags)
    assert create_predicate_from_tag_str('@foo | @bar')(tags)
    assert not create_predicate_from_tag_str('@foo & @bar')(tags)
    assert create_predicate_from_tag_str('(@foo & @bar) | @b')(tags)
    assert not create_predicate_from_tag_str('-@a')(tags)
    assert create_predicate_from_tag_str('-@c')(tags)
    assert not create_predicate_from_tag_str('-(@a | @bar)')(tags)
    assert create_predicate_from_tag_str('-(@a & @bar)')(tags)
    assert create_predicate_from_tag_str('-(@c | (@a & @d))')(tags)


def test_remove_index():
    new_ind = remove_index_entry({
        'foo': {1, 2},
        'bar': {3, 4}
    }, 'foo', 1)
    assert new_ind['foo'] == {2}
    new_ind = remove_index_entry(
        new_ind, 'foo', 2)
    assert 'foo' not in new_ind


def test_insert_index_entry():
    ind = insert_index_entry({}, 'foo', 1)
    assert ind['foo'] == {1}
    assert insert_index_entry(ind, 'foo', 2) == {'foo': {1, 2}}


def test_update_tags_index():
    ind = {'foo': {1, 2},
           'bar': {2, 3, 4},
           'baz': {3, 4}}
    old = { 'foo', 'bar' }
    new = { 'bar', 'baz' }
    nind = update_multi_index(ind, new, old, 2)
    assert nind == {
        'foo': {1},
        'bar': {2, 3, 4},
        'baz': {2, 3, 4}
    }


def test_parse_file():
    content = strip_lines('''
        ---
        title: Test Note
        group: foo
        ---
        This is a @Baz note. It's the the most @baz like note ever.
        Its a little @bar too.
        ''')
    title, tags, group, doi = parse_file(content)
    assert title == 'Test Note'
    assert tags == {'@baz', '@bar'}
    assert group == 'foo'
    assert doi == None
