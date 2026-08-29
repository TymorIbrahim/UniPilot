"""Assemble the browsable planner's rows for one student and one term.

This is the read side of manual semester planning: not "here is a plan we made
for you" but "here is what is still open to you, grouped by what it counts
toward". `course_shelves` decides the rows; this service fills them with the
courses the term actually offers and the facts a student needs to choose.

What a card carries depends on the row, because the decision does
--------------------------------------------------------------
On a `mandatory` row the student is choosing *when*, not whether, so the card
carries the cost of postponing: when the course next runs, and how much waits
on it (`course_deferral`).

On a `pool` or `open` row the choice is genuinely free, so the card carries
what previous students scored and thought, and the row is ordered by the
latter (`rank_choice_courses`).

An `open` row -- a credit bucket that accepts anything -- has no pool to draw
from, so its candidates are the term's offerings minus everything already
completed, planned, or claimed by a more specific row. That is upward of a
thousand courses, so it is ranked and capped; the row reports the true total
so the count is not mistaken for the whole field.
"""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.course_deferral import build_dependent_index, describe_deferral
from app.planning.course_shelves import MANDATORY, OPEN, build_course_shelves, rank_choice_courses
from app.planning.prerequisite_expression import (
    PrerequisiteParseError,
    is_satisfied_by,
    missing_alternatives,
    parse_prerequisite_expression,
)
from app.planning.prerequisite_resolver import canonical_course_number
from app.planning.semester_codes import plan_semester_to_offering_keys
from app.repositories import catalog_repository
from app.repositories.completed_course_repository import (
    find_completed_courses_for_statistics,
)
from app.services.course_outcome_stats import CourseSignal, build_course_outcomes
from app.services.graduation_progress_service import get_graduation_progress_for_user
from app.services.semester_plan_service import load_planning_context

OPEN_SHELF_LIMIT = 24
"""Courses shown on an "anything counts" row.

The candidate set there is the term's entire offering list -- about 1,250
courses in a winter term -- which is a ranking problem, not a list. The row
reports `candidateCount` alongside so the cap is visible rather than implied.
"""


def _eligibility(
    prerequisites_text: str | None,
    completed_numbers: set[str],
) -> dict[str, Any]:
    """Whether the student may take the course, read from the boolean rule.

    Text the grammar does not cover is reported as unknown rather than guessed
    either way -- see `prerequisite_expression`.
    """
    try:
        expression = parse_prerequisite_expression(prerequisites_text)
    except PrerequisiteParseError:
        return {"status": "unknown", "missingOptions": []}

    if expression is None:
        return {"status": "eligible", "missingOptions": []}
    if is_satisfied_by(expression, completed_numbers):
        return {"status": "eligible", "missingOptions": []}
    return {
        "status": "missing_prerequisites",
        "missingOptions": [
            sorted(option) for option in missing_alternatives(expression, completed_numbers)
        ],
    }


def _card(
    course: dict[str, Any],
    *,
    offered_numbers: set[str],
    completed_numbers: set[str],
    signals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    number = str(course.get("courseNumber") or "")
    return {
        "courseNumber": number,
        "title": course.get("title"),
        "titleHebrew": course.get("titleHebrew"),
        "credits": course.get("credits"),
        "faculty": course.get("faculty"),
        "offeredThisTerm": number in offered_numbers,
        "eligibility": _eligibility(course.get("prerequisitesText"), completed_numbers),
        "signal": signals.get(number),
        "catalogKnown": True,
    }


async def build_course_shelves_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    semester_code: str,
    existing_planned_courses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The rows a student should see when building `semester_code` by hand."""
    context = await load_planning_context(database, user_id)
    if context["status"] != "ok":
        return context

    offering_keys = plan_semester_to_offering_keys(semester_code)
    if offering_keys is None:
        return {"status": "validation_error", "errors": ["Invalid semesterCode"]}
    academic_year, term_semester_code = offering_keys

    completed_numbers = {
        number
        for record in context["completedCourseRecords"]
        if (number := canonical_course_number(record.get("courseNumber"))) is not None
    }
    planned_numbers = {
        number
        for course in existing_planned_courses or []
        if course.get("isActive", True) is not False
        and (number := canonical_course_number(course.get("courseNumber"))) is not None
    }

    # Deliberately NOT `context["graduationProgress"]`. `load_planning_context`
    # computes a thinner progress for its own candidate selection -- it resolves
    # catalog documents only for completed courses -- and its credit remainders
    # differ from the ones the Progress page shows. A row header that
    # contradicts the progress screen is worse than no row header.
    progress_result = await get_graduation_progress_for_user(database, user_id)
    if progress_result.get("status") != "ok":
        return progress_result
    requirement_progress = (progress_result.get("progress") or {}).get(
        "requirementProgress"
    ) or []

    shelves = build_course_shelves(
        requirement_progress=requirement_progress,
        pool_documents=context["poolDocuments"],
        completed_course_numbers=completed_numbers,
    )

    offered_numbers = await catalog_repository.list_course_numbers_with_semester_offerings(
        database, academic_year=academic_year, semester_code=term_semester_code
    )

    # An "anything counts" row draws on the term itself, minus everything a more
    # specific row already claims -- a course shown twice invites planning it twice.
    claimed = {number for shelf in shelves for number in shelf.course_numbers}
    open_candidates = sorted(
        offered_numbers - claimed - completed_numbers - planned_numbers
    )

    needed_numbers = sorted(claimed | set(open_candidates))
    course_documents = await catalog_repository.find_courses_by_numbers(database, needed_numbers)
    courses_by_number = {
        str(document.get("courseNumber")): document for document in course_documents
    }

    ratings = await catalog_repository.find_course_ratings(database, needed_numbers)
    published = await catalog_repository.find_course_grade_stats(database, needed_numbers)
    outcomes = build_course_outcomes(await find_completed_courses_for_statistics(database))
    signals = {
        number: CourseSignal(
            course_number=number,
            outcome=outcomes.get(number),
            rating=ratings.get(number),
            published=published.get(number),
        ).as_public_dict()
        for number in needed_numbers
        if number in outcomes or number in ratings or number in published
    }

    dependent_index = build_dependent_index(
        await catalog_repository.list_course_prerequisite_texts(database)
    )

    # What the student could actually add to THIS semester. A five-star course
    # that is not offered, or whose prerequisites are unmet, is not a better
    # suggestion than a three-star course they can register for today.
    selectable = {
        number
        for number in needed_numbers
        if number in offered_numbers
        and _eligibility(
            (courses_by_number.get(number) or {}).get("prerequisitesText"),
            completed_numbers,
        )["status"]
        != "missing_prerequisites"
    }

    payload_shelves: list[dict[str, Any]] = []
    for shelf in shelves:
        if shelf.kind == OPEN:
            candidate_numbers = rank_choice_courses(
                open_candidates, ratings=ratings, selectable=selectable
            )
            candidate_count = len(candidate_numbers)
            candidate_numbers = candidate_numbers[:OPEN_SHELF_LIMIT]
        elif shelf.kind == MANDATORY:
            # Order by what deferring costs: the course that runs least often,
            # and gates the most, is the one to schedule first.
            candidate_numbers = tuple(
                sorted(
                    shelf.course_numbers,
                    key=lambda number: (
                        -len(dependent_index.get(number, frozenset())),
                        number,
                    ),
                )
            )
            candidate_count = len(candidate_numbers)
        else:
            candidate_numbers = rank_choice_courses(
                shelf.course_numbers, ratings=ratings, selectable=selectable
            )
            candidate_count = len(candidate_numbers)

        cards = []
        for number in candidate_numbers:
            course = courses_by_number.get(number)
            if course is None:
                # A required course the catalog does not carry must still appear
                # on its row. Dropping it makes an outstanding obligation
                # disappear from the one screen meant to list them.
                if shelf.kind != MANDATORY:
                    continue
                cards.append(
                    {
                        "courseNumber": number,
                        "title": None,
                        "credits": None,
                        "offeredThisTerm": number in offered_numbers,
                        "eligibility": {"status": "unknown", "missingOptions": []},
                        "signal": signals.get(number),
                        "catalogKnown": False,
                    }
                )
                continue
            card = _card(
                course,
                offered_numbers=offered_numbers,
                completed_numbers=completed_numbers,
                signals=signals,
            )
            if shelf.kind == MANDATORY:
                card["deferral"] = describe_deferral(
                    course,
                    after=(academic_year, term_semester_code),
                    dependent_index=dependent_index,
                )
            cards.append(card)

        payload = shelf.as_public_dict()
        payload["courses"] = cards
        payload["candidateCount"] = candidate_count
        payload_shelves.append(payload)

    return {
        "status": "ok",
        "semesterCode": semester_code,
        "shelves": payload_shelves,
    }
