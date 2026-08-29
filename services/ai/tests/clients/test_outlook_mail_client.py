"""The agent's one HTTP call out to `outlook-mcp`, and what it does when that
fails.

Mirrors `test_internal_api_client.py`'s shape: every way outlook-mcp can fail
to answer has to leave this module as `OutlookMailClientError`, carrying a
detail a student can act on (or a safe generic one) rather than an internal
host:port or a raw error code.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.outlook_mail_client import OutlookMailClient, OutlookMailClientError
from app.config import Settings

_ASYNC_CLIENT = "app.clients.outlook_mail_client.httpx.AsyncClient"


def _settings() -> Settings:
    return Settings(outlook_mcp_url="http://outlook-mcp:8020", internal_service_token="t")


def _client_returning(response: Any) -> AsyncMock:
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def _client_raising(error: Exception) -> AsyncMock:
    client = AsyncMock()
    client.post = AsyncMock(side_effect=error)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def _response(status_code: int, payload: dict[str, Any]) -> MagicMock:
    import json

    response = MagicMock()
    response.status_code = status_code
    response.content = json.dumps(payload).encode()
    response.json.return_value = payload
    return response


async def _search() -> list[dict[str, Any]]:
    client = OutlookMailClient(user_id="507f1f77bcf86cd799439011", settings=_settings())
    return await client.search_messages(query="registration", max_results=5)


class TestOutlookMcpNotAnswering:
    async def test_a_transport_failure_is_an_OutlookMailClientError(self) -> None:
        with patch(_ASYNC_CLIENT, return_value=_client_raising(httpx.ConnectError("refused"))):
            with pytest.raises(OutlookMailClientError):
                await _search()

    async def test_the_detail_does_not_name_the_internal_host(self) -> None:
        leaky = httpx.ConnectError("[Errno 111] Connect call failed ('10.0.3.7', 8020)")
        with patch(_ASYNC_CLIENT, return_value=_client_raising(leaky)):
            with pytest.raises(OutlookMailClientError) as caught:
                await _search()
        assert "10.0.3.7" not in caught.value.detail
        assert "8020" not in caught.value.detail

    async def test_a_gateway_answering_with_html_is_not_a_json_crash(self) -> None:
        response = MagicMock()
        response.status_code = 502
        response.content = b"<html><body>Bad Gateway</body></html>"
        response.json.side_effect = ValueError("Expecting value")
        with patch(_ASYNC_CLIENT, return_value=_client_returning(response)):
            with pytest.raises(OutlookMailClientError):
                await _search()


class TestOutlookMcpAnsweringWithAnError:
    @pytest.mark.parametrize(
        ("code", "expected_fragment"),
        [
            ("outlook_not_connected", "connect your Outlook account"),
            ("outlook_consent_required", "reconnect your Outlook account"),
            ("outlook_token_expired", "connection has expired"),
        ],
    )
    async def test_an_actionable_error_code_becomes_a_student_facing_detail(
        self, code: str, expected_fragment: str
    ) -> None:
        payload = {"success": False, "error": {"code": code, "message": "internal detail"}}
        with patch(_ASYNC_CLIENT, return_value=_client_returning(_response(200, payload))):
            with pytest.raises(OutlookMailClientError) as caught:
                await _search()
        assert expected_fragment in caught.value.detail

    async def test_an_unrecognised_error_code_falls_back_to_a_generic_detail(self) -> None:
        """Never surface a raw internal error code or message verbatim -- only
        the codes explicitly mapped get a specific student-facing detail."""
        payload = {"success": False, "error": {"code": "outlook_graph_error", "message": "5xx from Graph"}}
        with patch(_ASYNC_CLIENT, return_value=_client_returning(_response(200, payload))):
            with pytest.raises(OutlookMailClientError) as caught:
                await _search()
        assert "5xx from Graph" not in caught.value.detail


class TestOutlookMcpAnsweringProperly:
    async def test_messages_come_back_unwrapped(self) -> None:
        payload = {
            "source": "outlook_email",
            "trusted": False,
            "warning": "...",
            "data": {"messages": [{"id": "1", "subject": "Registration"}], "count": 1},
        }
        with patch(_ASYNC_CLIENT, return_value=_client_returning(_response(200, payload))):
            messages = await _search()
        assert messages == [{"id": "1", "subject": "Registration"}]

    async def test_the_internal_token_travels_in_the_body_not_a_header(self) -> None:
        """outlook-mcp's handlers read `internalToken` off the MCP `arguments`
        dict, not a header -- this client calls those handlers through a thin
        HTTP wrapper that passes the body straight through, so it has to carry
        the token the same way."""
        payload = {"data": {"messages": [], "count": 0}}
        client = _client_returning(_response(200, payload))
        with patch(_ASYNC_CLIENT, return_value=client):
            await _search()

        _, kwargs = client.post.call_args
        assert kwargs["json"]["internalToken"] == "t"
        assert kwargs["json"]["userId"] == "507f1f77bcf86cd799439011"
