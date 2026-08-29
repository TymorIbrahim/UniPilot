"""Price the decision to postpone a course to a later semester.

Why this exists
---------------
A required course is not a course the student must take *now* -- it is one they
must take *eventually*. Deferring one is ordinary and often sensible: to lighten
a semester, to retake something, to fit work around study. So the planner's job
for a mandatory course is not to decide whether, but to make the cost of *when*
visible.

Two facts set that cost, and a student can see neither of them from the course
page:

Cadence. 1,833 of 2,613 catalog courses -- 70% -- are offered in exactly one
term per year. For those, "I'll take it next semester" actually means "I'll take
it in twelve months". Which case a course falls into is the single most useful
thing to say at the moment of deferral, and it is better said as a date than as
a number of terms.

Dependents. Postponing a course that gates three others postpones four slots,
not one. The edges come from the parsed prerequisite expression, counting every
branch of an alternative: if A is one of two ways into B, deferring A can still
block B for a student who has not taken the other way.

The dependent count is a LOWER BOUND. 979 of 2,613 courses state no
prerequisites at all, so zero means "none recorded", never "nothing depends on
this" -- and the payload says so rather than leaving the reader to assume.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from app.planning.prerequisite_expression import (
    PrerequisiteParseError,
    course_numbers,
    parse_prerequisite_expression,
)
from app.planning.prerequisite_resolver import canonical_course_number

WINTER = 200
SPRING = 201
SUMMER = 202

TERM_ORDER: tuple[int, ...] = (WINTER, SPRING, SUMMER)
"""The three Technion terms in the order they run within an academic year."""

TERMS_PER_YEAR = len(TERM_ORDER)


def _offered_terms(raw: Iterable[Any] | None) -> set[int]:
    terms: set[int] = set()
    for value in raw or []:
        try:
            term = int(value)
        except (TypeError, ValueError):
            continue
        if term in TERM_ORDER:
            terms.add(term)
    return terms


def _term_index(academic_year: int, term: int) -> int:
    """A single increasing coordinate so terms in different years compare."""
    return academic_year * TERMS_PER_YEAR + TERM_ORDER.index(term)


def next_offering(
    semesters_offered: Sequence[Any] | None,
    *,
    after: tuple[int, int],
) -> tuple[int, int] | None:
    """The first (academicYear, term) strictly after `after` that runs the course.

    None when the catalog records no term for the course: a course we cannot
    schedule has an unknown deferral cost, not a free one.
    """
    terms = _offered_terms(semesters_offered)
    if not terms:
        return None

    academic_year, term = after
    if term not in TERM_ORDER:
        return None

    position = _term_index(academic_year, term)
    # At most one full cycle is needed to find the next occurrence.
    for step in range(1, TERMS_PER_YEAR + 1):
        candidate = position + step
        candidate_year, candidate_index = divmod(candidate, TERMS_PER_YEAR)
        candidate_term = TERM_ORDER[candidate_index]
        if candidate_term in terms:
            return candidate_year, candidate_term
    return None


def build_dependent_index(
    catalog_courses: Iterable[dict[str, Any]],
) -> dict[str, frozenset[str]]:
    """Reverse prerequisite edges: course number -> courses that require it.

    Every branch of an alternative contributes an edge. A course whose
    prerequisite text the grammar does not cover contributes none -- an
    unread rule is not evidence of absence, and the count is documented as a
    lower bound for exactly this reason.
    """
    dependents: dict[str, set[str]] = {}
    for course in catalog_courses:
        dependent = canonical_course_number(course.get("courseNumber"))
        if dependent is None:
            continue
        try:
            expression = parse_prerequisite_expression(course.get("prerequisitesText"))
        except PrerequisiteParseError:
            continue
        for prerequisite in course_numbers(expression):
            dependents.setdefault(prerequisite, set()).add(dependent)
    return {number: frozenset(values) for number, values in dependents.items()}


def describe_deferral(
    course: dict[str, Any],
    *,
    after: tuple[int, int],
    dependent_index: dict[str, frozenset[str]],
) -> dict[str, Any]:
    """What postponing this course past `after` would cost."""
    course_number = canonical_course_number(course.get("courseNumber"))
    terms = _offered_terms(course.get("semestersOffered"))
    upcoming = next_offering(course.get("semestersOffered"), after=after)

    terms_until = None
    if upcoming is not None:
        terms_until = _term_index(*upcoming) - _term_index(*after)

    dependent_numbers = sorted(dependent_index.get(course_number or "", frozenset()))

    return {
        "courseNumber": course_number,
        "semestersOffered": sorted(terms),
        "offeredOncePerYear": len(terms) == 1,
        "nextOffering": (
            {"academicYear": upcoming[0], "semesterCode": upcoming[1]}
            if upcoming is not None
            else None
        ),
        "termsUntilNextOffering": terms_until,
        "dependentCount": len(dependent_numbers),
        "dependentCourseNumbers": dependent_numbers,
        # 979 of 2,613 catalog courses state no prerequisites, so an absent
        # edge is not evidence that nothing depends on this course.
        "dependentCountIsLowerBound": True,
    }
