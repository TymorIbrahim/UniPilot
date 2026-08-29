"""Parse catalog prerequisite text into the boolean expression it states.

Why this exists
---------------
The catalog carries prerequisites as text, in a small and remarkably consistent
grammar: 8-digit course numbers joined by `ו-` (and) and `או` (or), grouped
with parentheses. Of the 1,634 courses that state prerequisites, all but three
are covered by that grammar alone -- there is no prose to contend with.

`extract_course_numbers_from_text` reads the same text as a flat list of course
numbers, which silently turns every `או` into an `ו-`:

    00970215:  02360756 או 00960411 או 00460203 או 00460202 או 00460195

means "any ONE of five", and is read as "all five". Across the catalog that is
769 of the 1,105 courses using either operator -- only the 336 pure-`ו-` ones
survive the flattening intact. Students are told they are missing courses they
never needed, and the reverse dependency graph counts edges that do not exist.

Precedence
----------
`ו-` binds tighter than `או`, which is what the unparenthesised catalog text
relies on:

    01240400 ו-02340128 או 01150203 ו-02340128

is two alternative PAIRS, not two courses and two alternatives. Parentheses
override it, and 378 courses use them.

Text we do not understand
-------------------------
Parsing is all-or-nothing: anything the grammar does not cover raises rather
than yielding a partial tree. A partial parse is precisely how a disjunction
became a conjunction in the first place, and a prerequisite rule that is
half-read is more dangerous than one that is admittedly unread -- the caller
can fall back to conservative behaviour only if it is told.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from typing import Iterable, Union

from app.planning.prerequisite_resolver import canonical_course_number

MAX_ALTERNATIVES = 32
"""Cap on the alternatives `missing_alternatives` will enumerate.

A deeply nested expression expands combinatorially. No catalog entry comes
close today, but a list longer than this is unreadable anyway, so it is
truncated rather than allowed to grow without bound.
"""


class PrerequisiteParseError(ValueError):
    """The prerequisite text is not fully covered by the grammar."""


@dataclass(frozen=True)
class CourseLeaf:
    """One course, normalised to its 8-digit form."""

    course_number: str


@dataclass(frozen=True)
class AllOf:
    """Every child must be satisfied (`ו-`)."""

    children: tuple["Node", ...]


@dataclass(frozen=True)
class AnyOf:
    """At least one child must be satisfied (`או`)."""

    children: tuple["Node", ...]


Node = Union[CourseLeaf, AllOf, AnyOf]

_TOKEN_PATTERN = re.compile(
    r"""
      (?P<space>\s+)
    | (?P<lparen>\()
    | (?P<rparen>\))
    | (?P<or>או)
    | (?P<and>ו[-־])
    | (?P<number>\d{6,9})
    """,
    re.VERBOSE,
)


def _tokenize(text: str) -> list[tuple[str, str]]:
    """`(kind, value)` pairs, or raise if any character is not covered.

    `או` starts with aleph and `ו-` with vav, so the two never compete for the
    same position -- but the scan is still strictly left to right so that a
    stray character fails loudly instead of being skipped.
    """
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(text):
        match = _TOKEN_PATTERN.match(text, position)
        if match is None:
            raise PrerequisiteParseError(
                f"unrecognised text at offset {position}: {text[position:position + 20]!r}"
            )
        kind = match.lastgroup or ""
        if kind == "number":
            number = canonical_course_number(match.group())
            if number is None:
                raise PrerequisiteParseError(f"not a course number: {match.group()!r}")
            tokens.append(("number", number))
        elif kind != "space":
            tokens.append((kind, match.group()))
        position = match.end()
    return tokens


class _Parser:
    """Recursive descent over `expr := term ('או' term)*`,
    `term := atom ('ו-' atom)*`, `atom := NUMBER | '(' expr ')'`."""

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self._tokens = tokens
        self._index = 0

    def _peek(self) -> str | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index][0]

    def _advance(self) -> tuple[str, str]:
        token = self._tokens[self._index]
        self._index += 1
        return token

    def parse(self) -> Node:
        expression = self._parse_or()
        if self._index != len(self._tokens):
            raise PrerequisiteParseError("trailing tokens after a complete expression")
        return expression

    def _parse_or(self) -> Node:
        children = [self._parse_and()]
        while self._peek() == "or":
            self._advance()
            children.append(self._parse_and())
        return children[0] if len(children) == 1 else AnyOf(tuple(children))

    def _parse_and(self) -> Node:
        children = [self._parse_atom()]
        while self._peek() == "and":
            self._advance()
            children.append(self._parse_atom())
        return children[0] if len(children) == 1 else AllOf(tuple(children))

    def _parse_atom(self) -> Node:
        kind = self._peek()
        if kind == "number":
            return CourseLeaf(self._advance()[1])
        if kind == "lparen":
            self._advance()
            expression = self._parse_or()
            if self._peek() != "rparen":
                raise PrerequisiteParseError("unbalanced parenthesis")
            self._advance()
            return expression
        raise PrerequisiteParseError(f"expected a course number, found {kind or 'end of text'}")


def parse_prerequisite_expression(text: str | None) -> Node | None:
    """The expression the text states, or None when it states nothing.

    Raises `PrerequisiteParseError` when the text is not blank but is not fully
    covered by the grammar -- see the module docstring on why a partial parse
    is not offered.
    """
    if text is None or not str(text).strip():
        return None
    return _Parser(_tokenize(str(text).strip())).parse()


def _normalize(numbers: Iterable[str]) -> set[str]:
    return {
        normalized
        for raw in numbers
        if (normalized := canonical_course_number(raw)) is not None
    }


def is_satisfied_by(expression: Node | None, completed: Iterable[str]) -> bool:
    """Whether a student who has passed `completed` meets the requirement."""
    if expression is None:
        return True
    return _is_satisfied(expression, _normalize(completed))


def _is_satisfied(expression: Node, completed: set[str]) -> bool:
    if isinstance(expression, CourseLeaf):
        return expression.course_number in completed
    if isinstance(expression, AllOf):
        return all(_is_satisfied(child, completed) for child in expression.children)
    return any(_is_satisfied(child, completed) for child in expression.children)


def course_numbers(expression: Node | None) -> set[str]:
    """Every course the expression mentions, in any branch.

    This is the edge set for the reverse dependency graph: a course named in
    any alternative is one whose deferral can block this course.
    """
    if expression is None:
        return set()
    if isinstance(expression, CourseLeaf):
        return {expression.course_number}
    numbers: set[str] = set()
    for child in expression.children:
        numbers |= course_numbers(child)
    return numbers


def missing_alternatives(
    expression: Node | None,
    completed: Iterable[str],
    *,
    limit: int = MAX_ALTERNATIVES,
) -> list[frozenset[str]]:
    """The distinct sets of courses that would each satisfy the requirement.

    An empty frozenset means nothing further is needed, so a satisfied
    expression returns `[frozenset()]` -- distinct from `[]`, which would read
    as "no way to satisfy this".

    Alternatives that are supersets of a cheaper one are dropped: offering both
    `{A}` and `{A, B}` invites doing work that was never required.
    """
    if expression is None:
        return [frozenset()]
    alternatives = _alternatives(expression, _normalize(completed), limit)
    return _drop_supersets(alternatives)[:limit]


def _alternatives(
    expression: Node, completed: set[str], limit: int
) -> list[frozenset[str]]:
    if isinstance(expression, CourseLeaf):
        if expression.course_number in completed:
            return [frozenset()]
        return [frozenset({expression.course_number})]

    if isinstance(expression, AnyOf):
        combined: list[frozenset[str]] = []
        for child in expression.children:
            combined.extend(_alternatives(child, completed, limit))
        return combined

    per_child = [_alternatives(child, completed, limit) for child in expression.children]
    combined = []
    for combination in product(*per_child):
        combined.append(frozenset().union(*combination))
        if len(combined) >= limit:
            break
    return combined


def _drop_supersets(alternatives: list[frozenset[str]]) -> list[frozenset[str]]:
    """Deduplicate, keeping first-seen order, and remove any alternative that
    strictly contains another."""
    unique: list[frozenset[str]] = []
    for alternative in alternatives:
        if alternative not in unique:
            unique.append(alternative)
    return [
        alternative
        for alternative in unique
        if not any(other < alternative for other in unique)
    ]
