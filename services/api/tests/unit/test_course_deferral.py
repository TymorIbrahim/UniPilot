"""Unit tests for the cost of postponing a course to a later semester.

A student may legitimately defer a required course -- to lighten a semester, to
retake something, to fit a job. The planner's job is not to stop them but to
price the decision, because the two facts that set the price are ones the
student cannot see: how often the course runs, and how much else waits on it.
"""

from __future__ import annotations

import pytest

from app.planning.course_deferral import (
    SUMMER,
    SPRING,
    WINTER,
    build_dependent_index,
    describe_deferral,
    next_offering,
)


def _course(number, *, offered=None, prerequisites_text=None):
    return {
        "courseNumber": number,
        "semestersOffered": offered if offered is not None else [WINTER, SPRING],
        "prerequisitesText": prerequisites_text,
    }


class TestNextOffering:
    def test_a_course_offered_this_term_is_available_now(self) -> None:
        assert next_offering([WINTER, SPRING], after=(2026, WINTER)) == (2026, SPRING)

    def test_a_winter_only_course_deferred_from_winter_costs_a_full_year(self) -> None:
        """70% of the catalog runs once a year, so "next semester" is usually
        not next semester at all."""
        assert next_offering([WINTER], after=(2026, WINTER)) == (2027, WINTER)

    def test_a_spring_only_course_deferred_from_winter_costs_one_term(self) -> None:
        assert next_offering([SPRING], after=(2026, WINTER)) == (2026, SPRING)

    def test_the_academic_year_rolls_over_after_summer(self) -> None:
        assert next_offering([WINTER], after=(2026, SUMMER)) == (2027, WINTER)

    def test_a_course_offered_every_term_returns_the_very_next_one(self) -> None:
        assert next_offering([WINTER, SPRING, SUMMER], after=(2026, SPRING)) == (2026, SUMMER)

    def test_a_course_with_no_recorded_terms_has_no_known_next_offering(self) -> None:
        """Guessing a date for a course the catalog does not schedule would
        make a deferral look free when its cost is simply unknown."""
        assert next_offering([], after=(2026, WINTER)) is None

    def test_unrecognised_term_codes_are_ignored(self) -> None:
        assert next_offering([999], after=(2026, WINTER)) is None


class TestBuildDependentIndex:
    def test_a_course_named_in_another_prerequisite_gains_a_dependent(self) -> None:
        index = build_dependent_index(
            [
                _course("00940411"),
                _course("00940412", prerequisites_text="00940411"),
            ]
        )

        assert index["00940411"] == frozenset({"00940412"})

    def test_every_branch_of_an_alternative_counts_as_a_dependent(self) -> None:
        """If A satisfies B on its own, deferring A can still block B -- so A
        is a dependency even though it is not the only way in."""
        index = build_dependent_index(
            [
                _course("00940411"),
                _course("00940412"),
                _course("00940423", prerequisites_text="00940411 או 00940412"),
            ]
        )

        assert index["00940411"] == frozenset({"00940423"})
        assert index["00940412"] == frozenset({"00940423"})

    def test_a_course_nothing_depends_on_is_absent(self) -> None:
        index = build_dependent_index([_course("00940411")])

        assert index.get("00940411") is None

    def test_unparseable_prerequisite_text_contributes_no_edges(self) -> None:
        index = build_dependent_index(
            [_course("00940412", prerequisites_text="see the faculty handbook")]
        )

        assert index == {}


class TestDescribeDeferral:
    def test_reports_when_the_next_chance_comes(self) -> None:
        described = describe_deferral(
            _course("00940411", offered=[WINTER]),
            after=(2026, WINTER),
            dependent_index={},
        )

        assert described["nextOffering"] == {"academicYear": 2027, "semesterCode": WINTER}
        assert described["termsUntilNextOffering"] == 3
        assert described["offeredOncePerYear"] is True

    def test_a_course_offered_twice_a_year_is_not_once_a_year(self) -> None:
        described = describe_deferral(
            _course("00940411", offered=[WINTER, SPRING]),
            after=(2026, WINTER),
            dependent_index={},
        )

        assert described["offeredOncePerYear"] is False
        assert described["termsUntilNextOffering"] == 1

    def test_counts_what_waits_on_the_course(self) -> None:
        described = describe_deferral(
            _course("00940411"),
            after=(2026, WINTER),
            dependent_index={"00940411": frozenset({"00940412", "00940423"})},
        )

        assert described["dependentCount"] == 2
        assert described["dependentCourseNumbers"] == ["00940412", "00940423"]

    def test_the_dependent_count_is_marked_as_a_lower_bound(self) -> None:
        """37% of the catalog states no prerequisites at all, so a count of
        zero means "none recorded", not "nothing depends on this"."""
        described = describe_deferral(
            _course("00940411"), after=(2026, WINTER), dependent_index={}
        )

        assert described["dependentCount"] == 0
        assert described["dependentCountIsLowerBound"] is True

    def test_an_unschedulable_course_says_so_rather_than_guessing(self) -> None:
        described = describe_deferral(
            _course("00940411", offered=[]), after=(2026, WINTER), dependent_index={}
        )

        assert described["nextOffering"] is None
        assert described["termsUntilNextOffering"] is None
        assert described["offeredOncePerYear"] is False
