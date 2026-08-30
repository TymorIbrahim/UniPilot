"""Structured `{type: step}` events on `/advise/stream`.

The loop reports each activity as a mapping (`id`/`kind`/`label`/`status`).
The stream must forward those as `step` events so the advisor page can keep
an accumulating trace, and still emit a `progress` phrase on `running` so
older clients that only know that event stay non-silent.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.routes.advise as advise_module
from app.agent_core.facts.answer import Answer
from app.agent_core.facts.loop import LoopResult
from app.agent_core.facts.types import Basis
from app.dependencies.internal_auth import require_internal_service_token
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _bypass_internal_auth():
    app.dependency_overrides[require_internal_service_token] = lambda: None
    yield
    app.dependency_overrides.pop(require_internal_service_token, None)


def _answered(text: str) -> LoopResult:
    return LoopResult(
        outcome="answered",
        answer=Answer(text=text, basis=Basis.OFFICIAL_RECORD, used=(), citations=()),
        facts={},
        turns=1,
    )


def _events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def _patch_reporting(monkeypatch, items: list[object], result: LoopResult) -> None:
    async def _fake_run_advice(*, on_progress=None, **_kwargs) -> LoopResult:
        for item in items:
            if on_progress is not None:
                on_progress(item)
        return result

    monkeypatch.setattr(advise_module, "run_advice", _fake_run_advice)


async def test_advise_stream_forwards_structured_steps_before_the_answer(monkeypatch):
    _patch_reporting(
        monkeypatch,
        [
            {"id": "1-thinking", "kind": "thinking", "label": "Thinking…", "status": "running"},
            {"id": "1-thinking", "kind": "thinking", "label": "Thinking…", "status": "done"},
            {
                "id": "1-0-find",
                "kind": "find",
                "label": "Looking up your records…",
                "status": "running",
            },
            {
                "id": "1-0-find",
                "kind": "find",
                "label": "Looking up your records…",
                "status": "done",
            },
        ],
        _answered("You are eligible."),
    )
    response = client.post("/advise/stream", json={"question": "am i eligible?", "user_id": "u1"})

    assert response.status_code == 200
    events = _events(response.text)
    kinds = [event["type"] for event in events]
    assert kinds[:6] == [
        "step",
        "progress",
        "step",
        "step",
        "progress",
        "step",
    ]
    assert kinds[-2:] == ["chunk", "final"]

    steps = [event for event in events if event["type"] == "step"]
    assert [event["id"] for event in steps] == [
        "1-thinking",
        "1-thinking",
        "1-0-find",
        "1-0-find",
    ]
    assert [event["status"] for event in steps] == ["running", "done", "running", "done"]
    assert all("009" not in event["label"] for event in steps)

    progress = [event["text"] for event in events if event["type"] == "progress"]
    assert progress == ["Thinking…", "Looking up your records…"]


async def test_advise_stream_still_forwards_plain_progress_strings(monkeypatch):
    """Callers that still pass a phrase, not a step mapping, keep working."""
    _patch_reporting(
        monkeypatch,
        ["Looking up your records…"],
        _answered("42 credits."),
    )
    response = client.post("/advise/stream", json={"question": "how many?", "user_id": "u1"})
    kinds = [event["type"] for event in _events(response.text)]
    assert kinds == ["progress", "chunk", "final"]
    assert _events(response.text)[0]["text"] == "Looking up your records…"
