"""Integration tests for AI job endpoints."""

import pytest

from app.services.ai_job_queue import get_in_memory_ai_job_queue_store, set_ai_job_queue_store
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


async def setup_user_with_analysis(client, mongo_database, email: str) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(client, email)
    await client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    generate_response = await client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2"},
    )
    plan_id = generate_response.json()["data"]["semesterPlan"]["id"]
    analyze_response = await client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"planId": plan_id},
    )
    analysis_id = analyze_response.json()["data"]["academicRiskAnalysis"]["id"]
    return token, analysis_id


@pytest.mark.asyncio
async def test_enqueue_ai_job_happy_path(auth_client, mongo_database):
    token, analysis_id = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-enqueue@example.com"
    )

    response = await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "academic_risk_narrative", "analysisId": analysis_id},
    )

    assert response.status_code == 202
    job = response.json()["data"]["aiJob"]
    assert job["status"] == "pending"
    assert job["jobType"] == "academic_risk_narrative"
    assert job["input"]["analysisId"] == analysis_id
    assert job["result"] is None

    queue_store = get_in_memory_ai_job_queue_store()
    assert job["id"] in queue_store.enqueued


@pytest.mark.asyncio
async def test_enqueue_ai_job_returns_404_for_missing_analysis(auth_client, mongo_database):
    token, _ = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-missing-analysis@example.com"
    )

    response = await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "academic_risk_narrative", "analysisId": "665f2b0f2a3f7b2a1a9a7fff"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_enqueue_ai_job_returns_400_for_unknown_job_type(auth_client, mongo_database):
    token, analysis_id = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-bad-type@example.com"
    )

    response = await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "unsupported_type", "analysisId": analysis_id},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_enqueue_ai_job_returns_400_for_malformed_analysis_id(auth_client, mongo_database):
    token, _ = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-bad-id@example.com"
    )

    response = await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "academic_risk_narrative", "analysisId": "not-an-object-id"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_enqueue_ai_job_returns_503_when_queue_unavailable(auth_client, mongo_database):
    token, analysis_id = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-queue-down@example.com"
    )

    class FailingQueueStore:
        async def enqueue(self, job_id: str) -> None:
            raise RuntimeError("queue down")

    set_ai_job_queue_store(FailingQueueStore())
    try:
        response = await auth_client.post(
            "/ai-jobs",
            headers={"Authorization": f"Bearer {token}"},
            json={"jobType": "academic_risk_narrative", "analysisId": analysis_id},
        )
    finally:
        set_ai_job_queue_store(None)

    assert response.status_code == 503

    # The failed-to-enqueue job is still persisted with status=failed; the 503 response
    # itself carries no body id, so fetch it back via the list endpoint instead.
    list_response = await auth_client.get(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    jobs = list_response.json()["data"]["aiJobs"]
    assert any(job["status"] == "failed" for job in jobs)


@pytest.mark.asyncio
async def test_get_ai_job_by_id(auth_client, mongo_database):
    token, analysis_id = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-get@example.com"
    )

    enqueue_response = await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "academic_risk_narrative", "analysisId": analysis_id},
    )
    job_id = enqueue_response.json()["data"]["aiJob"]["id"]

    response = await auth_client.get(
        f"/ai-jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["aiJob"]["id"] == job_id


@pytest.mark.asyncio
async def test_get_ai_job_returns_400_for_invalid_id(auth_client, mongo_database):
    token, _ = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-bad-get-id@example.com"
    )

    response = await auth_client.get(
        "/ai-jobs/not-a-valid-object-id",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_ai_job_returns_404_when_missing(auth_client, mongo_database):
    token, _ = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-missing-get@example.com"
    )

    response = await auth_client.get(
        "/ai-jobs/665f2b0f2a3f7b2a1a9a7aaa",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_ai_jobs_returns_paginated_history(auth_client, mongo_database):
    token, analysis_id = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-list@example.com"
    )

    await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "academic_risk_narrative", "analysisId": analysis_id},
    )
    await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "academic_risk_narrative", "analysisId": analysis_id},
    )

    response = await auth_client.get(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["aiJobs"]) >= 2
    assert data["pagination"]["total"] >= 2


@pytest.mark.asyncio
async def test_list_ai_jobs_returns_400_for_unknown_query_param(auth_client, mongo_database):
    token = await register_access_token(auth_client, "ai-job-bad-param@example.com")

    response = await auth_client.get(
        "/ai-jobs?unknownParam=value",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "Unknown query parameter" in response.json()["error"]
