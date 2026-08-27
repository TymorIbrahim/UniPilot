"""Unit tests for ai_job_repository — sync helpers and async CRUD via mongomock."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.repositories.ai_job_repository import (
    _format_datetime,
    build_ai_job_document,
    create_ai_job,
    find_ai_job_by_id_and_user_id,
    find_ai_jobs_by_user_id,
    mark_ai_job_failed_to_enqueue,
    to_public_ai_job,
    to_public_ai_job_summary,
)

VALID_USER_ID = str(ObjectId())

VALID_INPUT_SNAPSHOT = {
    "analysisId": str(ObjectId()),
    "semesterCode": "2025-2",
    "summary": {"totalRisks": 2, "highestSeverity": "high", "counts": {"low": 0, "medium": 1, "high": 1}},
    "risks": [
        {"riskType": "overload", "severity": "high", "title": "Overloaded semester"},
        {"riskType": "prerequisite", "severity": "medium", "title": "Missing prereq"},
    ],
}


# ---------------------------------------------------------------------------
# _format_datetime
# ---------------------------------------------------------------------------

def test_format_datetime_converts_to_iso_z():
    dt = datetime(2025, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    assert _format_datetime(dt) == "2025-05-20T12:00:00Z"


def test_format_datetime_returns_none_for_none():
    assert _format_datetime(None) is None


def test_format_datetime_stringifies_other():
    assert _format_datetime("raw") == "raw"


# ---------------------------------------------------------------------------
# build_ai_job_document
# ---------------------------------------------------------------------------

def test_build_ai_job_document_returns_expected_shape():
    doc = build_ai_job_document(VALID_USER_ID, "academic_risk_narrative", VALID_INPUT_SNAPSHOT)
    assert isinstance(doc["userId"], ObjectId)
    assert doc["jobType"] == "academic_risk_narrative"
    assert doc["input"] == VALID_INPUT_SNAPSHOT
    assert doc["status"] == "pending"
    assert doc["result"] is None
    assert doc["error"] is None
    assert doc["attempts"] == 0
    assert isinstance(doc["createdAt"], datetime)
    assert isinstance(doc["queuedAt"], datetime)
    assert doc["startedAt"] is None
    assert doc["completedAt"] is None


def test_build_ai_job_document_raises_on_invalid_user_id():
    with pytest.raises(ValueError, match="Invalid user id"):
        build_ai_job_document("bad-id", "academic_risk_narrative", VALID_INPUT_SNAPSHOT)


# ---------------------------------------------------------------------------
# to_public_ai_job_summary
# ---------------------------------------------------------------------------

def test_to_public_ai_job_summary_returns_none_for_none():
    assert to_public_ai_job_summary(None) is None


def test_to_public_ai_job_summary_extracts_fields():
    doc = {
        "_id": ObjectId(),
        "jobType": "academic_risk_narrative",
        "status": "pending",
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 2, tzinfo=timezone.utc),
    }
    result = to_public_ai_job_summary(doc)
    assert result is not None
    assert result["jobType"] == "academic_risk_narrative"
    assert result["status"] == "pending"
    assert "input" not in result
    assert "result" not in result


# ---------------------------------------------------------------------------
# to_public_ai_job
# ---------------------------------------------------------------------------

def test_to_public_ai_job_returns_none_for_none():
    assert to_public_ai_job(None) is None


def test_to_public_ai_job_includes_input_and_result():
    doc = {
        "_id": ObjectId(),
        "jobType": "academic_risk_narrative",
        "status": "completed",
        "input": VALID_INPUT_SNAPSHOT,
        "result": {"narrative": "All good", "stats": {}},
        "error": None,
        "attempts": 1,
        "queuedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "startedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "completedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    result = to_public_ai_job(doc)
    assert result is not None
    assert result["input"] == VALID_INPUT_SNAPSHOT
    assert result["result"]["narrative"] == "All good"
    assert result["attempts"] == 1


def test_to_public_ai_job_defaults_missing_input_and_attempts():
    doc = {
        "_id": ObjectId(),
        "jobType": "academic_risk_narrative",
        "status": "pending",
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    result = to_public_ai_job(doc)
    assert result is not None
    assert result["input"] == {}
    assert result["attempts"] == 0


# ---------------------------------------------------------------------------
# Async CRUD via mongomock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_ai_job_returns_document_with_id(mongo_database):
    result = await create_ai_job(mongo_database, VALID_USER_ID, "academic_risk_narrative", VALID_INPUT_SNAPSHOT)
    assert "_id" in result
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_find_ai_jobs_by_user_id_returns_created(mongo_database):
    await create_ai_job(mongo_database, VALID_USER_ID, "academic_risk_narrative", VALID_INPUT_SNAPSHOT)
    result = await find_ai_jobs_by_user_id(mongo_database, VALID_USER_ID)
    assert result["total"] == 1
    assert len(result["jobs"]) == 1
    assert result["page"] == 1


@pytest.mark.asyncio
async def test_find_ai_jobs_by_user_id_empty_for_unknown(mongo_database):
    result = await find_ai_jobs_by_user_id(mongo_database, str(ObjectId()))
    assert result["total"] == 0
    assert result["jobs"] == []


@pytest.mark.asyncio
async def test_find_ai_jobs_by_user_id_empty_for_invalid(mongo_database):
    result = await find_ai_jobs_by_user_id(mongo_database, "bad-id")
    assert result["total"] == 0
    assert result["jobs"] == []


@pytest.mark.asyncio
async def test_find_ai_jobs_by_user_id_pagination(mongo_database):
    for i in range(5):
        data = {**VALID_INPUT_SNAPSHOT, "semesterCode": f"2025-{i}"}
        await create_ai_job(mongo_database, VALID_USER_ID, "academic_risk_narrative", data)

    result = await find_ai_jobs_by_user_id(mongo_database, VALID_USER_ID, page=1, limit=3)
    assert len(result["jobs"]) == 3
    assert result["total"] == 5
    assert result["limit"] == 3


@pytest.mark.asyncio
async def test_find_ai_job_by_id_and_user_id_returns_job(mongo_database):
    created = await create_ai_job(mongo_database, VALID_USER_ID, "academic_risk_narrative", VALID_INPUT_SNAPSHOT)
    job_id = str(created["_id"])

    result = await find_ai_job_by_id_and_user_id(mongo_database, job_id, VALID_USER_ID)
    assert result is not None
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_find_ai_job_by_id_returns_none_for_wrong_user(mongo_database):
    created = await create_ai_job(mongo_database, VALID_USER_ID, "academic_risk_narrative", VALID_INPUT_SNAPSHOT)
    job_id = str(created["_id"])

    result = await find_ai_job_by_id_and_user_id(mongo_database, job_id, str(ObjectId()))
    assert result is None


@pytest.mark.asyncio
async def test_find_ai_job_returns_none_for_invalid_ids(mongo_database):
    result = await find_ai_job_by_id_and_user_id(mongo_database, "bad", VALID_USER_ID)
    assert result is None
    result = await find_ai_job_by_id_and_user_id(mongo_database, str(ObjectId()), "bad")
    assert result is None


@pytest.mark.asyncio
async def test_mark_ai_job_failed_to_enqueue_updates_status(mongo_database):
    created = await create_ai_job(mongo_database, VALID_USER_ID, "academic_risk_narrative", VALID_INPUT_SNAPSHOT)

    await mark_ai_job_failed_to_enqueue(mongo_database, created["_id"])

    result = await find_ai_job_by_id_and_user_id(mongo_database, str(created["_id"]), VALID_USER_ID)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "queue_unavailable"
    assert result["completedAt"] is not None
