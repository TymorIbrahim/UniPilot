"""HTTP client for the Outlook mail tools (`services/outlook-mcp`).

Mirrors `internal_api_client.py`'s shape, with one deliberate difference: the
internal token travels IN THE JSON BODY as `internalToken`, not as an
`X-Internal-Service-Token` header. outlook-mcp's handlers were written to take
MCP tool `arguments` -- a flat dict with no separate header channel -- and this
client calls those same handlers verbatim through a thin HTTP wrapper
(`app/http_server.py` on the other side), so it carries the token the same way
an MCP call would rather than inventing a second auth path for one service.

`user_id` is bound to the CALLER of this client's constructor, never to a tool
argument the model can see or set -- `dispatch.py::_search_mailbox` never
receives a `userId` in `args` at all. See the module docstring in
`app/agent_core/facts/dispatch.py` for why that matters more than the `find`
predicate scoping it doesn't need.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

UNREACHABLE_DETAIL = "the mailbox service could not be reached"
"""Mirrors `internal_api_client.UNREACHABLE_DETAIL` -- fixed text because this
reaches a defect the model may quote, and an internal host:port is not
something to hand a student."""

_ERROR_DETAIL_BY_CODE = {
    "outlook_not_connected": "connect your Outlook account in Settings -> Integrations to use this",
    "outlook_consent_required": "reconnect your Outlook account in Settings -> Integrations to use this",
    "outlook_token_expired": "your Outlook connection has expired -- reconnect it in Settings -> Integrations",
    "outlook_permission_denied": "your Outlook connection is missing a required permission -- reconnect it in Settings -> Integrations",
    "outlook_rate_limited": "Outlook is temporarily rate-limited -- try again shortly",
}
"""Only the codes a student can actually act on. Anything else (validation,
network, not-found, an unrecognised code) falls through to a generic message --
the specifics belong in the server log, not in what the model can quote."""

_GENERIC_ERROR_DETAIL = "the mailbox could not be searched right now"


class OutlookMailClientError(Exception):
    def __init__(self, *, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class OutlookMailClient:
    """Bound to one authenticated student for the lifetime of one request."""

    def __init__(self, *, user_id: str, settings: Settings | None = None) -> None:
        self._user_id = user_id
        self._settings = settings or get_settings()

    async def search_messages(
        self,
        *,
        query: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """The student's own mailbox only -- `user_id` came from the constructor,
        never from a caller-supplied argument."""
        payload = await self._call(
            "/tools/search-messages",
            {
                "userId": self._user_id,
                "query": query,
                "maxResults": max_results,
            },
        )
        return list(payload.get("messages", []))

    async def _call(self, path: str, arguments: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings
        body = {
            **{key: value for key, value in arguments.items() if value is not None},
            "internalToken": settings.resolved_internal_service_token(),
        }
        url = f"{settings.resolved_outlook_mcp_url()}{path}"
        timeout = httpx.Timeout(settings.internal_api_timeout_seconds, connect=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=body)
        except httpx.HTTPError as exc:
            logger.warning("outlook-mcp unreachable at %s: %s", url, exc)
            raise OutlookMailClientError(detail=UNREACHABLE_DETAIL) from exc

        try:
            result = response.json() if response.content else {}
        except ValueError as exc:
            logger.warning("outlook-mcp returned non-JSON (%s) from %s: %s", response.status_code, url, exc)
            raise OutlookMailClientError(detail=_GENERIC_ERROR_DETAIL) from exc

        if not isinstance(result, dict) or result.get("error"):
            code = ""
            if isinstance(result, dict) and isinstance(result.get("error"), dict):
                code = str(result["error"].get("code") or "")
            detail = _ERROR_DETAIL_BY_CODE.get(code, _GENERIC_ERROR_DETAIL)
            raise OutlookMailClientError(detail=detail)

        data = result.get("data")
        if not isinstance(data, dict):
            raise OutlookMailClientError(detail=_GENERIC_ERROR_DETAIL)
        return data
