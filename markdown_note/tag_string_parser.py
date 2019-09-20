from typing import Callable, Tuple, Any, Set, List
from dataclasses import dataclass
from collections import defaultdict

And = 0
Or = 1

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


def _digest(s: str) -> Tuple[Any, str]:
    if s[0] == '(':
        end = s.find(')')
        return Paranthesis(s[1:end]), s[end + 1:]
    elif s[0] == '@':
        word_end_candidates = [end for end in 
                                (s.find(x) for x in [' ', ',', ';', '('])
                                if end > 0]
        if len(word_end_candidates) > 0:
            end = min(word_end_candidates)
            return Tag(s[0:end]), s[end:]
        else:
            return Tag(s), ''
    elif s[0] == ',':
        return And, s[1:]
    elif s[0] == ';':
        return Or, s[1:]
    else:
        raise ValueError('Error parsing tag strin at: ' + s)


def _get_object_repr(objs: List[Any], s: str) -> List[Any]:
    if s == "": 
        return objs
    else: 
        new_obj, remaining_str = _digest(s.strip())
        return _get_object_repr(objs + [new_obj], remaining_str.strip())


def _split_at(objs, split_target, result):
    try:
        end = next(i for i, obj in enumerate(objs) if obj == split_target)
        return _split_at(objs[end + 1:], split_target, result + [objs[:end]])
    except StopIteration:
        return result + [objs]


def transform_and_group(group):
    if not all(x == And for x in group[1::2]):
        raise ValueError(
            'There is an And-group where not every second element is an And')
    if len(group) > 1:
        return AndNode(group[::2])
    else:
        return group[0]


def _to_tree(objs):
    and_groups = _split_at(objs, Or, [])
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
