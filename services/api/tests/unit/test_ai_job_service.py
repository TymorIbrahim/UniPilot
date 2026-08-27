"""Unit tests for build_academic_risk_narrative_input — pure extraction function."""

from __future__ import annotations

from bson import ObjectId

from app.services.ai_job_service import build_academic_risk_narrative_input


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
