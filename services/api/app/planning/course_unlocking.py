"""What taking a course now would open up later.

The signal being thrown away
----------------------------
435 of the courses offered in one term are exactly ONE course away from being
available to one real student. Today they are filtered off the rows and
tallied into `ineligibleCount`, and the course that would open them gets no
credit for opening them.

That is the forward mirror of `course_deferral`: deferral asks what postponing
a course costs, and this asks what taking it buys. Both read the same
prerequisite graph, but this one is relative to the student -- it is not "what
lists this as a prerequisite" but "what would become available to THIS student
if they took it and nothing else".

Only unlocks that could count
-----------------------------
`relevant` restricts the answer to courses that could still advance one of the
student's unsatisfied requirements. Unlocking a course that counts toward
nothing is worth nothing, and counting it would flatter a near-graduation
student with a wall of options they have no room left to take.

This is also why the signal needs no runway threshold. A student with one
requirement left has few relevant courses to unlock and a small number falls
out on its own; a second-year with four open buckets has many. The scaling is
derived from their position rather than switched on at a credit count someone
picked.

An alternative not yet reachable is not a promise
--------------------------------------------------
Only alternatives the student is a SINGLE course from completing count. Taking
one half of a conjunction leaves the course blocked, and reporting it as
unlocked would be a promise they cannot cash next semester.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from app.planning.prerequisite_expression import (
    PrerequisiteParseError,
    is_satisfied_by,
    missing_alternatives,
    parse_prerequisite_expression,
)
from app.planning.prerequisite_resolver import canonical_course_number


def build_unlock_index(
    courses: Sequence[dict[str, Any]],
    *,
    completed: Iterable[str],
    relevant: Iterable[str],
) -> dict[str, frozenset[str]]:
    """Course number -> the blocked courses that taking it alone would open."""
    passed = {
        number
        for raw in completed
        if (number := canonical_course_number(raw)) is not None
    }
    countable = {
        number
        for raw in relevant
        if (number := canonical_course_number(raw)) is not None
    }

    unlocks: dict[str, set[str]] = {}
    for course in courses:
        blocked = canonical_course_number(course.get("courseNumber"))
        if blocked is None or blocked not in countable:
            continue
        try:
            expression = parse_prerequisite_expression(course.get("prerequisitesText"))
        except PrerequisiteParseError:
            continue
        if expression is None or is_satisfied_by(expression, passed):
            continue

        for option in missing_alternatives(expression, passed):
            if len(option) != 1:
                continue
            unlocks.setdefault(next(iter(option)), set()).add(blocked)

    return {number: frozenset(opened) for number, opened in unlocks.items()}
