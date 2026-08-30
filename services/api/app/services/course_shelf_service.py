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

import asyncio
from typing import Any, Iterable

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.course_deferral import (
    build_dependent_index,
    describe_deferral,
    next_offering,
)
from app.planning.course_ranking import (
    diversify_by_faculty,
    prior_mean_rating,
    rank_candidates,
)
from app.planning.course_notes import requires_manual_registration
from app.planning.course_shelves import MANDATORY, OPEN, build_course_shelves
from app.planning.course_unlocking import build_unlock_index
from app.planning.draft_summary import build_draft_summary
from app.planning.exam_summary import exams_from_offering
from app.planning.prerequisite_expression import (
    PrerequisiteParseError,
    is_satisfied_by,
    missing_alternatives,
    parse_prerequisite_expression,
)
from app.planning.prerequisite_resolver import canonical_course_number
from app.curriculum.cross_track_equivalence import equivalent_course_numbers
from app.planning.schedule_fit import (
    build_occupied_schedule,
    can_schedule_alongside,
    retake_clashes,
)
from app.planning.semester_codes import plan_semester_to_offering_keys
from app.planning.student_affinity import build_elective_affinity, describe_readiness
from app.planning.study_level import allowed_frameworks, is_appropriate_level
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
from app.repositories.completed_course_repository import (
    find_all_completed_courses_by_user_id,
)
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.semester_plan_suggestion_service import load_exact_term_offerings

LATER_COURSES_LIMIT = 12
"""Courses shown in a row's "not this term" group.

Over half of curated rows surface two courses or fewer, almost entirely because
pool courses do not run every term. Removing them outright leaves a row with
nothing in it and takes away the one thing that would let a student plan a term
ahead; keeping them, clearly separated and dated, gives the row its substance
back without pretending they are actionable now.
"""

UNLOCK_PREVIEW_LIMIT = 6
"""Course numbers listed on a card alongside the unlock count.

Reported rather than ranked on. A third of the term's courses unlock at least
one thing and the median unlocks exactly one, so as a rank key it would fire
constantly while separating almost nothing -- and how much a future option is
worth depends on how many semesters the student has left to spend, which they
know and the system does not.
"""

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


def _is_offered_this_term(number: str, offered_numbers: set[str]) -> bool:
    return bool(equivalent_course_numbers(number) & offered_numbers)


def _expand_numbers(numbers: Iterable[str]) -> set[str]:
    expanded: set[str] = set()
    for number in numbers:
        expanded |= equivalent_course_numbers(number)
    return expanded


CONFLICT_CHECK_HEAD = OPEN_SHELF_LIMIT * 3
"""How far down an open row's ranking a timetable is fetched.

The row shows `OPEN_SHELF_LIMIT`; checking three times that leaves room for
clashing entries to drop out and the row still to fill.
"""


def _card(
    course: dict[str, Any],
    *,
    offered_numbers: set[str],
    completed_numbers: set[str],
    signals: dict[str, dict[str, Any]],
    grades: dict[str, float],
    unlock_index: dict[str, frozenset[str]],
    retake_clash: bool = False,
) -> dict[str, Any]:
    number = str(course.get("courseNumber") or "")
    return {
        # The planner adds courses by catalog id, not by number.
        "id": str(course["_id"]) if course.get("_id") is not None else None,
        "courseNumber": number,
        "title": course.get("title"),
        "titleHebrew": course.get("titleHebrew"),
        "credits": course.get("credits"),
        "faculty": course.get("faculty"),
        "offeredThisTerm": _is_offered_this_term(number, offered_numbers),
        "eligibility": _eligibility(course.get("prerequisitesText"), completed_numbers),
        "signal": signals.get(number),
        # How the student did in this course's OWN prerequisites -- reported,
        # never ranked on. See `student_affinity`.
        "readiness": describe_readiness(course.get("prerequisitesText"), grades=grades),
        # What taking this would open next term, among courses that could still
        # count toward something the student needs.
        "unlocks": {
            "count": len(opened := unlock_index.get(number, frozenset())),
            "courseNumbers": sorted(opened)[:UNLOCK_PREVIEW_LIMIT],
        },
        # Its retake falls on a planned course's retake. Not a reason to hide
        # the course -- it only bites a student who fails both sittings.
        "retakeClashesWithDraft": retake_clash,
        # Cannot be enrolled through the normal system: the student must email
        # the lecturer with their transcript and be accepted.
        "requiresManualRegistration": requires_manual_registration(course.get("notes")),
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
    # Deliberately NOT `load_planning_context`. It computes a full graduation
    # progress of its own -- 2.9s of the endpoint's 7.4s -- and this service
    # then discards it in favour of `get_graduation_progress_for_user`, whose
    # numbers match the Progress page. Only three of its outputs are wanted, and
    # each is a single query.
    profile = await find_student_profile_by_user_id(database, user_id)
    if not profile:
        return {"status": "profile_not_found"}
    degree_id = profile.get("degreeId")
    if not degree_id:
        return {"status": "degree_not_selected"}
    degree_program = await catalog_repository.find_degree_program_by_id(
        database, str(degree_id)
    )
    if not degree_program:
        return {"status": "degree_not_found"}

    pool_documents, completed_records = await asyncio.gather(
        catalog_repository.list_course_pools_for_program(
            database, str(degree_program["programCode"])
        ),
        find_all_completed_courses_by_user_id(database, user_id),
    )
    context = {
        "status": "ok",
        "profile": profile,
        "poolDocuments": pool_documents,
        "completedCourseRecords": completed_records,
    }

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
    # These four do not depend on each other, and awaiting them in sequence was
    # most of the endpoint's wall time.
    (
        progress_result,
        offered_numbers,
        prerequisite_texts,
        statistics_records,
    ) = await asyncio.gather(
        get_graduation_progress_for_user(database, user_id),
        catalog_repository.list_course_numbers_with_semester_offerings(
            database, academic_year=academic_year, semester_code=term_semester_code
        ),
        catalog_repository.list_course_prerequisite_texts(database),
        find_completed_courses_for_statistics(database),
    )
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

    # An "anything counts" row draws on the term itself, minus everything a more
    # specific row already claims -- a course shown twice invites planning it twice.
    claimed = {number for shelf in shelves for number in shelf.course_numbers}
    open_candidates = sorted(
        offered_numbers
        - _expand_numbers(claimed)
        - _expand_numbers(completed_numbers)
        - _expand_numbers(planned_numbers)
    )

    needed_numbers = sorted(claimed | set(open_candidates))
    lookup_numbers = sorted(_expand_numbers(needed_numbers))
    (
        course_documents,
        ratings,
        published,
        completed_documents,
        history_ratings,
        planned_documents,
        planned_ratings,
    ) = await asyncio.gather(
        catalog_repository.find_planning_courses_by_numbers(database, lookup_numbers),
        catalog_repository.find_course_ratings(database, lookup_numbers),
        catalog_repository.find_course_grade_stats(database, lookup_numbers),
        # Their own past choices and their draft are both outside the candidate
        # set, so each needs its own lookup -- see the notes at the use sites.
        catalog_repository.find_planning_courses_by_numbers(
            database, sorted(completed_numbers)
        ),
        catalog_repository.find_course_ratings(database, sorted(completed_numbers)),
        catalog_repository.find_planning_courses_by_numbers(
            database, sorted(planned_numbers)
        ),
        catalog_repository.find_course_ratings(database, sorted(planned_numbers)),
    )
    courses_by_number: dict[str, dict[str, Any]] = {}
    for document in course_documents:
        catalog_number = str(document.get("courseNumber") or "")
        for alias in equivalent_course_numbers(catalog_number) or {catalog_number}:
            courses_by_number.setdefault(alias, document)
    outcomes = build_course_outcomes(statistics_records)
    signals: dict[str, dict[str, Any]] = {}
    for number in lookup_numbers:
        if number not in outcomes and number not in ratings and number not in published:
            continue
        payload = CourseSignal(
            course_number=number,
            outcome=outcomes.get(number),
            rating=ratings.get(number),
            published=published.get(number),
        ).as_public_dict()
        for alias in equivalent_course_numbers(number) or {number}:
            signals.setdefault(alias, payload)

    dependent_index = build_dependent_index(prerequisite_texts)

    # What the student could actually add to THIS semester. On a choice row a
    # course that is not offered, or whose prerequisites are unmet, is not a
    # weaker suggestion -- it is not a suggestion at all, so it is filtered out
    # rather than ranked low. The row still reports how many it dropped.
    # A course that shares credit with one the student already has or has
    # planned contributes ZERO toward the requirement, while the row would
    # still advertise it as progress.
    overlap_conflicts = build_catalog_overlap_conflicts(course_documents)
    already_credited = completed_numbers | planned_numbers

    # `studyFramework` is set on every catalog course and was consulted nowhere:
    # 197 graduate courses sat in this term's undergraduate candidate pool, 108
    # of them stating no prerequisites at all, so eligibility did not stop them
    # either. They stayed off the rows only because the cap and the ranking
    # happened to bury them.
    allowed_levels = allowed_frameworks((context["profile"] or {}).get("programType"))

    def _wrong_degree_level(number: str) -> bool:
        return not is_appropriate_level(
            (courses_by_number.get(number) or {}).get("studyFramework"),
            allowed=allowed_levels,
        )

    def _gives_no_additional_credit(number: str) -> bool:
        return bool(conflicts_for_course(number, overlap_conflicts) & already_credited)

    selectable = {
        number
        for number in needed_numbers
        if _is_offered_this_term(number, offered_numbers)
        and not _wrong_degree_level(number)
        and not _gives_no_additional_credit(number)
        and _eligibility(
            (courses_by_number.get(number) or {}).get("prerequisitesText"),
            completed_numbers,
        )["status"]
        != "missing_prerequisites"
    }

    # One prior for the whole request, so a course cannot score differently in
    # two rows of the same screen.

    # Restricted to courses that could still advance an unsatisfied requirement:
    # unlocking something that counts toward nothing is worth nothing.
    unlock_index = build_unlock_index(
        course_documents, completed=completed_numbers, relevant=needed_numbers
    )

    prior_mean = prior_mean_rating(ratings)
    grades = {
        number: float(grade)
        for record in context["completedCourseRecords"]
        if (number := canonical_course_number(record.get("courseNumber"))) is not None
        and isinstance(grade := record.get("grade"), (int, float))
        and not isinstance(grade, bool)
        and grade > 0
    }
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

    prepared: list[dict[str, Any]] = []
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
                    not _is_offered_this_term(number, offered_numbers),
                    -len(dependent_index.get(number, frozenset())),
                    number,
                ),
            )
            candidate_count = len(shelf.course_numbers)
            dropped_not_offered = 0
            dropped_ineligible = 0
            dropped_no_credit = 0
            dropped_wrong_level = 0
            later_numbers = []
        else:
            pool = list(open_candidates) if shelf.kind == OPEN else list(shelf.course_numbers)
            candidate_count = len(pool)
            selectable_here = [number for number in pool if number in selectable]
            dropped_not_offered = sum(
                1 for number in pool if not _is_offered_this_term(number, offered_numbers)
            )
            dropped_no_credit = sum(
                1
                for number in pool
                if _is_offered_this_term(number, offered_numbers)
                and not _wrong_degree_level(number)
                and _gives_no_additional_credit(number)
            )
            dropped_wrong_level = sum(
                1
                for number in pool
                if _is_offered_this_term(number, offered_numbers) and _wrong_degree_level(number)
            )
            later_numbers = [
                number
                for number in pool
                if not _is_offered_this_term(number, offered_numbers) and number in courses_by_number
            ]
            dropped_ineligible = (
                len(pool)
                - len(selectable_here)
                - dropped_not_offered
                - dropped_no_credit
                - dropped_wrong_level
            )

            ranked = rank_candidates(
                [
                    courses_by_number[number]
                    for number in selectable_here
                    if number in courses_by_number
                ],
                ratings=ratings,
                credits_remaining_overall=credits_remaining_overall,
                credits_remaining_in_bucket=shelf.credits_remaining,
                prior_mean=prior_mean,
                faculty_affinity=faculty_affinity,
                # Only for a curated pool. An "anything counts" row is the whole
                # term, so "unlocks others on this shelf" would degenerate into
                # "gates anything at all" -- which is not a reason to take a
                # free elective now, and inflated the urgency count for it.
                unlocks_within_shelf=(
                    {}
                    if shelf.kind == OPEN
                    else _unlocks_within(pool, courses_by_number=courses_by_number)
                ),
            )
            reasons_by_number = {entry.course_number: entry.reasons for entry in ranked}
            ordered_numbers = [entry.course_number for entry in ranked]

        prepared.append(
            {
                "shelf": shelf,
                "ordered": ordered_numbers,
                "reasons": reasons_by_number,
                "candidateCount": candidate_count,
                "notOffered": dropped_not_offered,
                "ineligible": dropped_ineligible,
                "noCredit": dropped_no_credit,
                "wrongLevel": dropped_wrong_level,
                "later": later_numbers,
            }
        )

    # Only courses that could actually be rendered need a timetable. A curated
    # row is small enough to check whole; an open row draws on the term and
    # shows `OPEN_SHELF_LIMIT`, so a head of its ranking is checked with room
    # for clashing entries to drop out and the row still to fill. Fetching all
    # ~1,256 was the slowest query in the request, and it could not be narrowed
    # until the ranking moved ahead of it.
    candidate_offerings: dict[str, dict[str, Any]] = {}
    occupied = build_occupied_schedule({}, planned_course_numbers=())
    if planned_numbers:
        checkable: set[str] = set(planned_numbers)
        for entry in prepared:
            ordered = entry["ordered"]
            checkable |= set(
                ordered[:CONFLICT_CHECK_HEAD] if entry["shelf"].kind == OPEN else ordered
            )
        candidate_offerings = await load_exact_term_offerings(
            database,
            sorted(checkable),
            academic_year=academic_year,
            semester_code=term_semester_code,
        )
        occupied = build_occupied_schedule(
            candidate_offerings, planned_course_numbers=planned_numbers
        )

    # Both "anything counts" rows draw on the whole term, so the same course
    # surfaced on each -- but taking it can only ever advance one requirement.
    # The first row to show it claims it, the way curated rows already claim
    # theirs out of the open pool.
    claimed_by_open: set[str] = set()

    payload_shelves: list[dict[str, Any]] = []
    for entry in prepared:
        shelf = entry["shelf"]
        reasons_by_number = entry["reasons"]
        ordered_numbers = entry["ordered"]
        candidate_count = entry["candidateCount"]
        dropped_not_offered = entry["notOffered"]
        dropped_ineligible = entry["ineligible"]
        dropped_no_credit = entry["noCredit"]
        dropped_wrong_level = entry["wrongLevel"]
        later_numbers = entry["later"]
        dropped_conflicting = 0

        if shelf.kind != MANDATORY:
            if shelf.kind == OPEN:
                ordered_numbers = [
                    number for number in ordered_numbers if number not in claimed_by_open
                ]
                # Never render past the window whose timetables were fetched.
                # `diversify_by_faculty` scans in order until the row is full,
                # so a run of same-faculty courses could otherwise carry it
                # beyond the checked head and show an unchecked course.
                ordered_numbers = ordered_numbers[:CONFLICT_CHECK_HEAD]
            # A course that cannot coexist with the draft is not a weaker
            # suggestion either -- same reason "not offered" is filtered.
            kept = [
                number
                for number in ordered_numbers
                if can_schedule_alongside(
                    candidate_offerings.get(number),
                    course_number=number,
                    occupied=occupied,
                )
            ]
            dropped_conflicting = len(ordered_numbers) - len(kept)
            ordered_numbers = kept

            if shelf.kind == OPEN:
                ordered_numbers = [
                    course["courseNumber"]
                    for course in diversify_by_faculty(
                        # `.get`: a number that normalises differently from its
                        # catalog key would otherwise raise here rather than
                        # simply not being shown.
                        [
                            courses_by_number[number]
                            for number in ordered_numbers
                            if number in courses_by_number
                        ],
                        limit=OPEN_SHELF_LIMIT,
                        per_faculty=OPEN_SHELF_PER_FACULTY,
                    )
                ]

        if shelf.kind == OPEN:
            claimed_by_open |= set(ordered_numbers)

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
                        "id": None,
                        "courseNumber": number,
                        "title": None,
                        "credits": None,
                        "offeredThisTerm": _is_offered_this_term(number, offered_numbers),
                        "eligibility": {"status": "unknown", "missingOptions": []},
                        "signal": signals.get(number),
                        "readiness": None,
                        "unlocks": {"count": 0, "courseNumbers": []},
                        "retakeClashesWithDraft": False,
                        "requiresManualRegistration": False,
                        "catalogKnown": False,
                        "reasons": [],
                    }
                )
                continue
            display = dict(course)
            display["courseNumber"] = number
            card = _card(
                display,
                offered_numbers=offered_numbers,
                completed_numbers=completed_numbers,
                signals=signals,
                grades=grades,
                unlock_index=unlock_index,
                retake_clash=retake_clashes(
                    candidate_offerings.get(number),
                    course_number=number,
                    occupied=occupied,
                ),
            )
            card["reasons"] = list(reasons_by_number.get(number, ()))
            if shelf.kind == MANDATORY:
                card["deferral"] = describe_deferral(
                    course,
                    after=(academic_year, term_semester_code),
                    dependent_index=dependent_index,
                )
            cards.append(card)

        # Not actionable this term, but the row is about them too: a chain with
        # three courses running and twelve waiting is a different thing from a
        # chain with three courses in it.
        payload = shelf.as_public_dict()
        payload["laterCourses"] = [
            {
                "courseNumber": number,
                "title": courses_by_number[number].get("title"),
                "credits": courses_by_number[number].get("credits"),
                "nextOffering": (
                    {"academicYear": upcoming[0], "semesterCode": upcoming[1]}
                    if (
                        upcoming := next_offering(
                            courses_by_number[number].get("semestersOffered"),
                            after=(academic_year, term_semester_code),
                        )
                    )
                    is not None
                    else None
                ),
            }
            for number in later_numbers[:LATER_COURSES_LIMIT]
        ]
        payload["courses"] = cards
        payload["candidateCount"] = candidate_count
        payload["notOfferedCount"] = dropped_not_offered
        payload["ineligibleCount"] = dropped_ineligible
        payload["noAdditionalCreditCount"] = dropped_no_credit
        payload["conflictsWithDraftCount"] = dropped_conflicting
        payload["wrongDegreeLevelCount"] = dropped_wrong_level
        # 11 of 14 real students have at least one row with nothing in it --
        # small specialised pools they cannot draw from this term. The row must
        # still appear, because the requirement is real and unmet, so it says
        # why instead of rendering as an empty carousel.
        payload["emptyReason"] = (
            None
            if cards
            else "pool_exhausted"
            if candidate_count == 0
            else "none_offered_this_term"
            if dropped_not_offered == candidate_count
            else "none_available_to_you"
        )
        payload_shelves.append(payload)

    draft_summary = build_draft_summary(
        planned_documents,
        ratings={**history_ratings, **ratings, **planned_ratings},
        completed_course_numbers=completed_numbers,
        exams_by_course={
            number: [
                exam["date"]
                for exam in exams_from_offering(
                    candidate_offerings.get(number), course_number=number, course_name=""
                )
                if exam.get("date")
            ]
            for number in planned_numbers
        },
    )

    return {
        "status": "ok",
        "semesterCode": semester_code,
        "shelves": payload_shelves,
        "draftSummary": draft_summary,
    }
