"""Security tests for AI job endpoints."""

import pytest

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
async def test_enqueue_requires_jwt(auth_client):
    response = await auth_client.post(
        "/ai-jobs",
        json={"jobType": "academic_risk_narrative", "analysisId": "665f2b0f2a3f7b2a1a9a7f11"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_requires_jwt(auth_client):
    response = await auth_client.get("/ai-jobs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_requires_jwt(auth_client):
    response = await auth_client.get("/ai-jobs/665f2b0f2a3f7b2a1a9a7f11")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cross_user_job_access_returns_404(auth_client, mongo_database):
    token_a, analysis_id = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-owner@example.com"
    )
    enqueue_response = await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"jobType": "academic_risk_narrative", "analysisId": analysis_id},
    )
    job_id = enqueue_response.json()["data"]["aiJob"]["id"]

    token_b = await register_access_token(auth_client, "ai-job-other@example.com")
    response = await auth_client.get(
        f"/ai-jobs/{job_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_analysis_id_returns_404(auth_client, mongo_database):
    _, analysis_id_a = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-analysis-owner@example.com"
    )

    token_b = await register_access_token(auth_client, "ai-job-analysis-other@example.com")
    response = await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"jobType": "academic_risk_narrative", "analysisId": analysis_id_a},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_enqueue_rejects_unexpected_body_fields(auth_client, mongo_database):
    token, analysis_id = await setup_user_with_analysis(
        auth_client, mongo_database, "ai-job-strict@example.com"
    )

    response = await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jobType": "academic_risk_narrative",
            "analysisId": analysis_id,
            "userId": "665f2b0f2a3f7b2a1a9a7fff",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_enqueue_enforces_job_rate_limit_with_429(job_security_client, mongo_database):
    token, analysis_id = await setup_user_with_analysis(
        job_security_client, mongo_database, "ai-job-rate-limit@example.com"
    )
    first = await job_security_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "academic_risk_narrative", "analysisId": analysis_id},
    )
    assert first.status_code == 202

    second = await job_security_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "academic_risk_narrative", "analysisId": analysis_id},
    )
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_course_recommendation_requires_jwt(auth_client):
    response = await auth_client.post(
        "/ai-jobs",
        json={"jobType": "course_recommendation_narrative"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_course_recommendation_is_scoped_to_own_profile(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token_a = await register_access_token(auth_client, "ai-job-course-rec-owner@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )

    token_b = await register_access_token(auth_client, "ai-job-course-rec-other@example.com")
    response = await auth_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"jobType": "course_recommendation_narrative"},
    )

    # user B has no profile of their own — must get their own 404, never see A's recommendation
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_course_recommendation_enforces_job_rate_limit_with_429(
    job_security_client, mongo_database
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(job_security_client, "ai-job-course-rec-rl@example.com")
    await job_security_client.post(
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

    first = await job_security_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "course_recommendation_narrative"},
    )
    assert first.status_code == 202

    second = await job_security_client.post(
        "/ai-jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"jobType": "course_recommendation_narrative"},
    )
    assert second.status_code == 429
