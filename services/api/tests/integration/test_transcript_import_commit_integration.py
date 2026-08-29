"""Integration tests for transcript import commit."""

import pytest

from tests.fixtures.completed_course_fixtures import seed_production_course_fixture

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_transcript_import_commit_requires_auth(auth_client):
    response = await auth_client.post(
        "/transcript-import/commit",
        json={
            "courses": [
                {
                    "courseNumber": "00960401",
                    "semesterCode": "2024-1",
                    "grade": 85,
                    "creditsEarned": 3,
                }
            ]
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_transcript_import_commit_creates_imported_records(auth_client, mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    token = await register_access_token(auth_client, "transcript-commit@example.com")

    response = await auth_client.post(
        "/transcript-import/commit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "courses": [
                {
                    "courseNumber": course["courseNumber"],
                    "semesterCode": "2024-1",
                    "grade": 85,
                    "creditsEarned": 3,
                    "title": "Imported course",
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]["importResult"]
    assert payload["createdCount"] == 1
    assert payload["created"][0]["source"] == "imported"
    assert payload["created"][0]["semesterCode"] == "2024-1"


@pytest.mark.asyncio
async def test_transcript_import_commit_reports_unresolved_catalog(auth_client):
    token = await register_access_token(auth_client, "transcript-unresolved@example.com")

    response = await auth_client.post(
        "/transcript-import/commit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "courses": [
                {
                    "courseNumber": "00000000",
                    "semesterCode": "2024-1",
                    "grade": 85,
                    "creditsEarned": 3,
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]["importResult"]
    # Still reported, so the student learns the course could not be matched --
    # but imported, so its credits do not vanish from the transcript total.
    assert payload["unresolvedCount"] == 1
    assert payload["unresolved"][0]["courseNumber"] == "00000000"
    assert payload["createdCount"] == 1
    assert payload["created"][0]["courseId"] is None
    assert payload["created"][0]["courseNumber"] == "00000000"
    assert payload["created"][0]["creditsEarned"] == 3


@pytest.mark.asyncio
async def test_self_scoped_routes_reject_an_attempt_to_name_another_user(auth_client):
    """Every self-scoped router refuses a `userId` query param, not just one.

    None of these routes READ a user id from the request -- they take it from
    the token -- so an extra param was simply ignored. That is the quiet version
    of the failure: an impersonation attempt looked like a success, and the day
    someone adds a `userId` filter to one of them there is nothing to catch it.
    `graduation_progress` had the guard; the other seven did not.
    """
    token = await register_access_token(auth_client, "impersonation-guard@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    for path in (
        "/completed-courses",
        "/student-profile",
        "/graduation-progress",
        "/semester-plans",
        "/academic-risks",
    ):
        response = await auth_client.get(f"{path}?userId=507f1f77bcf86cd799439011", headers=headers)
        assert response.status_code == 403, f"{path} accepted a cross-user query param"
        assert "Cross-user access" in response.json()["error"]
