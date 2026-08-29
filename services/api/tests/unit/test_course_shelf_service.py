"""Unit tests for assembling the browsable planner's rows."""

from __future__ import annotations

import pytest

from app.services import course_shelf_service


@pytest.fixture
def stub(monkeypatch):
    """Patch every I/O boundary the service uses, with sane defaults."""

    state = {
        "requirementProgress": [],
        "poolDocuments": [],
        "completedCourseRecords": [],
        "offered": set(),
        "courses": [],
        "ratings": {},
        "published": {},
        "prerequisiteTexts": [],
        "offerings": {},
        "profile": {"programType": "BSc"},
    }

    async def _context(database, user_id):
        return {
            "status": "ok",
            "profile": state["profile"],
            "poolDocuments": state["poolDocuments"],
            "completedCourseRecords": state["completedCourseRecords"],
            "graduationProgress": {},
        }

    async def _progress(database, user_id):
        return {"status": "ok", "progress": {"requirementProgress": state["requirementProgress"]}}

    async def _offered(database, **kwargs):
        return state["offered"]

    async def _courses(database, numbers):
        wanted = set(numbers)
        return [c for c in state["courses"] if c["courseNumber"] in wanted]

    async def _ratings(database, numbers):
        wanted = set(numbers)
        return {n: r for n, r in state["ratings"].items() if n in wanted} or state["ratings"]

    async def _published(database, numbers):
        return state["published"]

    async def _prereq_texts(database):
        return state["prerequisiteTexts"]

    async def _term_offerings(database, numbers, **kwargs):  # noqa: D401
        return {n: o for n, o in state["offerings"].items() if n in set(numbers)}

    async def _statistics(database):
        return []

    monkeypatch.setattr(course_shelf_service, "load_planning_context", _context)
    monkeypatch.setattr(course_shelf_service, "get_graduation_progress_for_user", _progress)
    monkeypatch.setattr(course_shelf_service, "find_completed_courses_for_statistics", _statistics)
    monkeypatch.setattr(
        course_shelf_service.catalog_repository,
        "list_course_numbers_with_semester_offerings",
        _offered,
    )
    monkeypatch.setattr(course_shelf_service.catalog_repository, "find_courses_by_numbers", _courses)
    monkeypatch.setattr(course_shelf_service.catalog_repository, "find_course_ratings", _ratings)
    monkeypatch.setattr(
        course_shelf_service.catalog_repository, "find_course_grade_stats", _published
    )
    monkeypatch.setattr(
        course_shelf_service.catalog_repository, "list_course_prerequisite_texts", _prereq_texts
    )
    monkeypatch.setattr(
        course_shelf_service, "load_exact_term_offerings", _term_offerings
    )
    return state


def _course(number, *, offered=(200,), prerequisites_text=None, credits=3.0):
    return {
        "courseNumber": number,
        "title": f"Course {number}",
        "credits": credits,
        "semestersOffered": list(offered),
        "prerequisitesText": prerequisites_text,
    }


def _bucket(group_id, title, *, remaining=(), requirement_type="elective", credits_remaining=3.0):
    return {
        "requirementGroupId": group_id,
        "title": title,
        "status": "in_progress",
        "requirementType": requirement_type,
        "creditsRemaining": credits_remaining,
        "remainingCourses": [{"courseNumber": n} for n in remaining],
    }


async def _build(**kwargs):
    return await course_shelf_service.build_course_shelves_for_user(
        object(), "user-1", semester_code=kwargs.pop("semester_code", "2025-1"), **kwargs
    )


@pytest.mark.asyncio
async def test_an_invalid_semester_code_is_rejected(stub) -> None:
    result = await _build(semester_code="not-a-semester")

    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_a_failed_progress_computation_short_circuits(stub, monkeypatch) -> None:
    """Without progress there are no requirements, and a row list built from
    nothing would read as "you have nothing left to do"."""

    async def _failing(database, user_id):
        return {"status": "degree_required"}

    monkeypatch.setattr(course_shelf_service, "get_graduation_progress_for_user", _failing)

    assert (await _build())["status"] == "degree_required"


@pytest.mark.asyncio
async def test_a_mandatory_card_carries_the_cost_of_postponing_it(stub) -> None:
    stub["requirementProgress"] = [
        _bucket("p:core", "Required", remaining=("00940704",), requirement_type="core")
    ]
    stub["courses"] = [_course("00940704", offered=(200,))]
    stub["offered"] = {"00940704"}
    stub["prerequisiteTexts"] = [
        {"courseNumber": "00940999", "prerequisitesText": "00940704"},
    ]

    shelves = (await _build())["shelves"]

    card = shelves[0]["courses"][0]
    assert shelves[0]["kind"] == "mandatory"
    assert card["deferral"]["dependentCount"] == 1
    assert card["deferral"]["offeredOncePerYear"] is True
    assert card["deferral"]["nextOffering"] == {"academicYear": 2026, "semesterCode": 200}


@pytest.mark.asyncio
async def test_a_choice_card_carries_no_deferral_cost(stub) -> None:
    """The question on a menu is which, not when."""
    stub["requirementProgress"] = [_bucket("p:elective", "Electives", remaining=("00940704",))]
    stub["courses"] = [_course("00940704")]
    stub["offered"] = {"00940704"}

    card = (await _build())["shelves"][0]["courses"][0]

    assert "deferral" not in card


@pytest.mark.asyncio
async def test_a_required_course_absent_from_the_catalog_still_appears(stub) -> None:
    """Dropping it makes an outstanding obligation vanish from the one screen
    meant to list them."""
    stub["requirementProgress"] = [
        _bucket("p:core", "Required", remaining=("00960221",), requirement_type="core")
    ]
    stub["courses"] = []

    card = (await _build())["shelves"][0]["courses"][0]

    assert card["courseNumber"] == "00960221"
    assert card["catalogKnown"] is False
    assert card["eligibility"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_a_course_the_student_cannot_take_is_dropped_and_counted(stub) -> None:
    """On a choice row a course with unmet prerequisites is not a weaker
    suggestion, it is not a suggestion -- but the row still has to admit it
    dropped something, or the count reads as the whole pool."""
    stub["requirementProgress"] = [
        _bucket("p:elective", "Electives", remaining=("00940111", "00940222"))
    ]
    stub["courses"] = [
        _course("00940111", prerequisites_text="00949999"),  # not completed
        _course("00940222"),
    ]
    stub["offered"] = {"00940111", "00940222"}
    stub["ratings"] = {
        "00940111": {"meanGeneralRank": 5.0},
        "00940222": {"meanGeneralRank": 3.0},
    }

    shelf = (await _build())["shelves"][0]

    assert [c["courseNumber"] for c in shelf["courses"]] == ["00940222"]
    assert shelf["candidateCount"] == 2
    assert shelf["ineligibleCount"] == 1
    assert shelf["notOfferedCount"] == 0


@pytest.mark.asyncio
async def test_a_course_not_offered_this_term_is_dropped_from_a_choice_row(stub) -> None:
    stub["requirementProgress"] = [
        _bucket("p:elective", "Electives", remaining=("00940111", "00940222"))
    ]
    stub["courses"] = [_course("00940111"), _course("00940222")]
    stub["offered"] = {"00940222"}

    shelf = (await _build())["shelves"][0]

    assert [c["courseNumber"] for c in shelf["courses"]] == ["00940222"]
    assert shelf["notOfferedCount"] == 1


@pytest.mark.asyncio
async def test_a_required_course_not_offered_this_term_still_shows_but_sorts_last(stub) -> None:
    """It cannot be scheduled into this semester whatever else is true of it --
    but it is still outstanding, and the row exists to list what is."""
    stub["requirementProgress"] = [
        _bucket(
            "p:core", "Required", remaining=("00940111", "00940222"), requirement_type="core"
        )
    ]
    stub["courses"] = [_course("00940111"), _course("00940222")]
    stub["offered"] = {"00940222"}
    # 00940111 gates more, and would lead if being offered did not come first.
    stub["prerequisiteTexts"] = [
        {"courseNumber": "00949001", "prerequisitesText": "00940111"},
        {"courseNumber": "00949002", "prerequisitesText": "00940111"},
    ]

    shelf = (await _build())["shelves"][0]

    assert [c["courseNumber"] for c in shelf["courses"]] == ["00940222", "00940111"]
    assert shelf["courses"][1]["offeredThisTerm"] is False


@pytest.mark.asyncio
async def test_an_open_row_is_capped_but_reports_the_true_total(stub) -> None:
    """"Anything counts" draws on the whole term. The cap must be visible, or
    the row reads as the entire field of choice."""
    numbers = [f"009401{index:02d}" for index in range(40)]
    stub["requirementProgress"] = [
        _bucket("p:free", "Free electives", credits_remaining=2.0)
    ]
    stub["courses"] = [_course(number) for number in numbers]
    stub["offered"] = set(numbers)

    shelf = (await _build())["shelves"][0]

    assert shelf["kind"] == "open"
    assert len(shelf["courses"]) == course_shelf_service.OPEN_SHELF_LIMIT
    assert shelf["candidateCount"] == 40


@pytest.mark.asyncio
async def test_an_open_row_excludes_what_another_row_already_claims(stub) -> None:
    """A course shown twice invites planning it twice."""
    stub["requirementProgress"] = [
        _bucket("p:core", "Required", remaining=("00940111",), requirement_type="core"),
        _bucket("p:free", "Free electives", credits_remaining=2.0),
    ]
    stub["courses"] = [_course("00940111"), _course("00940222")]
    stub["offered"] = {"00940111", "00940222"}

    shelves = (await _build())["shelves"]

    open_shelf = next(shelf for shelf in shelves if shelf["kind"] == "open")
    assert [c["courseNumber"] for c in open_shelf["courses"]] == ["00940222"]


@pytest.mark.asyncio
async def test_courses_already_planned_are_not_offered_again(stub) -> None:
    stub["requirementProgress"] = [_bucket("p:free", "Free electives", credits_remaining=2.0)]
    stub["courses"] = [_course("00940111"), _course("00940222")]
    stub["offered"] = {"00940111", "00940222"}

    shelves = (await _build())["shelves"]
    planned = await course_shelf_service.build_course_shelves_for_user(
        object(),
        "user-1",
        semester_code="2025-1",
        existing_planned_courses=[{"courseNumber": "00940111", "isActive": True}],
    )

    assert len(shelves[0]["courses"]) == 2
    assert [c["courseNumber"] for c in planned["shelves"][0]["courses"]] == ["00940222"]


def _offering(number, day, time_range, *, exams=None):
    return {
        "courseNumber": number,
        "academicYear": 2025,
        "semesterCode": 200,
        "scheduleGroups": [{"day": day, "time": time_range, "type": "lecture", "group": "10"}],
        "examDates": exams or {},
    }


@pytest.mark.asyncio
async def test_a_course_clashing_with_the_draft_is_dropped_and_counted(stub) -> None:
    """A course that cannot coexist with what the student already picked is as
    unactionable as one the term does not offer."""
    stub["requirementProgress"] = [
        _bucket("p:elective", "Electives", remaining=("00940111", "00940222"))
    ]
    stub["courses"] = [_course("00940111"), _course("00940222")]
    stub["offered"] = {"00940111", "00940222", "00940999"}
    stub["offerings"] = {
        "00940999": _offering("00940999", "Sunday", "10:30-12:30"),
        "00940111": _offering("00940111", "Sunday", "11:30-13:30"),  # clashes
        "00940222": _offering("00940222", "Tuesday", "09:30-11:30"),
    }

    result = await course_shelf_service.build_course_shelves_for_user(
        object(),
        "user-1",
        semester_code="2025-1",
        existing_planned_courses=[{"courseNumber": "00940999", "isActive": True}],
    )

    shelf = result["shelves"][0]
    assert [c["courseNumber"] for c in shelf["courses"]] == ["00940222"]
    assert shelf["conflictsWithDraftCount"] == 1


@pytest.mark.asyncio
async def test_an_empty_draft_never_filters_on_conflicts(stub) -> None:
    stub["requirementProgress"] = [_bucket("p:elective", "Electives", remaining=("00940111",))]
    stub["courses"] = [_course("00940111")]
    stub["offered"] = {"00940111"}

    shelf = (await _build())["shelves"][0]

    assert len(shelf["courses"]) == 1
    assert shelf["conflictsWithDraftCount"] == 0


@pytest.mark.asyncio
async def test_a_course_giving_no_additional_credit_is_dropped(stub) -> None:
    """It shares credit with one the student already passed, so it advances the
    requirement by zero while the row would advertise it as progress."""
    stub["requirementProgress"] = [
        _bucket("p:elective", "Electives", remaining=("00940111", "00940222"))
    ]
    stub["completedCourseRecords"] = [{"courseNumber": "00949999", "grade": 80}]
    courses = [_course("00940111"), _course("00940222")]
    courses[0]["noAdditionalCreditText"] = "00949999"
    stub["courses"] = courses
    stub["offered"] = {"00940111", "00940222"}

    shelf = (await _build())["shelves"][0]

    assert [c["courseNumber"] for c in shelf["courses"]] == ["00940222"]
    assert shelf["noAdditionalCreditCount"] == 1


@pytest.mark.asyncio
async def test_a_course_others_on_the_shelf_need_is_ranked_first(stub) -> None:
    stub["requirementProgress"] = [
        _bucket("p:elective", "Electives", remaining=("00960111", "00960222"))
    ]
    unlocker = _course("00960111")
    dependent = _course("00960222", prerequisites_text="00960111")
    stub["courses"] = [unlocker, dependent]
    stub["offered"] = {"00960111", "00960222"}
    stub["ratings"] = {"00960222": {"meanGeneralRank": 5.0, "responseCount": 60}}

    shelf = (await _build())["shelves"][0]

    assert shelf["courses"][0]["courseNumber"] == "00960111"
    assert "unlocks_later_courses" in shelf["courses"][0]["reasons"]


@pytest.mark.asyncio
async def test_a_card_reports_what_taking_it_would_open(stub) -> None:
    """435 courses in one real term are a single course away from being
    available. The course that would open them got no credit for it."""
    stub["requirementProgress"] = [
        _bucket("p:elective", "Electives", remaining=("00940111", "00940222", "00940333"))
    ]
    stub["courses"] = [
        _course("00940111"),
        _course("00940222", prerequisites_text="00940111"),
        _course("00940333", prerequisites_text="00940111"),
    ]
    stub["offered"] = {"00940111", "00940222", "00940333"}

    shelf = (await _build())["shelves"][0]
    unlocker = next(c for c in shelf["courses"] if c["courseNumber"] == "00940111")

    assert unlocker["unlocks"]["count"] == 2
    assert unlocker["unlocks"]["courseNumbers"] == ["00940222", "00940333"]


@pytest.mark.asyncio
async def test_unlocking_does_not_reorder_the_row(stub) -> None:
    """A third of the term unlocks something and the median unlocks exactly
    one, so ranking on it would fire constantly and separate almost nothing."""
    stub["requirementProgress"] = [
        _bucket("p:free", "Free electives", credits_remaining=2.0)
    ]
    stub["courses"] = [
        _course("00940111"),
        _course("00940222"),
        _course("00949999", prerequisites_text="00940111"),
    ]
    stub["offered"] = {"00940111", "00940222"}
    stub["ratings"] = {"00940222": {"meanGeneralRank": 4.8, "responseCount": 60}}

    shelf = (await _build())["shelves"][0]

    # 00940111 unlocks a course; 00940222 is simply better reviewed and leads.
    assert shelf["courses"][0]["courseNumber"] == "00940222"


@pytest.mark.asyncio
async def test_an_empty_row_says_why_rather_than_rendering_blank(stub) -> None:
    stub["requirementProgress"] = [
        _bucket("p:elective", "Project courses", remaining=("00940111",))
    ]
    stub["courses"] = [_course("00940111", prerequisites_text="00949999")]
    stub["offered"] = {"00940111"}

    shelf = (await _build())["shelves"][0]

    assert shelf["courses"] == []
    assert shelf["emptyReason"] == "none_available_to_you"


@pytest.mark.asyncio
async def test_a_row_with_nothing_offered_this_term_is_distinguished(stub) -> None:
    stub["requirementProgress"] = [
        _bucket("p:elective", "Project courses", remaining=("00940111",))
    ]
    stub["courses"] = [_course("00940111")]
    stub["offered"] = set()

    assert (await _build())["shelves"][0]["emptyReason"] == "none_offered_this_term"


@pytest.mark.asyncio
async def test_a_filled_row_has_no_empty_reason(stub) -> None:
    stub["requirementProgress"] = [
        _bucket("p:elective", "Electives", remaining=("00940111",))
    ]
    stub["courses"] = [_course("00940111")]
    stub["offered"] = {"00940111"}

    assert (await _build())["shelves"][0]["emptyReason"] is None


@pytest.mark.asyncio
async def test_chain_sequencing_does_not_apply_to_an_anything_counts_row(stub) -> None:
    """An open row IS the whole term, so "unlocks others on this shelf" would
    mean "gates anything at all" -- not a reason to take a free elective now."""
    stub["requirementProgress"] = [
        _bucket("p:free", "Free electives", credits_remaining=2.0)
    ]
    stub["courses"] = [
        _course("00940111"),
        _course("00940222", prerequisites_text="00940111"),
    ]
    stub["offered"] = {"00940111", "00940222"}

    shelf = (await _build())["shelves"][0]

    assert shelf["kind"] == "open"
    assert all(
        "unlocks_later_courses" not in (c.get("reasons") or []) for c in shelf["courses"]
    )


@pytest.mark.asyncio
async def test_an_undergraduate_is_not_offered_graduate_courses(stub, monkeypatch) -> None:
    """197 graduate courses sat in one term's undergraduate candidate pool, and
    108 state no prerequisites, so eligibility filtering did not exclude them."""
    async def _context(database, user_id):
        return {
            "status": "ok",
            "profile": {"programType": "BSc"},
            "poolDocuments": [],
            "completedCourseRecords": [],
            "graduationProgress": {},
        }

    monkeypatch.setattr(course_shelf_service, "load_planning_context", _context)
    stub["requirementProgress"] = [
        _bucket("p:elective", "Electives", remaining=("00940111", "00980610"))
    ]
    undergrad = _course("00940111")
    undergrad["studyFramework"] = "לימודי הסמכה"
    graduate = _course("00980610")
    graduate["studyFramework"] = "תארים מתקדמים"
    stub["courses"] = [undergrad, graduate]
    stub["offered"] = {"00940111", "00980610"}

    shelf = (await _build())["shelves"][0]

    assert [c["courseNumber"] for c in shelf["courses"]] == ["00940111"]
    assert shelf["wrongDegreeLevelCount"] == 1


@pytest.mark.asyncio
async def test_the_draft_summary_describes_what_is_planned(stub) -> None:
    """Planned courses are excluded from every shelf, so their documents and
    ratings have to be fetched separately -- reusing the candidate lookups
    silently yields a draft with no credits and no difficulty."""
    stub["requirementProgress"] = [_bucket("p:elective", "Electives", remaining=("00940333",))]
    planned = _course("00940111", credits=3.5)
    stub["courses"] = [planned, _course("00940333")]
    stub["offered"] = {"00940111", "00940333"}
    stub["ratings"] = {"00940111": {"meanDifficultyRank": 4.5, "responseCount": 20}}

    result = await course_shelf_service.build_course_shelves_for_user(
        object(),
        "user-1",
        semester_code="2025-1",
        existing_planned_courses=[{"courseNumber": "00940111", "isActive": True}],
    )

    summary = result["draftSummary"]
    assert summary["plannedCourseCount"] == 1
    assert summary["plannedCredits"] == 3.5
    assert summary["difficulty"]["plannedMean"] == 4.5
