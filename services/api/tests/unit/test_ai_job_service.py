"""Unit tests for ai_job_service pure input-builder functions."""

from __future__ import annotations

from bson import ObjectId

from app.services.ai_job_service import (
    build_academic_risk_narrative_input,
    build_course_recommendation_input,
)


def test_build_academic_risk_narrative_input_extracts_expected_fields():
    analysis_id = ObjectId()
    analysis_document = {
        "_id": analysis_id,
        "semesterCode": "2025-2",
        "summary": {
            "totalRisks": 2,
            "highestSeverity": "high",
            "counts": {"low": 0, "medium": 1, "high": 1},
        },
        "risks": [
            {
                "riskType": "overload",
                "severity": "high",
                "title": "Overloaded semester",
                "explanation": "Too many credits",
                "evidence": {},
                "suggestedFixes": [],
                "source": "rule",
                "relatedCourseIds": [],
            },
        ],
    }

    result = build_academic_risk_narrative_input(analysis_document)

    assert result["analysisId"] == str(analysis_id)
    assert result["semesterCode"] == "2025-2"
    assert result["summary"]["totalRisks"] == 2
    assert result["risks"] == [
        {"riskType": "overload", "severity": "high", "title": "Overloaded semester"}
    ]


def test_build_academic_risk_narrative_input_defaults_missing_summary_and_risks():
    analysis_document = {"_id": ObjectId(), "semesterCode": None}

    result = build_academic_risk_narrative_input(analysis_document)

    assert result["summary"] == {
        "totalRisks": 0,
        "highestSeverity": None,
        "counts": {"low": 0, "medium": 0, "high": 0},
    }
    assert result["risks"] == []


# ---------------------------------------------------------------------------
# build_course_recommendation_input
# ---------------------------------------------------------------------------


def _catalog_course(course_id: str, *, number: str, title: str, credits: float, prerequisites=None):
    return {
        "_id": course_id,
        "courseNumber": number,
        "title": title,
        "credits": credits,
        "prerequisites": prerequisites or [],
        "status": "published",
    }


def _base_context(**overrides):
    context = {
        "degree": {"programCode": "test-program"},
        "catalogCourses": [],
        "completedCourseRecords": [],
        "graduationProgress": {
            "remainingMandatoryCourses": [],
            "remainingElectiveCredits": 0,
            "requirementProgress": [],
            "completionPercentage": 40,
            "creditsRemaining": 80,
        },
        "hardRequirements": None,
        "poolDocuments": None,
        "semesterMatrixDocuments": None,
    }
    context.update(overrides)
    return context


def test_build_course_recommendation_input_includes_takeable_mandatory_course():
    course_id = str(ObjectId())
    context = _base_context(
        catalogCourses=[_catalog_course(course_id, number="00940101", title="Algebra", credits=3.0)],
        graduationProgress={
            "remainingMandatoryCourses": [{"courseId": course_id}],
            "remainingElectiveCredits": 0,
            "requirementProgress": [],
            "completionPercentage": 40,
            "creditsRemaining": 80,
        },
    )

    result = build_course_recommendation_input(context)

    assert result["degreeCode"] == "test-program"
    assert result["completionPercentage"] == 40
    assert result["creditsRemaining"] == 80
    assert result["recommendedMandatoryCourses"] == [
        {"courseNumber": "00940101", "title": "Algebra", "credits": 3.0}
    ]
    assert result["recommendedElectiveCourses"] == []


def test_build_course_recommendation_input_excludes_courses_with_unmet_prerequisites():
    blocked_id = str(ObjectId())
    prereq_id = str(ObjectId())
    context = _base_context(
        catalogCourses=[
            _catalog_course(
                blocked_id,
                number="00940201",
                title="Advanced Algebra",
                credits=3.0,
                prerequisites=[prereq_id],
            ),
        ],
        graduationProgress={
            "remainingMandatoryCourses": [{"courseId": blocked_id}],
            "remainingElectiveCredits": 0,
            "requirementProgress": [],
            "completionPercentage": 10,
            "creditsRemaining": 100,
        },
    )

    result = build_course_recommendation_input(context)

    assert result["recommendedMandatoryCourses"] == []


def test_build_course_recommendation_input_caps_at_five_candidates():
    course_ids = [str(ObjectId()) for _ in range(7)]
    context = _base_context(
        catalogCourses=[
            _catalog_course(cid, number=f"0094010{i}", title=f"Course {i}", credits=3.0)
            for i, cid in enumerate(course_ids)
        ],
        graduationProgress={
            "remainingMandatoryCourses": [{"courseId": cid} for cid in course_ids],
            "remainingElectiveCredits": 0,
            "requirementProgress": [],
            "completionPercentage": 0,
            "creditsRemaining": 155,
        },
    )

    result = build_course_recommendation_input(context)

    assert len(result["recommendedMandatoryCourses"]) == 5


def test_build_course_recommendation_input_returns_empty_lists_when_nothing_remains():
    context = _base_context()

    result = build_course_recommendation_input(context)

    assert result["recommendedMandatoryCourses"] == []
    assert result["recommendedElectiveCourses"] == []
