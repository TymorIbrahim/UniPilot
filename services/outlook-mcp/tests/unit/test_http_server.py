"""The HTTP transport `services/ai` actually reaches over the network.

`app/server.py`'s stdio transport has no stdin to attach to in a standalone
container -- this is what makes the same tools reachable from another service.
Every route is a thin pass-through to the handler already covered by
`test_handlers.py`, so these tests exist to prove the WIRING (request body in,
handler's own dict out, unchanged), not to re-test handler logic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.http_server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_a_missing_internal_token_is_a_200_with_an_error_payload(client: TestClient) -> None:
    """The handler never raises an HTTP-level error for a bad token -- it
    answers 200 with `success: False`, the same way it would over stdio. The
    caller (`OutlookMailClient`) reads the payload, not the status code."""
    response = client.post("/tools/search-messages", json={"userId": "507f1f77bcf86cd799439011"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "outlook_validation_error"


def test_search_messages_returns_the_untrusted_wrapper(
    mongo_database, sample_user_id, internal_token, monkeypatch, client: TestClient
) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    from app.config import get_settings
    from app.db.mongo import set_test_database

    get_settings.cache_clear()
    set_test_database(mongo_database)

    async def fake_search(self, **kwargs):
        return [
            {
                "id": "msg-1",
                "subject": "Registration opens Monday",
                "sender": {"name": "Registrar", "email": "registrar@technion.ac.il"},
                "receivedDateTime": "2026-08-20T09:00:00Z",
                "snippet": "Course registration opens next week",
                "hasAttachments": False,
                "folderId": "inbox",
            }
        ]

    from app.graph.client import GraphMailClient

    monkeypatch.setattr(GraphMailClient, "search_messages", fake_search)

    response = client.post(
        "/tools/search-messages",
        json={"userId": sample_user_id, "internalToken": internal_token, "maxResults": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["trusted"] is False
    assert payload["data"]["messages"][0]["subject"] == "Registration opens Monday"


def test_search_messages_reports_not_connected_rather_than_erroring(
    mongo_database, sample_user_id, internal_token, monkeypatch, client: TestClient
) -> None:
    """No token document was ever inserted for this user -- exactly the shape
    of a student who has never connected Outlook. `OutlookMailClient` maps this
    code to "connect your Outlook account"; this test only proves the code
    reaches the HTTP layer unchanged."""
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    from app.config import get_settings
    from app.db.mongo import set_test_database

    get_settings.cache_clear()
    set_test_database(mongo_database)

    response = client.post(
        "/tools/search-messages",
        json={"userId": sample_user_id, "internalToken": internal_token},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "outlook_not_connected"
