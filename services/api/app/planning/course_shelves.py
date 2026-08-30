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
    is_required_pool: bool = False
    """The bucket cannot be satisfied without drawing from this pool."""
    steps_required: int | None = None
    steps_completed: int | None = None
    """For a `choose_n` pool, courses needed rather than credits: a chain asks
    for one course, and reporting its bucket's credits instead says nothing
    about what would finish it."""

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
            "isRequiredPool": self.is_required_pool,
            "stepsRequired": self.steps_required,
            "stepsCompleted": self.steps_completed,
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


def _pool_state(entry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each linked pool's OWN requirement, keyed by its group id.

    A bucket's remainder is not a pool's remainder. Four chains under one bucket
    all reported the bucket's figure, and the science supplement showed the
    bucket's 5.0 credits where the pool itself needs 5.5.
    """
    constraints = entry.get("poolConstraints") or {}
    states: dict[str, dict[str, Any]] = {}
    for pool in constraints.get("allPools") or []:
        group_id = str((pool or {}).get("requirementGroupId") or "")
        if group_id:
            states[group_id] = pool
    for pool in constraints.get("mandatoryPools") or []:
        group_id = str((pool or {}).get("requirementGroupId") or "")
        if not group_id:
            continue
        states.setdefault(group_id, pool)
        # A pool the bucket cannot be satisfied without. When the bucket's
        # credits are already complete this is the ONLY row that can still
        # advance it, and the others cannot contribute at all.
        states[group_id] = {**states[group_id], "isRequired": not pool.get("satisfied", False)}
    return states


def _step_count(state: dict[str, Any] | None, key: str) -> int | None:
    value = (state or {}).get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _pool_credits_remaining(state: dict[str, Any] | None, fallback: float) -> float:
    if not state:
        return fallback
    required = state.get("creditsRequired")
    if not isinstance(required, (int, float)) or isinstance(required, bool):
        return fallback
    completed = state.get("creditsCompleted")
    if not isinstance(completed, (int, float)) or isinstance(completed, bool):
        completed = 0.0
    return max(0.0, float(required) - float(completed))


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
    planned_course_numbers: Iterable[str] = (),
) -> list[CourseShelf]:
    """The rows a student should see, for the requirements they have left.

    Satisfied requirements are omitted: a row for work already done is clutter,
    and the shelf list is meant to be a list of what is still open.

    Courses already in the draft are removed from every row -- offering one the
    student has just added invites planning it twice -- but they do NOT count
    toward a pool's momentum, which measures what has been passed, not what is
    merely intended.
    """
    completed = frozenset(
        number
        for raw in completed_course_numbers
        if (number := canonical_course_number(raw)) is not None
    )
    planned = frozenset(
        number
        for raw in planned_course_numbers
        if (number := canonical_course_number(raw)) is not None
    )
    hidden = completed | planned

    unsatisfied = [
        entry
        for entry in requirement_progress or []
        if entry.get("status") != "satisfied" and entry.get("requirementGroupId")
    ]

    # A course the student must take anyway is not a choice. `00940704` is an
    # outstanding core requirement and also sits in the faculty-elective pool;
    # listed in both it read as something to weigh, when taking it is settled
    # and its credits count once. Obligations win the course, and the choice
    # rows yield it -- the same precedence the auto-planner uses.
    obligations: frozenset[str] = frozenset(
        number
        for entry in unsatisfied
        if str(entry.get("requirementType") or "") in OBLIGATION_REQUIREMENT_TYPES
        for number in _normalized_numbers(entry.get("remainingCourses") or [], exclude=hidden)
    )

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

        names_obligations = (
            str(entry.get("requirementType") or "") in OBLIGATION_REQUIREMENT_TYPES
        )
        remaining = _normalized_numbers(
            entry.get("remainingCourses") or [],
            exclude=hidden if names_obligations else hidden | obligations,
        )
        if remaining:
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
        pool_states = _pool_state(entry)
        pool_shelves = []
        for pool in pools_by_bucket.get(bucket_id, []):
            references = pool.get("courseReferences") or []
            numbers = _normalized_numbers(references, exclude=hidden | obligations)
            if not numbers:
                continue
            started, size = pool_momentum(
                [(reference or {}).get("courseNumber") for reference in references],
                completed=completed,
            )
            pool_id = str(pool.get("requirementGroupId") or bucket_id)
            state = pool_states.get(pool_id)
            pool_shelves.append(
                CourseShelf(
                    shelf_id=pool_id,
                    title=str(pool.get("title") or bucket_title),
                    kind=POOL,
                    requirement_group_id=bucket_id,
                    requirement_title=bucket_title,
                    credits_remaining=_pool_credits_remaining(state, credits_remaining),
                    course_numbers=numbers,
                    started_count=started,
                    pool_size=size,
                    is_required_pool=bool((state or {}).get("isRequired")),
                    steps_required=_step_count(state, "stepsRequired"),
                    steps_completed=_step_count(state, "stepsCompleted"),
                )
            )
        # A pool the bucket cannot be satisfied without leads it, whatever the
        # student has started elsewhere.
        pool_shelves.sort(
            key=lambda shelf: (not shelf.is_required_pool, -shelf.started_count, shelf.title)
        )
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
