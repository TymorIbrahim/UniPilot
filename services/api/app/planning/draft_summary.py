"""Describe the semester the student has assembled, not the next course.

Why this is separate from the cards
-----------------------------------
A card answers "should I add this". It cannot answer "is what I have built
sensible", which is the question students get wrong most often -- and the two
facts that answer it only exist at the level of the whole basket.

Difficulty, finally used
------------------------
`meanDifficultyRank` sits on 821 courses and drives nothing, deliberately: a
hard course is not a worse course, and ranking a menu by difficulty steers
students away from material they came to learn. Aggregated over a draft it
answers a different and legitimate question -- how this semester compares with
the ones this student has already carried. That comparison is against their own
record rather than a fixed threshold, so it needs no invented notion of "too
hard" and adapts to a student who thrives on load.

Exam crowding
-------------
Exam dates are published for 100% of offerings, better coverage than any other
signal we hold, and until now only same-day collisions were caught. Three exams
in four days is the avoidable harm students care about most and it is invisible
on every individual card, because it is a property of the combination.

Absent rather than zero
-----------------------
An empty draft has no difficulty and no exam spread; a student who has picked
nothing has not built a light semester. Every aggregate here is None when there
is nothing to compute it from, and reports its own coverage where the
underlying data is thin -- a difficulty mean over one of four courses is not a
description of the semester.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Sequence

from app.planning.prerequisite_resolver import canonical_course_number

HEAVIER_THAN_USUAL_MARGIN = 0.5
"""How far above their own average a draft must sit before it is called heavy.

On a 1-5 scale, half a point is a difference a student would recognise; below
it the comparison is noise dressed as a finding.
"""


def _number(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _mean_difficulty(
    course_numbers: Iterable[str],
    ratings: dict[str, dict[str, Any]],
) -> tuple[float | None, int]:
    values = [
        value
        for number in course_numbers
        if (value := _number((ratings.get(number) or {}).get("meanDifficultyRank"))) is not None
    ]
    if not values:
        return None, 0
    return sum(values) / len(values), len(values)


def _parse_exam_day(raw: Any) -> date | None:
    """Exam dates arrive ISO from `exams_from_offering`; anything else is skipped."""
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def _exam_summary(
    planned_numbers: list[str],
    exams_by_course: dict[str, Sequence[Any]],
) -> dict[str, Any]:
    """Earliest sitting per course, and the tightest gap between any two."""
    first_sitting: dict[str, date] = {}
    without_exam = 0
    for number in planned_numbers:
        days = [
            parsed
            for raw in (exams_by_course.get(number) or [])
            if (parsed := _parse_exam_day(raw)) is not None
        ]
        if days:
            first_sitting[number] = min(days)
        else:
            without_exam += 1

    ordered = sorted(first_sitting.items(), key=lambda item: (item[1], item[0]))
    tightest_gap: int | None = None
    tightest_pair: list[str] | None = None
    for (left_number, left_day), (right_number, right_day) in zip(ordered, ordered[1:]):
        gap = (right_day - left_day).days
        if tightest_gap is None or gap < tightest_gap:
            tightest_gap = gap
            tightest_pair = [left_number, right_number]

    return {
        "examCount": len(first_sitting),
        "withoutPublishedExam": without_exam,
        "tightestGapDays": tightest_gap,
        "tightestPair": tightest_pair,
        "firstExam": ordered[0][1].isoformat() if ordered else None,
        "lastExam": ordered[-1][1].isoformat() if ordered else None,
    }


def build_draft_summary(
    planned_courses: Sequence[dict[str, Any]],
    *,
    ratings: dict[str, dict[str, Any]],
    completed_course_numbers: Iterable[str],
    exams_by_course: dict[str, Sequence[Any]],
) -> dict[str, Any]:
    """What the student has built so far, as a whole."""
    planned_numbers = [
        number
        for course in planned_courses
        if (number := canonical_course_number(course.get("courseNumber"))) is not None
    ]

    credits = 0.0
    for course in planned_courses:
        value = _number(course.get("credits"))
        if value is not None:
            credits += value

    if not planned_numbers:
        return {
            "plannedCourseCount": 0,
            "plannedCredits": round(credits, 2),
            "difficulty": None,
            "exams": None,
        }

    planned_mean, rated = _mean_difficulty(planned_numbers, ratings)
    completed_numbers = [
        number
        for raw in completed_course_numbers
        if (number := canonical_course_number(raw)) is not None
    ]
    completed_mean, _ = _mean_difficulty(completed_numbers, ratings)

    difficulty = None
    if planned_mean is not None:
        heavier = (
            None
            if completed_mean is None
            else planned_mean - completed_mean >= HEAVIER_THAN_USUAL_MARGIN
        )
        difficulty = {
            "plannedMean": round(planned_mean, 2),
            "yourCompletedMean": None if completed_mean is None else round(completed_mean, 2),
            "heavierThanUsual": heavier,
            # 31% of the catalog is rated; a mean over one of four courses is
            # not a description of the semester.
            "ratedCourses": rated,
            "plannedCourses": len(planned_numbers),
            "scaleMin": 1,
            "scaleMax": 5,
        }

    return {
        "plannedCourseCount": len(planned_numbers),
        "plannedCredits": round(credits, 2),
        "difficulty": difficulty,
        "exams": _exam_summary(planned_numbers, exams_by_course),
    }
