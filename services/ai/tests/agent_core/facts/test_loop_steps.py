"""The loop's student-facing activity channel.

Each thinking turn and each dispatched tool reports running then done. Labels
are kind-only so a course number or grade cannot leak onto the live trace.
"""

from __future__ import annotations

from app.agent_core.facts.answer import HeldFact
from app.agent_core.facts.dispatch import DispatchContext
from app.agent_core.facts.loop import run_loop
from app.agent_core.facts.types import (
    Basis,
    Collection,
    Completeness,
    Record,
    Scalar,
    ScalarKind,
)

I = ScalarKind.IDENTIFIER


def _coll(*ids: str) -> Collection:
    return Collection(
        records=tuple(Record(fields={"id": Scalar(I, i)}, basis=Basis.OFFICIAL_RECORD) for i in ids),
        completeness=Completeness(complete=True, total=len(ids)),
    )


class _ScriptedModel:
    def __init__(self, *replies):
        self.replies = list(replies)

    async def respond(self, prompt):
        return self.replies.pop(0) if self.replies else {}


def _context(**facts) -> DispatchContext:
    return DispatchContext(
        facts={name: HeldFact(value=value, basis=Basis.OFFICIAL_RECORD) for name, value in facts.items()}
    )


async def test_it_reports_thinking_and_tool_steps_without_grounded_values() -> None:
    events: list[dict] = []
    model = _ScriptedModel(
        {"calls": [{"tool": "compute", "args": {"pipelines": [
            {"name": "n", "source": "required", "stages": [{"op": "aggregate", "agg": "count"}]}
        ]}}]},
        {"answer": "You need {n} more."},
    )
    await run_loop(
        "how many?",
        model,
        _context(required=_coll("00940314", "00960211")),
        on_progress=events.append,
    )

    pairs = [(event["kind"], event["status"]) for event in events]
    assert pairs[0] == ("thinking", "running")
    assert ("thinking", "done") in pairs
    assert ("compute", "running") in pairs
    assert ("compute", "done") in pairs
    # thinking for the answer turn, after the tool finished
    assert pairs.count(("thinking", "running")) == 2
    assert pairs.count(("compute", "running")) == 1
    assert pairs.count(("compute", "done")) == 1

    for event in events:
        assert "009" not in event["label"]
        assert "00940314" not in json_blob(event)
        assert event["status"] in ("running", "done")
        assert event["id"]
        assert event["kind"]


def json_blob(event: dict) -> str:
    return " ".join(str(value) for value in event.values())
