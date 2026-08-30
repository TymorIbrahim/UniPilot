"""Integration tests for the browsable planner rows endpoint.

The unit tests stub the service, so they never exercise the request schema.
That gap let the endpoint reject every non-empty draft the planner sent, with
the panel showing only "something went wrong".
"""

import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_semester_plans_integration import (
    create_profile,
    register_access_token,
)


@pytest.mark.asyncio
async def test_course_shelves_accepts_a_draft_carrying_only_course_numbers(
    auth_client, mongo_database
):
    """What the planner actually sends. `ExistingPlannedCourseInput` demands
    `courseId` and `credits` because it is shaped for saving a plan; the
    shelves only need to know which numbers are spoken for."""
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "shelves-draft@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/course-shelves",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "semesterCode": "2025-2",
            "existingPlannedCourses": [{"courseNumber": "00940345", "isActive": True}],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["semesterCode"] == "2025-2"
    assert isinstance(payload["shelves"], list)
    assert payload["draftSummary"]["plannedCourseCount"] >= 0


@pytest.mark.asyncio
async def test_course_shelves_works_with_an_empty_draft(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "shelves-empty@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/course-shelves",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["draftSummary"]["plannedCourseCount"] == 0


@pytest.mark.asyncio
async def test_course_shelves_rejects_an_invalid_semester_code(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "shelves-bad-term@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/course-shelves",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "not-a-semester"},
    )

    # The app normalises validation failures into its own 400 envelope.
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_course_shelves_requires_authentication(auth_client):
    response = await auth_client.post(
        "/semester-plans/course-shelves", json={"semesterCode": "2025-2"}
    )

    assert response.status_code == 401
