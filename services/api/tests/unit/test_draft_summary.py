"""Unit tests for describing the semester the student is assembling.

Per-course cards answer "should I add this". They cannot answer "is what I have
built sensible", which is the question a student gets wrong most often -- and
the two facts that answer it, difficulty and exam crowding, are invisible until
the whole basket is considered.
"""

from __future__ import annotations

import pytest

from app.planning.draft_summary import build_draft_summary


def _rating(difficulty, responses=20):
    return {"meanDifficultyRank": difficulty, "responseCount": responses}


class TestCredits:
    def test_sums_what_is_planned(self) -> None:
        summary = build_draft_summary(
            [{"courseNumber": "00940111", "credits": 3.5}, {"courseNumber": "00940222", "credits": 2.0}],
            ratings={},
            completed_course_numbers=(),
            exams_by_course={},
        )

        assert summary["plannedCourseCount"] == 2
        assert summary["plannedCredits"] == 5.5

    def test_an_empty_draft_summarises_to_nothing_rather_than_zeroes(self) -> None:
        """A student who has picked nothing has not built a light semester."""
        summary = build_draft_summary(
            [], ratings={}, completed_course_numbers=(), exams_by_course={}
        )

        assert summary["plannedCourseCount"] == 0
        assert summary["difficulty"] is None
        assert summary["exams"] is None


class TestDifficulty:
    def test_compares_the_draft_to_the_student_s_own_history(self) -> None:
        """An absolute difficulty number means little; the useful comparison is
        against what this student has actually carried before."""
        summary = build_draft_summary(
            [{"courseNumber": "00940111", "credits": 3.0}],
            ratings={
                "00940111": _rating(4.5),
                "00949001": _rating(3.0),
                "00949002": _rating(3.0),
            },
            completed_course_numbers=("00949001", "00949002"),
            exams_by_course={},
        )

        assert summary["difficulty"]["plannedMean"] == 4.5
        assert summary["difficulty"]["yourCompletedMean"] == 3.0
        assert summary["difficulty"]["heavierThanUsual"] is True

    def test_a_draft_in_line_with_their_history_is_not_flagged(self) -> None:
        summary = build_draft_summary(
            [{"courseNumber": "00940111", "credits": 3.0}],
            ratings={"00940111": _rating(3.1), "00949001": _rating(3.0)},
            completed_course_numbers=("00949001",),
            exams_by_course={},
        )

        assert summary["difficulty"]["heavierThanUsual"] is False

    def test_coverage_is_reported_so_a_thin_sample_is_visible(self) -> None:
        """Only 31% of the catalog is rated. A mean over one of four courses is
        not a description of the semester."""
        summary = build_draft_summary(
            [
                {"courseNumber": "00940111", "credits": 3.0},
                {"courseNumber": "00940222", "credits": 3.0},
            ],
            ratings={"00940111": _rating(4.5)},
            completed_course_numbers=(),
            exams_by_course={},
        )

        assert summary["difficulty"]["ratedCourses"] == 1
        assert summary["difficulty"]["plannedCourses"] == 2

    def test_no_ratings_at_all_reports_nothing_rather_than_average(self) -> None:
        summary = build_draft_summary(
            [{"courseNumber": "00940111", "credits": 3.0}],
            ratings={},
            completed_course_numbers=(),
            exams_by_course={},
        )

        assert summary["difficulty"] is None

    def test_no_history_leaves_the_comparison_absent_not_zero(self) -> None:
        summary = build_draft_summary(
            [{"courseNumber": "00940111", "credits": 3.0}],
            ratings={"00940111": _rating(4.5)},
            completed_course_numbers=(),
            exams_by_course={},
        )

        assert summary["difficulty"]["yourCompletedMean"] is None
        assert summary["difficulty"]["heavierThanUsual"] is None


class TestExams:
    def test_reports_the_tightest_gap_between_two_exams(self) -> None:
        """Three exams in four days is the avoidable harm students care about
        most, and it is invisible on any single card."""
        summary = build_draft_summary(
            [
                {"courseNumber": "00940111", "credits": 3.0},
                {"courseNumber": "00940222", "credits": 3.0},
                {"courseNumber": "00940333", "credits": 3.0},
            ],
            ratings={},
            completed_course_numbers=(),
            exams_by_course={
                "00940111": ["2026-02-10"],
                "00940222": ["2026-02-11"],
                "00940333": ["2026-03-01"],
            },
        )

        assert summary["exams"]["tightestGapDays"] == 1
        assert summary["exams"]["examCount"] == 3
        assert summary["exams"]["tightestPair"] == ["00940111", "00940222"]

    def test_uses_the_earliest_sitting_of_each_course(self) -> None:
        summary = build_draft_summary(
            [
                {"courseNumber": "00940111", "credits": 3.0},
                {"courseNumber": "00940222", "credits": 3.0},
            ],
            ratings={},
            completed_course_numbers=(),
            exams_by_course={
                "00940111": ["2026-03-20", "2026-02-10"],
                "00940222": ["2026-02-12"],
            },
        )

        assert summary["exams"]["tightestGapDays"] == 2

    def test_one_exam_has_no_gap_to_report(self) -> None:
        summary = build_draft_summary(
            [{"courseNumber": "00940111", "credits": 3.0}],
            ratings={},
            completed_course_numbers=(),
            exams_by_course={"00940111": ["2026-02-10"]},
        )

        assert summary["exams"]["tightestGapDays"] is None
        assert summary["exams"]["examCount"] == 1

    def test_courses_without_a_published_exam_are_counted_separately(self) -> None:
        summary = build_draft_summary(
            [
                {"courseNumber": "00940111", "credits": 3.0},
                {"courseNumber": "00940222", "credits": 3.0},
            ],
            ratings={},
            completed_course_numbers=(),
            exams_by_course={"00940111": ["2026-02-10"]},
        )

        assert summary["exams"]["examCount"] == 1
        assert summary["exams"]["withoutPublishedExam"] == 1

    @pytest.mark.parametrize("bad", [["not-a-date"], [None], []])
    def test_unreadable_exam_dates_are_skipped(self, bad) -> None:
        summary = build_draft_summary(
            [{"courseNumber": "00940111", "credits": 3.0}],
            ratings={},
            completed_course_numbers=(),
            exams_by_course={"00940111": bad},
        )

        assert summary["exams"]["examCount"] == 0
