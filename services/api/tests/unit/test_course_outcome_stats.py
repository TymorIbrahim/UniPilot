"""Tests for per-course outcome statistics."""

from __future__ import annotations

from app.services.course_outcome_stats import (
    MINIMUM_COHORT,
    build_course_outcomes,
    outcome_sort_key,
)


def _row(number: str, grade: float, **metadata) -> dict:
    return {
        "courseNumber": number,
        "grade": grade,
        "metadata": {"importedCourseNumber": number, **metadata},
    }


def test_aggregates_mean_and_pass_rate_over_a_cohort() -> None:
    records = [_row("00940224", g) for g in (90, 80, 70, 60, 50)]

    outcome = build_course_outcomes(records)["00940224"]

    assert outcome.sample_size == 5
    assert outcome.mean_grade == 70.0
    assert outcome.pass_rate == 0.8  # 50 is below the pass mark of 55
    assert outcome.is_demanding is True


def test_a_course_everyone_passes_is_not_demanding() -> None:
    outcome = build_course_outcomes([_row("00940345", g) for g in (95, 90, 85, 80, 75)])[
        "00940345"
    ]
    assert outcome.pass_rate == 1.0
    assert outcome.is_demanding is False


def test_a_cohort_too_small_to_publish_is_dropped() -> None:
    """These are real students' grades: with two rows, anyone holding one can
    derive the other, so a small cohort is withheld rather than rounded."""
    records = [_row("00940224", g) for g in (90, 80, 70, 60)]

    assert build_course_outcomes(records) == {}
    assert len(records) == MINIMUM_COHORT - 1


def test_failed_attempts_count_toward_the_statistics() -> None:
    """Dropping them is exactly what makes a hard course look easy."""
    records = [_row("01040166", g) for g in (30, 40, 60, 70, 80)]

    outcome = build_course_outcomes(records)["01040166"]

    assert outcome.sample_size == 5
    assert outcome.pass_rate == 0.6
    assert outcome.mean_grade == 56.0


def test_exemptions_and_pass_fail_rows_are_excluded() -> None:
    """They carry a sentinel grade, not a score -- averaging them in would
    report a difficulty that nobody experienced."""
    records = [_row("03240033", g) for g in (90, 80, 70, 60, 75)]
    records.append(_row("03240033", 0.0, exemption=True))
    records.append(_row("03240033", 56.0, passGrade=True))

    outcome = build_course_outcomes(records)["03240033"]

    assert outcome.sample_size == 5
    assert outcome.mean_grade == 75.0


def test_a_row_with_no_course_number_is_ignored() -> None:
    assert build_course_outcomes([{"grade": 90, "metadata": {}}]) == {}


def test_a_row_with_a_non_numeric_grade_is_ignored() -> None:
    records = [_row("00940224", g) for g in (90, 80, 70, 60, 55)]
    records.append({"courseNumber": "00940224", "grade": "not-a-grade", "metadata": {}})

    assert build_course_outcomes(records)["00940224"].sample_size == 5


def test_public_dict_rounds_and_never_carries_a_single_grade() -> None:
    outcome = build_course_outcomes([_row("00940224", g) for g in (91, 82, 73, 64, 55)])[
        "00940224"
    ]

    payload = outcome.as_public_dict()

    assert payload == {
        "courseNumber": "00940224",
        "sampleSize": 5,
        "meanGrade": 73.0,
        "passRate": 1.0,
        "isDemanding": False,
    }
    assert "grades" not in payload


class TestOutcomeSortKey:
    def test_a_course_with_no_statistics_is_never_pushed_down(self) -> None:
        """Coverage is thin, so an unknown course must not rank below a known
        one -- otherwise the whole catalog sinks beneath a handful of courses."""
        outcomes = build_course_outcomes([_row("00940224", g) for g in (90, 80, 70, 60, 50)])

        assert outcome_sort_key("00000000", outcomes) < outcome_sort_key("00940224", outcomes)
        assert outcome_sort_key(None, outcomes) == (0, 0.0, 0.0)

    def test_between_two_known_courses_the_safer_one_sorts_first(self) -> None:
        records = [_row("00940345", g) for g in (95, 90, 85, 80, 75)]
        records += [_row("01040166", g) for g in (30, 40, 60, 70, 80)]
        outcomes = build_course_outcomes(records)

        assert outcome_sort_key("00940345", outcomes) < outcome_sort_key("01040166", outcomes)
