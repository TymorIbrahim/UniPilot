"""HTTP transport for the Outlook mail tools.

`app/server.py`'s stdio transport is for a developer's local MCP client (Cursor,
per the README) -- a process another CONTAINER cannot attach stdin to. This is
the transport a backend service (`services/ai`) actually calls over the network.

Deliberately a thin wrapper: every route just hands the request body straight to
the existing handler in `app/tools/handlers.py` as its `arguments` dict and
returns whatever it returns. Auth (`_validate_internal_token`), validation, the
untrusted-content wrapping, and the error-code taxonomy are the handler's, not
duplicated here -- so a stdio call and an HTTP call to the same tool behave
identically. `internalToken` therefore travels IN THE BODY (as an MCP tool
argument would carry it), not as a header -- the one deliberate difference from
this repo's other internal services, and it exists so the handler underneath
never has to know which transport called it.

Every handler already catches its own exceptions and returns a `{"success":
False, "error": {...}}` payload rather than raising, so every route below
answers 200 whether the tool call succeeded or not; the caller reads `error`
out of the body, not the status code.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from app.tools.handlers import (
    outlook_get_attachment_text,
    outlook_get_message,
    outlook_get_recent_messages,
    outlook_list_folders,
    outlook_search_messages,
)

app = FastAPI(
    title="UniPilot Outlook Mail (internal)",
    description="Internal HTTP transport for the Outlook mail MCP tools.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


async def _arguments(request: Request) -> dict[str, Any]:
    body = await request.json()
    return body if isinstance(body, dict) else {}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/search-messages")
async def search_messages(request: Request) -> dict[str, Any]:
    return await outlook_search_messages(await _arguments(request))


@app.post("/tools/get-message")
async def get_message(request: Request) -> dict[str, Any]:
    return await outlook_get_message(await _arguments(request))


@app.post("/tools/list-folders")
async def list_folders(request: Request) -> dict[str, Any]:
    return await outlook_list_folders(await _arguments(request))


@app.post("/tools/get-recent-messages")
async def get_recent_messages(request: Request) -> dict[str, Any]:
    return await outlook_get_recent_messages(await _arguments(request))


@app.post("/tools/get-attachment-text")
async def get_attachment_text(request: Request) -> dict[str, Any]:
    return await outlook_get_attachment_text(await _arguments(request))
