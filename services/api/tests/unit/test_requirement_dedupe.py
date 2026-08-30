"""Unit tests for collapsing duplicated requirement groups."""

from __future__ import annotations

from app.repositories.catalog_repository import _dedupe_requirements_by_group_id


def _doc(group_id, credits, promoted="2026-06-01", extra=None):
    return {
        "requirementGroupId": group_id,
        "minCredits": credits,
        "promotedAt": promoted,
        **(extra or {}),
    }


def test_a_requirement_named_twice_is_one_requirement() -> None:
    """023323 carries ten documents for five groups, so its credits doubled --
    304.0 where the catalogue states 152.0 -- and every requirement appeared
    twice on the student's progress."""
    documents = [
        _doc("p:required", 84.0),
        _doc("p:required", 84.0),
        _doc("p:enrichment", 6.0),
        _doc("p:enrichment", 6.0),
    ]

    result = _dedupe_requirements_by_group_id(documents)

    assert len(result) == 2
    assert sum(float(d["minCredits"]) for d in result) == 90.0


def test_the_most_recent_promotion_wins() -> None:
    """A re-promotion supersedes what it replaced rather than being averaged."""
    documents = [
        _doc("p:required", 84.0, promoted="2026-01-01"),
        _doc("p:required", 87.0, promoted="2026-06-27"),
    ]

    assert _dedupe_requirements_by_group_id(documents)[0]["minCredits"] == 87.0


def test_documents_without_a_group_id_are_dropped() -> None:
    assert _dedupe_requirements_by_group_id([{"minCredits": 5.0}]) == []


def test_distinct_groups_are_all_kept_in_a_stable_order() -> None:
    documents = [_doc("p:zeta", 1.0), _doc("p:alpha", 2.0)]

    result = _dedupe_requirements_by_group_id(documents)

    assert [d["requirementGroupId"] for d in result] == ["p:alpha", "p:zeta"]
