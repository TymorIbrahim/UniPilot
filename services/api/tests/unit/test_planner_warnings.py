"""Unit tests for planner prerequisite and credit warnings."""

from app.planning.planner_warnings import assess_prerequisite_warning, build_planner_insights


def test_assess_prerequisite_manual_verification_when_only_text():
    course = {
        "courseNumber": "00940345",
        "prerequisitesText": "קורסים 00940101 ו-00940102",
    }
    result = assess_prerequisite_warning(
        course,
        completed_records=[],
        courses_by_number={},
        courses_by_id={},
    )
    assert result["status"] == "manual_verification"


def test_assess_prerequisite_satisfied_with_explicit_ids():
    course = {
        "courseNumber": "00940345",
        "prerequisites": ["abc123"],
    }
    result = assess_prerequisite_warning(
        course,
        completed_records=[{"courseId": "abc123", "courseNumber": "00940101"}],
        courses_by_number={},
        courses_by_id={"abc123": {"courseNumber": "00940101", "titleHebrew": "Algebra"}},
    )
    assert result["status"] == "satisfied"


def test_assess_prerequisite_missing_with_explicit_ids():
    course = {
        "courseNumber": "00940345",
        "prerequisites": ["abc123"],
    }
    result = assess_prerequisite_warning(
        course,
        completed_records=[],
        courses_by_number={},
        courses_by_id={"abc123": {"courseNumber": "00940101", "titleHebrew": "Algebra"}},
    )
    assert result["status"] == "missing"
    assert result["missingPrerequisites"][0]["courseNumber"] == "00940101"


def test_assess_prerequisite_resolved_ids_missing():
    course = {
        "courseNumber": "00940345",
        "prerequisites": None,
        "prerequisitesText": "00940101",  # no explicit prereqs but text has numbers
    }
    from app.planning.prerequisite_resolver import resolve_prerequisite_ids

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "app.planning.planner_warnings.resolve_prerequisite_ids",
        return_value=["pid1"],
    ):
        from app.planning.planner_warnings import assess_prerequisite_warning

        result = assess_prerequisite_warning(
            course,
            completed_records=[],
            courses_by_number={},
            courses_by_id={"pid1": {"courseNumber": "00940101"}},
        )
    assert result["status"] == "missing"


def test_assess_prerequisite_resolved_ids_satisfied():
    course = {
        "courseNumber": "00940345",
        "prerequisites": None,
        "prerequisitesText": "00940101",
    }
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "app.planning.planner_warnings.resolve_prerequisite_ids",
        return_value=["pid1"],
    ):
        from app.planning.planner_warnings import assess_prerequisite_warning

        result = assess_prerequisite_warning(
            course,
            completed_records=[{"courseId": "pid1", "courseNumber": "00940101"}],
            courses_by_number={},
            courses_by_id={"pid1": {"courseNumber": "00940101"}},
        )
    assert result["status"] == "satisfied"


def test_one_satisfied_alternative_is_enough():
    """`00970215` needs ONE of five courses. Read as a flat list it demanded
    all five, and a student who had done exactly what was asked was told they
    were missing four courses."""
    course = {
        "courseNumber": "00970215",
        "prerequisitesText": "02360756 או 00960411 או 00460203 או 00460202 או 00460195",
    }

    result = assess_prerequisite_warning(
        course,
        completed_records=[{"courseId": "x", "courseNumber": "00960411"}],
        courses_by_number={},
        courses_by_id={},
    )

    assert result["status"] == "satisfied"


def test_an_unsatisfied_choice_reports_the_alternatives_separately():
    course = {
        "courseNumber": "00970215",
        "prerequisitesText": "02360756 או 00960411",
    }

    result = assess_prerequisite_warning(
        course,
        completed_records=[],
        courses_by_number={},
        courses_by_id={},
    )

    assert result["status"] == "missing"
    assert result["requiresOneOf"] is True
    assert result["missingPrerequisiteOptions"] == [["02360756"], ["00960411"]]
    # The flat key means "all of these are needed", which is false here.
    assert "missingPrerequisiteNumbers" not in result


def test_a_conjunction_still_reports_one_combined_option():
    course = {
        "courseNumber": "00940345",
        "prerequisitesText": "00940564 ו-00940424",
    }

    result = assess_prerequisite_warning(
        course,
        completed_records=[{"courseId": "x", "courseNumber": "00940564"}],
        courses_by_number={},
        courses_by_id={},
    )

    assert result["status"] == "missing"
    assert result["requiresOneOf"] is False
    assert result["missingPrerequisiteNumbers"] == ["00940424"]


def test_and_binds_tighter_than_or_when_deciding_eligibility():
    """Two alternative pairs, not two courses and two alternatives."""
    course = {
        "courseNumber": "00940345",
        "prerequisitesText": "01240400 ו-02340128 או 01150203 ו-02340128",
    }

    result = assess_prerequisite_warning(
        course,
        completed_records=[
            {"courseId": "a", "courseNumber": "01150203"},
            {"courseId": "b", "courseNumber": "02340128"},
        ],
        courses_by_number={},
        courses_by_id={},
    )

    assert result["status"] == "satisfied"


def test_text_the_grammar_does_not_cover_stays_manual():
    """Three catalog entries are truncated mid-rule by the source. Guessing at
    a half-stated requirement is worse than admitting it is unread."""
    course = {
        "courseNumber": "00960573",
        "prerequisitesText": "(00940347 ו-00940411) או (00940345 ו-...",
    }

    result = assess_prerequisite_warning(
        course,
        completed_records=[{"courseId": "a", "courseNumber": "00940347"}],
        courses_by_number={},
        courses_by_id={},
    )

    assert result["status"] == "manual_verification"


def test_assess_prerequisite_possibly_missing_from_text():
    course = {
        "courseNumber": "00940345",
        "prerequisites": None,
        "prerequisitesText": "requires 00940101",
    }
    result = assess_prerequisite_warning(
        course,
        completed_records=[],
        courses_by_number={},
        courses_by_id={},
    )
    assert result["status"] in ("possibly_missing", "manual_verification")


def test_assess_prerequisite_no_prereqs_returns_none_status():
    course = {"courseNumber": "00940345"}
    result = assess_prerequisite_warning(
        course,
        completed_records=[],
        courses_by_number={},
        courses_by_id={},
    )
    assert result["status"] == "none"


def test_build_planner_insights_without_schedule():
    plan = {
        "semesters": [
            {
                "plannedCourses": [
                    {"courseId": "cid1", "courseNumber": "00940345", "credits": 5, "isActive": True},
                ],
            }
        ]
    }
    from app.planning.planner_warnings import build_planner_insights

    insights = build_planner_insights(
        plan,
        profile=None,
        completed_records=[],
        catalog_courses=[],
    )
    assert insights["totalCredits"] == 5
    assert insights["creditsWarning"] is None


def test_build_planner_insights_unknown_course_warning():
    plan = {
        "semesters": [
            {
                "plannedCourses": [
                    {"courseId": "cid_unknown", "courseNumber": "99999999", "credits": 3, "isActive": True},
                ],
            }
        ]
    }
    from app.planning.planner_warnings import build_planner_insights

    insights = build_planner_insights(
        plan,
        profile=None,
        completed_records=[],
        catalog_courses=[],  # empty - course not in catalog
    )
    assert any(w["status"] == "unknown_course" for w in insights["courseWarnings"])


def test_build_planner_insights_total_credits_and_conflicts():
    plan = {
        "semesters": [
            {
                "plannedCourses": [
                    {"courseId": "1", "courseNumber": "00940345", "credits": 3, "isActive": True},
                    {"courseId": "2", "courseNumber": "00940411", "credits": 3.5, "isActive": False},
                ],
                "weeklySchedule": {
                    "status": "conflicts",
                    "entries": [
                        {
                            "courseNumber": "00940345",
                            "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
                        },
                        {
                            "courseNumber": "00940411",
                            "scheduleGroups": [{"day": "Sunday", "time": "11:30-13:30"}],
                        },
                    ],
                    "conflicts": [
                        {
                            "day": "Sunday",
                            "timeRange": "10:30-12:30",
                            "courseNumbers": ["00940345", "00940411"],
                        }
                    ],
                },
            }
        ]
    }
    insights = build_planner_insights(
        plan,
        profile={"preferences": {"maxCreditsPerSemester": 2}},
        completed_records=[],
        catalog_courses=[],
    )
    assert insights["totalCredits"] == 3
    assert insights["creditsWarning"]["status"] == "over_max"
    assert insights["scheduleConflicts"] == []


# ---------------------------------------------------------------------------
# Missing coverage
# ---------------------------------------------------------------------------

def test_assess_prerequisite_possibly_missing_when_numbers_not_completed():
    """Lines 116-118: parsed_numbers present but prereq_text is falsy."""
    from unittest.mock import patch

    course = {
        "courseNumber": "00940345",
        "prerequisitesText": None,  # no text → bypasses line 107
    }
    # Patch to return numbers even when text is None, to exercise lines 116-118
    with patch(
        "app.planning.planner_warnings.extract_course_numbers_from_text",
        return_value=["00940101"],
    ):
        result = assess_prerequisite_warning(
            course,
            completed_records=[],
            courses_by_number={},
            courses_by_id={},
        )
    assert result["status"] == "possibly_missing"
    assert "00940101" in result["missingPrerequisiteNumbers"]


def test_build_planner_insights_recomputes_conflicts_when_none():
    plan = {
        "semesters": [
            {
                "semesterCode": "2025-2",
                "plannedCourses": [
                    {"courseId": "id1", "courseNumber": "00940101", "credits": 3, "isActive": True},
                ],
                "weeklySchedule": {
                    "entries": [
                        {
                            "courseId": "id1",
                            "courseNumber": "00940101",
                            "courseTitle": "A",
                            "scheduleGroups": [{"day": "Sunday", "time": "10:00-12:00"}],
                        }
                    ],
                    "customEvents": [],
                    # No "conflicts" key → conflicts is None → triggers recomputation
                },
            }
        ]
    }
    insights = build_planner_insights(
        plan,
        profile=None,
        completed_records=[],
        catalog_courses=[],
    )
    # Conflicts should have been computed
    assert "scheduleConflicts" in insights
