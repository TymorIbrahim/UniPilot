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
what previous students scored and thought, and the row is ordered by
`course_ranking.rank_candidates` -- structural urgency first, then evidence-
weighted opinion, then what this student has shown interest in.

An `open` row -- a credit bucket that accepts anything -- has no pool to draw
from, so its candidates are the term's offerings minus everything already
completed, planned, or claimed by a more specific row. That is upward of a
thousand courses, so it is ranked and capped; the row reports the true total
so the count is not mistaken for the whole field.
"""

from __future__ import annotations

from typing import Any, Iterable

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.course_deferral import build_dependent_index, describe_deferral
from app.planning.course_ranking import (
    diversify_by_faculty,
    prior_mean_rating,
    rank_candidates,
)
from app.planning.course_shelves import MANDATORY, OPEN, build_course_shelves
from app.planning.prerequisite_expression import (
    PrerequisiteParseError,
    is_satisfied_by,
    missing_alternatives,
    parse_prerequisite_expression,
)
from app.planning.prerequisite_resolver import canonical_course_number
from app.planning.schedule_fit import build_occupied_schedule, can_schedule_alongside
from app.planning.semester_codes import plan_semester_to_offering_keys
from app.planning.student_affinity import build_elective_affinity, describe_readiness
from app.repositories import catalog_repository
from app.repositories.completed_course_repository import (
    find_completed_courses_for_statistics,
)
from app.planning.prerequisite_expression import course_numbers as expression_course_numbers
from app.services.catalog_overlap_groups import (
    build_catalog_overlap_conflicts,
    conflicts_for_course,
)
from app.services.course_outcome_stats import CourseSignal, build_course_outcomes
from app.services.graduation_progress_service import get_graduation_progress_for_user
from app.services.semester_plan_service import load_planning_context
from app.services.semester_plan_suggestion_service import load_exact_term_offerings

OPEN_SHELF_PER_FACULTY = 3
"""Most courses one faculty may contribute to an "anything counts" row.

Six of the eight best-scoring courses in the catalog come from two faculties,
so without a cap the widest row in the product is the narrowest one on screen.
"""

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


def _unlocks_within(
    course_numbers_on_shelf: Iterable[str],
    *,
    courses_by_number: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """How many OTHER courses on this shelf list each one as a prerequisite.

    Restricted to the shelf on purpose: the question is how to order the
    courses the student is choosing between, not how much the course gates
    across the whole catalog.
    """
    members = set(course_numbers_on_shelf)
    unlocks: dict[str, int] = {}
    for number in members:
        try:
            expression = parse_prerequisite_expression(
                (courses_by_number.get(number) or {}).get("prerequisitesText")
            )
        except PrerequisiteParseError:
            continue
        for prerequisite in expression_course_numbers(expression) & members:
            unlocks[prerequisite] = unlocks.get(prerequisite, 0) + 1
    return unlocks


def _card(
    course: dict[str, Any],
    *,
    offered_numbers: set[str],
    completed_numbers: set[str],
    signals: dict[str, dict[str, Any]],
    grades: dict[str, float],
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
        # How the student did in this course's OWN prerequisites -- reported,
        # never ranked on. See `student_affinity`.
        "readiness": describe_readiness(course.get("prerequisitesText"), grades=grades),
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
        planned_course_numbers=planned_numbers,
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

    # What the student could actually add to THIS semester. On a choice row a
    # course that is not offered, or whose prerequisites are unmet, is not a
    # weaker suggestion -- it is not a suggestion at all, so it is filtered out
    # rather than ranked low. The row still reports how many it dropped.
    # A course that shares credit with one the student already has or has
    # planned contributes ZERO toward the requirement, while the row would
    # still advertise it as progress.
    overlap_conflicts = build_catalog_overlap_conflicts(course_documents)
    already_credited = completed_numbers | planned_numbers

    def _gives_no_additional_credit(number: str) -> bool:
        return bool(conflicts_for_course(number, overlap_conflicts) & already_credited)

    selectable = {
        number
        for number in needed_numbers
        if number in offered_numbers
        and not _gives_no_additional_credit(number)
        and _eligibility(
            (courses_by_number.get(number) or {}).get("prerequisitesText"),
            completed_numbers,
        )["status"]
        != "missing_prerequisites"
    }

    # One prior for the whole request, so a course cannot score differently in
    # two rows of the same screen.

    prior_mean = prior_mean_rating(ratings)
    grades = {
        number: float(grade)
        for record in context["completedCourseRecords"]
        if (number := canonical_course_number(record.get("courseNumber"))) is not None
        and isinstance(grade := record.get("grade"), (int, float))
        and not isinstance(grade, bool)
        and grade > 0
    }
    # Their OWN past choices, which are by definition not candidates -- so
    # their faculties have to be looked up separately. Reusing
    # `courses_by_number` here silently yields an empty affinity.
    completed_documents = await catalog_repository.find_courses_by_numbers(
        database, sorted(completed_numbers)
    )
    faculty_affinity = build_elective_affinity(
        requirement_progress,
        faculties_by_number={
            str(document.get("courseNumber")): document.get("faculty")
            for document in completed_documents
        },
    )
    credits_remaining_overall = float(
        (progress_result.get("progress") or {}).get("creditsRemaining") or 0.0
    )

    # What the draft semester already commits. Loading offerings is only worth
    # it once something is planned -- an empty draft clashes with nothing.
    occupied = build_occupied_schedule({}, planned_course_numbers=())
    candidate_offerings: dict[str, dict[str, Any]] = {}
    if planned_numbers:
        # NOT `list_offerings_for_courses_in_semester`: that returns a summary
        # (slot types, instructors) with no `scheduleGroups` or `examDates`, so
        # every conflict check silently passed.
        candidate_offerings = await load_exact_term_offerings(
            database,
            sorted(planned_numbers | set(needed_numbers)),
            academic_year=academic_year,
            semester_code=term_semester_code,
        )
        occupied = build_occupied_schedule(
            candidate_offerings, planned_course_numbers=planned_numbers
        )

    payload_shelves: list[dict[str, Any]] = []
    for shelf in shelves:
        reasons_by_number: dict[str, tuple[str, ...]] = {}

        if shelf.kind == MANDATORY:
            # These must all be taken eventually, so none are filtered. Order by
            # what can be acted on now, then by how much each one gates: a
            # course that is not offered this term cannot be scheduled into it,
            # whatever else is true of it.
            ordered_numbers = sorted(
                shelf.course_numbers,
                key=lambda number: (
                    number not in offered_numbers,
                    -len(dependent_index.get(number, frozenset())),
                    number,
                ),
            )
            candidate_count = len(shelf.course_numbers)
            dropped_not_offered = 0
            dropped_ineligible = 0
            dropped_no_credit = 0
            dropped_conflicting = 0
        else:
            pool = list(open_candidates) if shelf.kind == OPEN else list(shelf.course_numbers)
            candidate_count = len(pool)
            selectable_here = [number for number in pool if number in selectable]
            # A course that cannot coexist with the draft is not a weaker
            # suggestion either -- same reason "not offered" is filtered.
            actionable = [
                number
                for number in selectable_here
                if can_schedule_alongside(
                    candidate_offerings.get(number),
                    course_number=number,
                    occupied=occupied,
                )
            ]
            dropped_not_offered = sum(
                1 for number in pool if number not in offered_numbers
            )
            dropped_no_credit = sum(
                1
                for number in pool
                if number in offered_numbers and _gives_no_additional_credit(number)
            )
            dropped_conflicting = len(selectable_here) - len(actionable)
            dropped_ineligible = (
                len(pool)
                - len(selectable_here)
                - dropped_not_offered
                - dropped_no_credit
            )

            ranked = rank_candidates(
                [courses_by_number[number] for number in actionable if number in courses_by_number],
                ratings=ratings,
                credits_remaining_overall=credits_remaining_overall,
                credits_remaining_in_bucket=shelf.credits_remaining,
                prior_mean=prior_mean,
                faculty_affinity=faculty_affinity,
                unlocks_within_shelf=_unlocks_within(
                    pool, courses_by_number=courses_by_number
                ),
            )
            reasons_by_number = {entry.course_number: entry.reasons for entry in ranked}
            ordered_numbers = [entry.course_number for entry in ranked]

            if shelf.kind == OPEN:
                ordered_numbers = [
                    course["courseNumber"]
                    for course in diversify_by_faculty(
                        [courses_by_number[number] for number in ordered_numbers],
                        limit=OPEN_SHELF_LIMIT,
                        per_faculty=OPEN_SHELF_PER_FACULTY,
                    )
                ]

        cards = []
        for number in ordered_numbers:
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
                        "reasons": [],
                    }
                )
                continue
            card = _card(
                course,
                offered_numbers=offered_numbers,
                completed_numbers=completed_numbers,
                signals=signals,
                grades=grades,
            )
            card["reasons"] = list(reasons_by_number.get(number, ()))
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
        payload["notOfferedCount"] = dropped_not_offered
        payload["ineligibleCount"] = dropped_ineligible
        payload["noAdditionalCreditCount"] = dropped_no_credit
        payload["conflictsWithDraftCount"] = dropped_conflicting
        payload_shelves.append(payload)

    return {
        "status": "ok",
        "semesterCode": semester_code,
        "shelves": payload_shelves,
    }
