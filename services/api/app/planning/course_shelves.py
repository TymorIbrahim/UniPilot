"""Group candidate courses by the requirement they would advance.

Why this exists
---------------
`build_candidate_pools` returns one flat `mandatoryCandidates` list and one flat
`electiveCandidates` list. That is the right shape for the auto-planner, which
picks a set under a credit cap and does not care where the credits land. It is
the wrong shape for a student browsing their own options, where the requirement
a course advances IS the reason to show it -- and that attribution is computed
in `requirementProgress` and then thrown away.

A shelf is one row: a named group of courses that all advance the same
requirement, with the credits that requirement still needs.

Three kinds, because the choice is not the same in each
-------------------------------------------------------
`mandatory` -- courses the student must eventually pass. There is no choice of
*whether*, only of *when*, so these are not ranked by desirability; see
`course_deferral` for what a card here should say instead.

`pool` -- an enumerable set of eligible courses, several of which may serve the
same requirement. This is a genuine choice and the one place course outcome and
rating data legitimately drives ordering.

`open` -- a credit bucket that accepts anything (free electives, enrichment).
Its pool is empty by design, so the candidates are the term's whole offering
list and must come from a query rather than from the catalog rules. The shelf
is still emitted, because a row that says "2 credits, anything counts" is
information; a missing row is not.

One bucket, several shelves
---------------------------
A bucket may link several pools. `elective-faculty` links four -- three thematic
focus chains and a catch-all -- which are alternative ways to spend the same
credits, so they are a row each rather than one merged list. A bucket may also
carry named required courses AND a choice pool: `core-mandatory` has both, and
merging them would present a free choice as an obligation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.planning.prerequisite_resolver import canonical_course_number

MANDATORY = "mandatory"
POOL = "pool"
OPEN = "open"

OBLIGATION_REQUIREMENT_TYPES = frozenset({"core"})
"""Requirement types whose `remainingCourses` are obligations rather than options.

`isMandatory` does not carry this distinction: it is true on "Faculty electives"
because the BUCKET is required -- 35.5 credits of it -- while the courses named
under it are a menu. Only a `core` requirement names courses the student must
individually pass.
"""


@dataclass(frozen=True)
class CourseShelf:
    """One row of the browsable planner."""

    shelf_id: str
    title: str
    kind: str
    requirement_group_id: str
    requirement_title: str
    credits_remaining: float
    course_numbers: tuple[str, ...]

    @property
    def is_choice(self) -> bool:
        """Whether the student is picking between these, or must take them all."""
        return self.kind != MANDATORY

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "shelfId": self.shelf_id,
            "title": self.title,
            "kind": self.kind,
            "requirementGroupId": self.requirement_group_id,
            "requirementTitle": self.requirement_title,
            "creditsRemaining": self.credits_remaining,
            "courseNumbers": list(self.course_numbers),
            "isChoice": self.is_choice,
        }


def _normalized_numbers(
    references: Iterable[dict[str, Any]],
    *,
    exclude: frozenset[str],
) -> tuple[str, ...]:
    """Course numbers in source order, normalised, deduplicated, minus `exclude`."""
    numbers: list[str] = []
    seen: set[str] = set()
    for reference in references or []:
        number = canonical_course_number((reference or {}).get("courseNumber"))
        if number is None or number in seen or number in exclude:
            continue
        seen.add(number)
        numbers.append(number)
    return tuple(numbers)


def _credits_remaining(entry: dict[str, Any]) -> float:
    try:
        return float(entry.get("creditsRemaining") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_course_shelves(
    *,
    requirement_progress: list[dict[str, Any]],
    pool_documents: list[dict[str, Any]],
    completed_course_numbers: Iterable[str] = (),
) -> list[CourseShelf]:
    """The rows a student should see, for the requirements they have left.

    Satisfied requirements are omitted: a row for work already done is clutter,
    and the shelf list is meant to be a list of what is still open.
    """
    completed = frozenset(
        number
        for raw in completed_course_numbers
        if (number := canonical_course_number(raw)) is not None
    )

    unsatisfied = [
        entry
        for entry in requirement_progress or []
        if entry.get("status") != "satisfied" and entry.get("requirementGroupId")
    ]

    pools_by_bucket: dict[str, list[dict[str, Any]]] = {}
    for document in pool_documents or []:
        bucket_id = document.get("linkedCreditBucketId")
        if bucket_id:
            pools_by_bucket.setdefault(str(bucket_id), []).append(document)

    shelves: list[CourseShelf] = []
    for entry in unsatisfied:
        bucket_id = str(entry["requirementGroupId"])
        bucket_title = str(entry.get("title") or bucket_id)
        credits_remaining = _credits_remaining(entry)

        remaining = _normalized_numbers(
            entry.get("remainingCourses") or [], exclude=completed
        )
        if remaining:
            names_obligations = (
                str(entry.get("requirementType") or "") in OBLIGATION_REQUIREMENT_TYPES
            )
            shelves.append(
                CourseShelf(
                    shelf_id=bucket_id,
                    title=bucket_title,
                    kind=MANDATORY if names_obligations else POOL,
                    requirement_group_id=bucket_id,
                    requirement_title=bucket_title,
                    credits_remaining=credits_remaining,
                    course_numbers=remaining,
                )
            )

        linked_pools = sorted(
            pools_by_bucket.get(bucket_id, []),
            key=lambda document: str(document.get("title") or document.get("requirementGroupId") or ""),
        )
        pool_shelves = [
            CourseShelf(
                shelf_id=str(pool.get("requirementGroupId") or bucket_id),
                title=str(pool.get("title") or bucket_title),
                kind=POOL,
                requirement_group_id=bucket_id,
                requirement_title=bucket_title,
                credits_remaining=credits_remaining,
                course_numbers=numbers,
            )
            for pool in linked_pools
            if (numbers := _normalized_numbers(pool.get("courseReferences") or [], exclude=completed))
        ]
        shelves.extend(pool_shelves)

        # Nothing enumerable anywhere, but the requirement still wants credits:
        # the candidates are whatever the term offers.
        if not remaining and not pool_shelves and credits_remaining > 0:
            shelves.append(
                CourseShelf(
                    shelf_id=bucket_id,
                    title=bucket_title,
                    kind=OPEN,
                    requirement_group_id=bucket_id,
                    requirement_title=bucket_title,
                    credits_remaining=credits_remaining,
                    course_numbers=(),
                )
            )

    return shelves
