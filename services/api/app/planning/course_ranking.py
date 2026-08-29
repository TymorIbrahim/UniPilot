"""Order the candidate courses on one shelf.

The objective
-------------
Not "what would this student enjoy" -- that is Netflix's question, and Netflix
has no deadline and no constraint. A degree planner is asking what the best use
of this semester's slot is, which makes opportunity cost as much a part of the
answer as preference, and often the larger part.

So ranking runs as filter -> band -> score -> diversify, and every stage is
meant to be legible on the card. A weighted composite would rank marginally
better and could not be explained, and on a decision this consequential an
unexplainable order is worse than a slightly weaker legible one.

Why the rating is shrunk
------------------------
CheeseFork ratings are thin and wildly uneven: 821 rated courses, a median of 8
responses, and 36% with five or fewer. Every one of the ten highest raw means
has six responses or fewer, six of them exactly three. Ranking on the raw mean
therefore selects for SMALL SAMPLES, because that is where extreme means live,
and buries a 4.43 from 136 reviewers under a wall of 5.0s from three.

The standard remedy applies: shrink each mean toward the corpus mean in
proportion to how little evidence stands behind it,

    (v / (v + m)) * R  +  (m / (v + m)) * C

with `m` the median response count. A course with no rating lands exactly on
the corpus mean rather than at the bottom -- a third of the catalog is unrated,
and the absence of an opinion is not a bad opinion.

Why urgency is a count, and what is in it
-----------------------------------------
Three facts about a course change what a semester slot is worth, and none is a
matter of taste:

  closes  -- taking it finishes the requirement outright
  scarce  -- it is one of the 70% offered once a year, so the alternative to
             taking it now is a twelve-month wait
  unlocks -- other courses ON THIS SHELF list it as a prerequisite, so taking a
             leaf before its unlocker wastes the ordering

Urgency is how many of the three hold, not a weighted blend of them. A count
needs no invented coefficients and states itself on the card: "two reasons to
take this now".

`closes` and `scarce` are deadline facts and apply only near the end -- a
student three years out loses almost nothing by deferring a once-a-year course,
so letting scarcity outrank quality there would be wrong. `unlocks` is a
SEQUENCING fact rather than a deadline one: whenever a student means to take
several courses from a chain, the unlocker goes first regardless of how much
runway they have.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from app.planning.prerequisite_resolver import canonical_course_number

PRIOR_RESPONSES = 8
"""Weight of the corpus mean, in units of reviews. The median response count.

Below it small samples still dominate the ordering; above it every course
compresses toward the mean and the ranking starts tracking review count rather
than what reviewers said.
"""

FALLBACK_PRIOR_MEAN = 3.5
"""Corpus mean rating, used when too few ratings are loaded to estimate one."""

MINIMUM_RATINGS_FOR_PRIOR = 30
"""Below this, the sample is not a corpus and the fallback is used instead."""

URGENCY_RUNWAY_CREDITS = 40.0
"""Remaining credits within which scarcity starts to outrank preference.

Roughly two semesters at a typical load. Beyond it a once-a-year course can be
deferred at almost no cost, so quality leads instead.
"""

WELL_REVIEWED_SCORE = 4.0
"""Shrunk score at which a course is worth calling out as well reviewed."""

AFFINITY_SHARE = 0.25
"""Share of a student's own elective choices that marks a faculty as one of theirs.

A quarter of their free choices is enough to be a pattern rather than a single
curiosity, and low enough that a student who spreads across four faculties is
credited with all of them.
"""


@dataclass(frozen=True)
class RankedCourse:
    """One candidate, with why it landed where it did."""

    course_number: str
    score: float
    band: int
    """How many structural reasons favour taking this course now (0-3)."""
    reasons: tuple[str, ...]
    matches_interest: bool = False


def shrunk_rating(
    mean_rank: float | None,
    responses: int | None,
    *,
    prior_mean: float,
    prior_weight: int = PRIOR_RESPONSES,
) -> float:
    """A rating discounted by how little evidence supports it."""
    try:
        observed = float(mean_rank)
        count = int(responses or 0)
    except (TypeError, ValueError):
        return prior_mean
    if count <= 0:
        return prior_mean
    return (count * observed + prior_weight * prior_mean) / (count + prior_weight)


def prior_mean_rating(ratings: dict[str, dict[str, Any]]) -> float:
    """The corpus mean, or the documented fallback when too little is loaded.

    Computed once per request and shared across every shelf, so the same course
    cannot score differently in two rows of the same screen.
    """
    means = [
        float(value)
        for entry in (ratings or {}).values()
        if isinstance(value := (entry or {}).get("meanGeneralRank"), (int, float))
        and not isinstance(value, bool)
    ]
    if len(means) < MINIMUM_RATINGS_FOR_PRIOR:
        return FALLBACK_PRIOR_MEAN
    return sum(means) / len(means)


def _is_once_a_year(course: dict[str, Any]) -> bool:
    terms = [term for term in (course.get("semestersOffered") or []) if term in (200, 201, 202)]
    return len(terms) == 1


def _closes_requirement(course: dict[str, Any], credits_remaining_in_bucket: float) -> bool:
    if credits_remaining_in_bucket <= 0:
        return False
    try:
        credits = float(course.get("credits") or 0.0)
    except (TypeError, ValueError):
        return False
    return credits >= credits_remaining_in_bucket


def rank_candidates(
    courses: Sequence[dict[str, Any]],
    *,
    ratings: dict[str, dict[str, Any]],
    credits_remaining_overall: float,
    credits_remaining_in_bucket: float,
    prior_mean: float | None = None,
    faculty_affinity: dict[str, float] | None = None,
    unlocks_within_shelf: dict[str, int] | None = None,
) -> list[RankedCourse]:
    """Order one shelf's candidates, best use of the slot first.

    `faculty_affinity` is the share of the student's own past elective choices
    going to each faculty. A course from a faculty they keep choosing is more
    relevant to them, so it leads within its band -- this is the one part of the
    ordering that differs between two students looking at the same row.

    Note what is NOT here: how well the student is likely to SCORE. Ranking a
    weak subject down would narrow their degree and entrench the weakness, and
    is the personalised form of ranking by pass rate. Relevance is personalised;
    difficulty is reported (see `student_affinity.describe_readiness`).

    Ordering is total and deterministic: equal band and score fall back to the
    course number, so the same shelf renders identically on every reload.
    """
    prior = FALLBACK_PRIOR_MEAN if prior_mean is None else prior_mean
    urgency_applies = credits_remaining_overall <= URGENCY_RUNWAY_CREDITS

    ranked: list[RankedCourse] = []
    for course in courses:
        number = canonical_course_number(course.get("courseNumber"))
        if number is None:
            continue

        rating = (ratings or {}).get(number) or {}
        score = shrunk_rating(
            rating.get("meanGeneralRank"), rating.get("responseCount"), prior_mean=prior
        )

        reasons: list[str] = []
        closes = _closes_requirement(course, credits_remaining_in_bucket)
        scarce = _is_once_a_year(course)

        unlocks = int((unlocks_within_shelf or {}).get(number, 0))

        urgency = 0
        if urgency_applies and closes:
            urgency += 1
            reasons.append("closes_requirement")
        if urgency_applies and scarce:
            urgency += 1
            reasons.append("offered_once_a_year")
        if unlocks:
            urgency += 1
            reasons.append("unlocks_later_courses")
        if score >= WELL_REVIEWED_SCORE:
            reasons.append("well_reviewed")

        faculty = course.get("faculty")
        matches_interest = bool(
            faculty and (faculty_affinity or {}).get(str(faculty), 0.0) >= AFFINITY_SHARE
        )
        if matches_interest:
            reasons.append("matches_your_electives")

        ranked.append(
            RankedCourse(
                course_number=number,
                score=score,
                band=urgency,
                reasons=tuple(reasons),
                matches_interest=matches_interest,
            )
        )

    ranked.sort(
        key=lambda entry: (
            -entry.band,
            not entry.matches_interest,
            -entry.score,
            entry.course_number,
        )
    )
    return ranked


def diversify_by_faculty(
    courses: Sequence[dict[str, Any]],
    *,
    limit: int,
    per_faculty: int | None,
) -> list[dict[str, Any]]:
    """Trim an already-ordered row so one department cannot fill it.

    Only worth doing where the candidate set is the whole term -- six of the
    eight best-scoring courses in the catalog come from two faculties, and a row
    of 24 that is really three departments is a worse row than one spanning the
    range. Order within what survives is untouched.

    Courses with no recorded faculty are never pooled together: treating
    "unknown" as one department would cap them collectively for a property they
    do not share.
    """
    if per_faculty is None:
        return list(courses)

    seen: dict[str, int] = {}
    kept: list[dict[str, Any]] = []
    for course in courses:
        if len(kept) >= limit:
            break
        faculty = course.get("faculty")
        if faculty:
            key = str(faculty)
            if seen.get(key, 0) >= per_faculty:
                continue
            seen[key] = seen.get(key, 0) + 1
        kept.append(course)
    return kept
