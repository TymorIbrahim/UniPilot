"""Unit tests for what taking a course now would open up later.

435 courses offered this term are exactly ONE course away from being available
to one real student. Today they are filtered out and counted, and the course
that would open them gets no credit for it.
"""

from __future__ import annotations

from app.planning.course_unlocking import build_unlock_index


def _course(number, prerequisites_text=None):
    return {"courseNumber": number, "prerequisitesText": prerequisites_text}


class TestBuildUnlockIndex:
    def test_a_course_that_alone_unblocks_another_gets_the_credit(self) -> None:
        index = build_unlock_index(
            [_course("00940222", "00940111")],
            completed=set(),
            relevant={"00940222"},
        )

        assert index["00940111"] == frozenset({"00940222"})

    def test_every_single_course_alternative_counts_as_an_unlocker(self) -> None:
        """"A or B" means taking either one opens it, so both are unlockers."""
        index = build_unlock_index(
            [_course("00940333", "00940111 או 00940222")],
            completed=set(),
            relevant={"00940333"},
        )

        assert index["00940111"] == frozenset({"00940333"})
        assert index["00940222"] == frozenset({"00940333"})

    def test_a_course_still_two_away_unlocks_nothing_yet(self) -> None:
        """Taking one of a conjunction leaves it blocked, so claiming it opens
        the course would be a promise the student cannot cash."""
        index = build_unlock_index(
            [_course("00940333", "00940111 ו-00940222")],
            completed=set(),
            relevant={"00940333"},
        )

        assert index == {}

    def test_partial_progress_brings_a_conjunction_within_reach(self) -> None:
        index = build_unlock_index(
            [_course("00940333", "00940111 ו-00940222")],
            completed={"00940111"},
            relevant={"00940333"},
        )

        assert index["00940222"] == frozenset({"00940333"})

    def test_a_course_the_student_can_already_take_is_not_an_unlock(self) -> None:
        index = build_unlock_index(
            [_course("00940222", "00940111")],
            completed={"00940111"},
            relevant={"00940222"},
        )

        assert index == {}

    def test_only_courses_that_count_toward_something_are_reported(self) -> None:
        """Unlocking a course that advances no outstanding requirement is worth
        nothing, and counting it would flatter a near-graduation student with
        options they have no room left to take."""
        index = build_unlock_index(
            [_course("00940222", "00940111"), _course("00940999", "00940111")],
            completed=set(),
            relevant={"00940222"},
        )

        assert index["00940111"] == frozenset({"00940222"})

    def test_unparseable_prerequisites_contribute_nothing(self) -> None:
        index = build_unlock_index(
            [_course("00940222", "see the faculty handbook")],
            completed=set(),
            relevant={"00940222"},
        )

        assert index == {}

    def test_a_course_with_no_prerequisites_is_not_blocked_by_anything(self) -> None:
        index = build_unlock_index(
            [_course("00940222", None)], completed=set(), relevant={"00940222"}
        )

        assert index == {}
