from typing import Callable, Tuple, Any, Set, List
from dataclasses import dataclass
from collections import defaultdict

And = 0
and_symbol = '&'
Or = 1
or_symbol = '|'
Not = 2
not_symbol = '-'

@dataclass
class Tag:
    name: str
    def __call__(self, tags: Set[str]) -> bool:
        return self.name in tags


@dataclass
class Paranthesis:
    string: str


@dataclass
class AndNode:
    children: list
    def __call__(self, tags: Set[str]) -> bool:
        return all(child(tags) for child in self.children)


@dataclass
class OrNode:
    children: list
    def __call__(self, tags: Set[str]) -> bool:
        return any(child(tags) for child in self.children)


@dataclass
class NotNode:
    children: list
    def __call__(self, tags: Set[str]) -> bool:
        assert len(self.children) == 1
        return not self.children[0](tags)


def _find_matching_closing_paranthesis(s: str, open_pars=0, idx=1):
    '''Expects that s does not contain the opening paranthesis, for which the
    corresponding closing one is searched.
    If the input was 'foo)' the result will be 4'''
    if s[0] == '(':
        return _find_matching_closing_paranthesis(
                s[1:], open_pars + 1, idx + 1)
    elif s[0] == ')':
        if open_pars == 0:
            return idx
        else:
            return _find_matching_closing_paranthesis(
                    s[1:], open_pars - 1, idx + 1)
    else:
        return _find_matching_closing_paranthesis(
                s[1:], open_pars, idx + 1)


def _digest(s: str) -> Tuple[Any, str]:
    if s[0] == '(':
        end = _find_matching_closing_paranthesis(s[1:])
        return Paranthesis(s[1:end]), s[end + 1:]
    elif s[0] == '@':
        word_end_candidates = [end for end in 
                                (s.find(x) for x in 
                                    [' ', and_symbol, or_symbol, 
                                     '(', not_symbol])
                                if end > 0]
        if len(word_end_candidates) > 0:
            end = min(word_end_candidates)
            return Tag(s[0:end]), s[end:]
        else:
            return Tag(s), ''
    elif s[0] == and_symbol:
        return And, s[1:]
    elif s[0] == or_symbol:
        return Or, s[1:]
    elif s[0] == not_symbol:
        return Not, s[1:]
    else:
        raise ValueError('Error parsing tag strin at: ' + s)


def _get_object_repr(objs: List[Any], s: str) -> List[Any]:
    '''Converts a string into its object representation, on direct call use an
    empty list as first arg'''
    if s == "": 
        return objs
    else: 
        new_obj, remaining_str = _digest(s.strip())
        return _get_object_repr(objs + [new_obj], remaining_str.strip())


def _split_at(objs, split_target, result):
    '''like str.split for arbitrary object lists'''
    try:
        end = next(i for i, obj in enumerate(objs) if obj == split_target)
        return _split_at(objs[end + 1:], split_target, result + [objs[:end]])
    except StopIteration:
        return result + [objs]


def transform_and_group(group):
    '''takes a list of object representations, as returned by _get_object_repr.
    Expects that all those objects should be concatenated via and, so every
    second object must be `And` and returns an AndNode, or if the list only has
    one element, the element.'''
    if not all(x == And for x in group[1::2]):
        raise ValueError(
            'There is an And-group where not every second element is an And')
    if len(group) > 1:
        return AndNode(group[::2])
    else:
        return group[0]


def _bind_nots(objs: List[Any], result = None):
    '''replaces every [..., Not, X, ...] by NotNode(X)'''
    if len(objs) == 0:
        return result
    if result is None:
        result = []
    if objs[0] == Not:
        if len(objs) < 2:
            raise ValueError('There is a `-` without following target')
        return _bind_nots(objs[2:], result + [NotNode([objs[1]])])
    else:
        return _bind_nots(objs[1:], result + objs[:1])
    


def _to_tree(objs):
    and_groups = _split_at(_bind_nots(objs), Or, [])
    if len(and_groups) == 1:
        return transform_and_group(and_groups[0])
    return OrNode([transform_and_group(group) for group in and_groups])


def _clean_tree(tree):
    if type(tree) == Tag:
        return tree
    if type(tree) != Paranthesis:
        # Must be AndNode or OrNode here
        return type(tree)([_clean_tree(child) for child in tree.children])
    return create_predicate_from_tag_str(tree.string)


def create_predicate_from_tag_str(s: str)-> Callable[[Set[str]], bool]:
    return _clean_tree(_to_tree(_get_object_repr([], s)))
