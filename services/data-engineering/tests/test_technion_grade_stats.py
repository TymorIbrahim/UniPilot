"""Tests for the published Technion grade-statistics reader."""

from __future__ import annotations

import pytest

from app.sources.technion_grade_stats import (
    index_url,
    parse_course_index,
    parse_term_section,
    select_course_section,
)


def _section(students=100, pass_fail="90/10", minimum="20", maximum="100",
             average="75.5", median="78"):
    return {
        "students": str(students),
        "passFail": pass_fail,
        "passPercent": "90",
        "min": minimum,
        "max": maximum,
        "average": average,
        "median": median,
    }


class TestParseTermSection:
    def test_reads_the_published_fields(self) -> None:
        stats = parse_term_section("202501", _section())

        assert stats is not None
        assert (stats.students, stats.passed, stats.failed) == (100, 90, 10)
        assert (stats.minimum, stats.maximum) == (20.0, 100.0)
        assert (stats.average, stats.median) == (75.5, 78.0)
        assert stats.pass_rate == 0.9

    def test_values_arrive_as_strings_and_are_converted(self) -> None:
        """Skipping the conversion sorts and averages them as text."""
        stats = parse_term_section("202501", _section(average="70.545"))
        assert isinstance(stats.average, float)
        assert stats.average == 70.545

    @pytest.mark.parametrize(
        "override",
        [
            {"passFail": "not-a-ratio"},
            {"students": ""},
            {"average": "n/a"},
            {"median": None},
            {"min": "abc"},
            {"max": None},
        ],
    )
    def test_a_partial_row_is_dropped_not_defaulted(self, override) -> None:
        """A zero minimum or absent cohort would pass through the pooling and
        quietly bias everything computed from it."""
        section = {**_section(), **override}
        assert parse_term_section("202501", section) is None

    def test_a_cohort_of_zero_is_dropped(self) -> None:
        assert parse_term_section("202501", _section(students=0)) is None

    def test_a_non_mapping_section_is_dropped(self) -> None:
        assert parse_term_section("202501", "nope") is None


class TestSelectCourseSection:
    def test_prefers_the_combined_final_over_a_single_sitting(self) -> None:
        block = {"Finals": _section(), "Final_A": _section(), "Exam_A": _section()}
        assert select_course_section(block)[0] == "Finals"

    def test_falls_back_to_the_first_sitting_when_there_is_no_combined_figure(self) -> None:
        assert select_course_section({"Final_A": _section(), "Exam_A": _section()})[0] == "Final_A"

    def test_never_selects_an_exam_only_section(self) -> None:
        """`Exam_A` is the exam alone; the course grade includes coursework.

        Measured on one real term: 70.5 for the exam against 77.7 for the
        course, so reading the exam reports a harsher course than students sat.
        """
        assert select_course_section({"Exam_A": _section(), "Exam_B": _section()}) is None

    def test_a_term_with_only_staff_yields_nothing(self) -> None:
        assert select_course_section({"Staff": [{"name": "x"}]}) is None
        assert select_course_section("nope") is None


class TestParseCourseIndex:
    def test_pools_terms_weighted_by_cohort_size(self) -> None:
        """A 10-student summer sitting must not move the mean like a 200-student
        winter one."""
        document = {
            "202401": {"Finals": _section(students=200, average="80", median="82")},
            "202403": {"Finals": _section(students=10, average="50", median="50")},
        }

        stats = parse_course_index(document, course_number="00940224")

        assert stats.term_count == 2
        assert stats.students == 210
        assert stats.average == pytest.approx((80 * 200 + 50 * 10) / 210)
        assert stats.average > 78  # not the naive (80+50)/2 = 65

    def test_min_and_max_span_every_term(self) -> None:
        document = {
            "202401": {"Finals": _section(minimum="40", maximum="95")},
            "202402": {"Finals": _section(minimum="12", maximum="100")},
        }

        stats = parse_course_index(document, course_number="00940224")

        assert (stats.minimum, stats.maximum) == (12.0, 100.0)

    def test_passed_and_failed_accumulate(self) -> None:
        document = {
            "202401": {"Finals": _section(students=100, pass_fail="90/10")},
            "202402": {"Finals": _section(students=50, pass_fail="40/10")},
        }

        stats = parse_course_index(document, course_number="00940224")

        assert (stats.passed, stats.failed) == (130, 20)
        assert stats.pass_rate == pytest.approx(130 / 150)

    def test_terms_without_usable_statistics_are_skipped(self) -> None:
        document = {
            "202401": {"Finals": _section()},
            "202402": {"Staff": [{"name": "x"}]},
            "202403": {"Finals": {"students": "oops"}},
        }

        assert parse_course_index(document, course_number="00940224").term_count == 1

    def test_a_course_with_nothing_usable_returns_none(self) -> None:
        assert parse_course_index({}, course_number="00940224") is None
        assert parse_course_index("nope", course_number="00940224") is None
        assert parse_course_index({"202401": {"Staff": []}}, course_number="00940224") is None

    def test_public_dict_names_the_median_for_what_it_is(self) -> None:
        """A true pooled median needs the underlying grades, which are not
        published -- so the field says it is the mean of term medians."""
        document = {
            "202401": {"Finals": _section(students=100, median="80")},
            "202402": {"Finals": _section(students=100, median="70")},
        }

        payload = parse_course_index(document, course_number="00940224").as_public_dict()

        assert payload["medianOfTermMedians"] == 75.0
        assert "median" not in payload
        assert payload["source"] == "technion-histograms"
        assert payload["students"] == 200


def test_index_url_points_at_the_published_branch() -> None:
    assert index_url("00940224").endswith("/gh-pages/00940224/index.json")
