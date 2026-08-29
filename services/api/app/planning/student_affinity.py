"""What a student's own record says about which courses are relevant to them.

Derived, not declared
---------------------
`preferences` is empty on real profiles -- there are no stated interests to
read. Everything here is inferred from what the student has actually done,
which is the only personal signal the system holds.

Relevance, not difficulty
-------------------------
The line this module holds: personalise on what a student has shown interest
in and is prepared for, never on where they would score highest.

One real transcript averages 87 in humanities, 76 in data science and 55 in
mathematics. Ranking maths courses down for that student would narrow their
degree, entrench the weakness, and is the personalised form of ranking by pass
rate -- a recommendation optimised for an easy semester rather than a good one.
It is also built on four courses.

So performance never orders anything. `describe_readiness` exists to put a
specific fact on a card -- "you passed this course's prerequisite with 57" --
which is about preparation for THAT course, not about the student's general
ability, and which the student can act on by choosing to prepare or to accept
the risk. Ordering stays a question of relevance.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from app.planning.prerequisite_expression import (
    PrerequisiteParseError,
    course_numbers,
    parse_prerequisite_expression,
)
from app.planning.prerequisite_resolver import canonical_course_number

CHOSEN_REQUIREMENT_TYPES = frozenset({"elective", "enrichment", "free_elective"})
"""Requirement types whose completed courses reflect a decision by the student.

Core courses were assigned by the degree. Counting them measures what the
programme demanded, not what the student prefers -- for one real transcript it
would report a 30-to-1 preference for their own faculty, which is simply the
shape of the curriculum.
"""


def _normalized(numbers: Iterable[Any]) -> set[str]:
    return {
        number
        for raw in numbers
        if (number := canonical_course_number(raw)) is not None
    }


def build_elective_affinity(
    requirement_progress: Sequence[dict[str, Any]],
    *,
    faculties_by_number: dict[str, str | None],
) -> dict[str, float]:
    """Share of the student's own elective choices going to each faculty.

    Weights sum to 1 across the faculties they have chosen from, so the value
    is a share of revealed interest rather than a raw count -- comparable
    between a student with four free choices and one with twenty.
    """
    counts: dict[str, int] = {}
    total = 0
    for entry in requirement_progress or []:
        if str(entry.get("requirementType") or "") not in CHOSEN_REQUIREMENT_TYPES:
            continue
        for course in entry.get("completedCourses") or []:
            number = canonical_course_number((course or {}).get("courseNumber"))
            if number is None:
                continue
            faculty = faculties_by_number.get(number)
            if not faculty:
                continue
            counts[str(faculty)] = counts.get(str(faculty), 0) + 1
            total += 1

    if not total:
        return {}
    return {faculty: count / total for faculty, count in counts.items()}


def pool_momentum(
    pool_course_numbers: Iterable[str],
    *,
    completed: Iterable[str],
) -> tuple[int, int]:
    """How much of a pool the student has already worked through.

    A chain they have started is evidence of an interest they chose, which is
    the closest thing in this data to "because you watched that". Returned as
    (taken, total) rather than a ratio so the row can say "3 of 19" -- a share
    alone cannot distinguish 1-of-2 from 10-of-20.
    """
    pool = _normalized(pool_course_numbers)
    return len(pool & _normalized(completed)), len(pool)


def describe_readiness(
    prerequisites_text: str | None,
    *,
    grades: dict[str, float],
) -> dict[str, Any] | None:
    """The student's weakest grade among prerequisites they actually took.

    Only prerequisites with a recorded grade count: an alternative they never
    took is not evidence about their preparation. Returns None when there is
    nothing to say, so the card shows nothing rather than a reassuring blank.
    """
    try:
        expression = parse_prerequisite_expression(prerequisites_text)
    except PrerequisiteParseError:
        return None
    if expression is None:
        return None

    taken = [
        (number, grades[number])
        for number in sorted(course_numbers(expression))
        if number in grades
    ]
    if not taken:
        return None

    weakest_course, weakest_grade = min(taken, key=lambda item: (item[1], item[0]))
    return {
        "weakestPrerequisiteCourse": weakest_course,
        "weakestPrerequisiteGrade": weakest_grade,
    }
