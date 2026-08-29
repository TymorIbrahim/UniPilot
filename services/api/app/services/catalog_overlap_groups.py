"""Catalog overlap rules from Technion semester JSON (מקצועות ללא זיכוי נוסף)."""

from __future__ import annotations

from typing import Any

from app.planning.prerequisite_resolver import extract_course_numbers_from_text
from app.services.completed_course_attempts import latest_attempt_rank
from app.services.course_reference_keys import course_number_keys, merge_overlapping_equivalence_groups


def build_catalog_overlap_conflicts(
    catalog_courses: list[dict[str, Any]],
) -> dict[str, frozenset[str]]:
    """Symmetric adjacency of the pairs `noAdditionalCreditText` actually names.

    "מקצועות ללא זיכוי נוסף" is a PAIRWISE relation, not an equivalence relation:
    it says *these two* courses overlap in content, and it is not transitive.
    Merging it into equivalence groups (which is what `build_catalog_overlap_groups`
    below still does, for a different question) invents conflicts the registrar
    never declared -- two courses that merely share one partner get collapsed into
    a single group, and everything but one member is then stripped of credit.

    Measured on a real transcript: `02340221` names nine partners, `00940219`
    names seven, and NEITHER names the other. They share `02340121`, so closure
    put both in one 29-member group and discarded `02340221` -- 4.0 credits at
    grade 93 -- as a duplicate of a course it does not overlap.

    Symmetric because the catalog states the pair from one side only about half
    the time; if A names B then taking both earns credit once, whichever row the
    text happens to live on.
    """
    conflicts: dict[str, set[str]] = {}

    def link(left: str, right: str) -> None:
        if left == right:
            return
        conflicts.setdefault(left, set()).add(right)
        conflicts.setdefault(right, set()).add(left)

    for course in catalog_courses:
        number = course.get("courseNumber") or course.get("number")
        if number is None:
            continue
        overlap_text = course.get("noAdditionalCreditText")
        if not overlap_text:
            continue

        own_keys = course_number_keys(str(number))
        for overlap_number in extract_course_numbers_from_text(str(overlap_text)):
            partner_keys = course_number_keys(overlap_number)
            for own_key in own_keys:
                for partner_key in partner_keys:
                    link(own_key, partner_key)

    return {key: frozenset(partners) for key, partners in conflicts.items()}


def serialize_catalog_overlap_conflicts(
    conflicts: dict[str, frozenset[str]],
) -> list[list[str]]:
    """Conflicts as `string[][]` for the web, one group per course plus its partners.

    Deliberately NOT the transitive closure. Clients union the groups that touch
    a course they care about, which reproduces exactly the pairs the catalog
    names; emitting merged groups here would push the closure bug into the UI's
    equivalence matching as well.
    """
    seen: set[tuple[str, ...]] = set()
    serialized: list[list[str]] = []
    for key in sorted(conflicts):
        group = tuple(sorted({key, *conflicts[key]}))
        if len(group) < 2 or group in seen:
            continue
        seen.add(group)
        serialized.append(list(group))
    return serialized


def conflicts_for_course(
    course_number: str | None,
    conflicts: dict[str, frozenset[str]],
) -> frozenset[str]:
    """Course-number keys that the catalog says share credit with this course."""
    if not course_number or not conflicts:
        return frozenset()

    partners: set[str] = set()
    for key in course_number_keys(str(course_number)):
        partners |= conflicts.get(key, frozenset())
    return frozenset(partners)


def build_catalog_overlap_groups(catalog_courses: list[dict[str, Any]]) -> list[set[str]]:
    """Coarse substitution groups from noAdditionalCreditText.

    Deliberately still merged, and deliberately NOT what decides credit. This
    answers "might these course numbers be filling the same slot?" for pool
    matching and for drawing the curriculum graph, where over-grouping costs a
    slightly generous match. `build_catalog_overlap_conflicts` answers "does the
    registrar say these two overlap?", which is what credit turns on -- see the
    note there for why the two must not be the same function.
    """
    groups: list[set[str]] = []
    for course in catalog_courses:
        number = course.get("courseNumber") or course.get("number")
        if number is None:
            continue
        overlap_text = course.get("noAdditionalCreditText")
        if not overlap_text:
            continue

        members = set(course_number_keys(str(number)))
        for overlap_number in extract_course_numbers_from_text(str(overlap_text)):
            members |= course_number_keys(overlap_number)

        if len(members) > 1:
            groups.append(members)

    return merge_overlapping_equivalence_groups(groups)


def collect_overlap_partner_numbers(catalog_courses: list[dict[str, Any]]) -> set[str]:
    """Course numbers referenced in noAdditionalCreditText for loaded catalog rows."""
    partners: set[str] = set()
    for course in catalog_courses:
        overlap_text = course.get("noAdditionalCreditText")
        if not overlap_text:
            continue
        for number in extract_course_numbers_from_text(str(overlap_text)):
            partners |= course_number_keys(number)
    return partners


def expand_keys_with_equivalence(
    keys: set[str],
    equivalence_groups: list[set[str]],
) -> set[str]:
    """Union all equivalence groups that intersect the given course-number keys."""
    if not keys or not equivalence_groups:
        return set(keys)

    expanded = set(keys)
    for group in equivalence_groups:
        if expanded & group:
            expanded |= group
    return expanded


def overlap_group_for_course(
    course_number: str | None,
    overlap_groups: list[set[str]],
) -> frozenset[str] | None:
    if not course_number or not overlap_groups:
        return None
    keys = course_number_keys(course_number)
    for group in overlap_groups:
        if keys & group:
            return frozenset(group)
    return None


def _completion_precedence_key(
    completion: dict[str, Any],
    *,
    recorded_at_timestamp,
) -> tuple[int, float, str]:
    """Latest completion wins within a catalog overlap group (not max credits)."""
    return latest_attempt_rank(
        attempt=int(completion.get("attempt") or 1),
        recorded_at_timestamp=recorded_at_timestamp(completion.get("recordedAt")),
        semester_code=str(completion.get("semesterCode") or ""),
    )


def exclude_overlap_duplicate_credits(
    effective_completions: dict[str, dict[str, Any]],
    catalog_courses_by_id: dict[str, dict[str, Any]],
    conflicts: dict[str, frozenset[str]],
    *,
    recorded_at_timestamp,
) -> set[str]:
    """Course ids that earn no additional credit because a course they overlap already did.

    Walks the student's own courses newest-first and keeps each one unless it
    conflicts -- by a pair the catalog actually names -- with one already kept.
    That is a greedy maximal independent set over the conflict graph restricted
    to this transcript, which for the shapes that occur here (a handful of
    courses, usually one declared pair) is also the maximum: it never drops a
    course that had no kept conflict, which is the failure the previous
    group-based version produced.

    Newest-first because the later attempt is the one the registrar shows, which
    is `_completion_precedence_key`'s existing rule; keeping it means a retake
    still supersedes the course it replaces.
    """
    if not conflicts:
        return set()

    id_to_keys: dict[str, set[str]] = {}
    for course_id in effective_completions:
        catalog_course = catalog_courses_by_id.get(course_id)
        if not catalog_course:
            continue
        number = catalog_course.get("courseNumber") or catalog_course.get("number")
        if number is None:
            continue
        id_to_keys[course_id] = course_number_keys(str(number))

    ordered = sorted(
        (course_id for course_id in effective_completions if course_id in id_to_keys),
        key=lambda course_id: (
            _completion_precedence_key(
                effective_completions[course_id],
                recorded_at_timestamp=recorded_at_timestamp,
            ),
            course_id,
        ),
        reverse=True,
    )

    kept_keys: set[str] = set()
    excluded_ids: set[str] = set()
    for course_id in ordered:
        own_keys = id_to_keys[course_id]
        partner_keys: set[str] = set()
        for key in own_keys:
            partner_keys |= conflicts.get(key, frozenset())

        if partner_keys & kept_keys:
            excluded_ids.add(course_id)
            continue

        kept_keys |= own_keys

    return excluded_ids
