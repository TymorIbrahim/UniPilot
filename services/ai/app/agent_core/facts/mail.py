"""The student's own connected mailbox as a search-and-cite source.

Mirrors `prose.search_corpus`'s shape exactly: a model-supplied query, a
context-bound client, records back as a `Collection` so the ordinary algebra
(`select`, `sort`, `limit`) applies without reinventing it for mail. The
difference is what the client is bound to -- a wiki retriever is shared across
every student; an `OutlookMailClient` is constructed once per request, already
bound to the asking student's own `user_id`
(`service.py::run_advice` -> `wiring.build_context`), so there is no `userId`
anywhere in this module's arguments to get wrong.
"""

from __future__ import annotations

from app.agent_core.facts.types import Basis, Collection, Completeness, Record, Scalar, ScalarKind
from app.clients.outlook_mail_client import OutlookMailClient


async def search_mailbox(client: OutlookMailClient, query: str, limit: int = 10) -> Collection:
    """Candidate messages, as a Collection so the algebra applies to them.

    Never complete: a mailbox search is top-k by construction, the same reason
    `search_corpus` never claims completeness either -- a `count` over a
    truncated inbox scan would be a confident number that means nothing.
    """
    messages = await client.search_messages(query=query, max_results=limit)
    records = tuple(
        Record(
            fields=_fields(message),
            basis=Basis.LIVE_MAIL,
        )
        for message in messages
    )
    return Collection(records=records, completeness=Completeness(complete=False, total=None))


def _fields(message: dict) -> dict[str, Scalar]:
    sender = message.get("sender") or {}
    snippet = message.get("snippet")
    snippet_text = snippet.get("content") if isinstance(snippet, dict) else snippet

    fields = {
        "id": Scalar(ScalarKind.IDENTIFIER, str(message.get("id") or "")),
        "subject": Scalar(ScalarKind.TEXT, str(message.get("subject") or "")),
        "senderName": Scalar(ScalarKind.TEXT, str(sender.get("name") or "")),
        "senderEmail": Scalar(ScalarKind.TEXT, str(sender.get("email") or "")),
        # A string, not `ScalarKind.DATE`: the client hands back Graph's ISO-8601
        # text as-is, and DATE is for values already coerced to a real
        # `date`/`datetime` -- claiming the kind here without that conversion
        # would let an ordering comparison run against uncoerced text.
        "receivedDateTime": Scalar(ScalarKind.TEXT, str(message.get("receivedDateTime") or "")),
        "snippet": Scalar(ScalarKind.TEXT, str(snippet_text or "")),
    }
    return {name: value for name, value in fields.items() if value.value}
