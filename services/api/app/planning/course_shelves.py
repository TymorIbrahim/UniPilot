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
from app.planning.student_affinity import pool_momentum

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
    started_count: int = 0
    pool_size: int = 0

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
            # "3 of 19 taken" -- a share alone cannot tell 1-of-2 from 10-of-20.
            "startedCount": self.started_count,
            "poolSize": self.pool_size,
        }


def rank_choice_courses(
    course_numbers: Iterable[str],
    *,
    ratings: dict[str, dict[str, Any]],
    selectable: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Order a choice shelf: what can be taken now, best-reviewed first.

    `selectable` is the subset the student could actually add to this semester
    -- offered this term and with prerequisites met. Those sort first whatever
    their rating, because a five-star course the student cannot register for is
    not a better suggestion than a three-star course they can. Passing None
    treats every course as selectable.

    Ranking by pass rate is deliberately NOT done. A high pass rate means a
    course is easy, not that it is good, and ordering a menu by easiness is a
    worse recommendation dressed up as a data-driven one -- the same reason
    `outcome_sort_key` is only ever a tie-break in a generated plan. What a
    student choosing freely wants first is what other students thought was
    worth taking, which is `meanGeneralRank`. Pass rate and difficulty belong
    on the card as context.

    Unrated courses keep catalog order and sort after the rated ones rather
    than being scored as if the absence of an opinion were a bad one -- a third
    of the catalog has no rating. They are a trailing group, not a low rank,
    and the caller is expected to present them as such.
    """
    numbers = [
        number
        for raw in course_numbers
        if (number := canonical_course_number(raw)) is not None
    ]
    available = (
        None
        if selectable is None
        else {
            number
            for raw in selectable
            if (number := canonical_course_number(raw)) is not None
        }
    )

    def sort_key(number: str) -> tuple[int, int, float, str]:
        blocked = 0 if available is None or number in available else 1
        rating = ratings.get(number) or {}
        mean_general = rating.get("meanGeneralRank")
        if not isinstance(mean_general, (int, float)) or isinstance(mean_general, bool):
            return (blocked, 1, 0.0, number)
        return (blocked, 0, -float(mean_general), number)

    return tuple(sorted(numbers, key=sort_key))


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

        # A chain the student has already started is the closest thing this data
        # has to "because you watched that", so it leads the bucket's rows.
        # Bucket order itself is left alone: it is the curriculum's own
        # sequence, and reordering it would be a surprise, not a personalisation.
        pool_shelves = []
        for pool in pools_by_bucket.get(bucket_id, []):
            references = pool.get("courseReferences") or []
            numbers = _normalized_numbers(references, exclude=completed)
            if not numbers:
                continue
            started, size = pool_momentum(
                [(reference or {}).get("courseNumber") for reference in references],
                completed=completed,
            )
            pool_shelves.append(
                CourseShelf(
                    shelf_id=str(pool.get("requirementGroupId") or bucket_id),
                    title=str(pool.get("title") or bucket_title),
                    kind=POOL,
                    requirement_group_id=bucket_id,
                    requirement_title=bucket_title,
                    credits_remaining=credits_remaining,
                    course_numbers=numbers,
                    started_count=started,
                    pool_size=size,
                )
            )
        pool_shelves.sort(key=lambda shelf: (-shelf.started_count, shelf.title))
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
