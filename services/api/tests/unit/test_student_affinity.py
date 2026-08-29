"""Unit tests for what a student's own record says about relevance.

The profile carries no stated interests -- `preferences` is empty for real
students -- so everything here is derived from what they have actually done.
"""

from __future__ import annotations

import pytest

from app.planning.student_affinity import (
    build_elective_affinity,
    describe_readiness,
    pool_momentum,
)


class TestBuildElectiveAffinity:
    def test_weights_the_faculties_a_student_chose_for_themselves(self) -> None:
        progress = [
            {
                "requirementType": "elective",
                "completedCourses": [{"courseNumber": "00320001"}, {"courseNumber": "00320002"}],
            },
            {
                "requirementType": "enrichment",
                "completedCourses": [{"courseNumber": "00940001"}],
            },
        ]
        faculties = {
            "00320001": "Humanities",
            "00320002": "Humanities",
            "00940001": "Data Science",
        }

        affinity = build_elective_affinity(progress, faculties_by_number=faculties)

        assert affinity["Humanities"] == pytest.approx(2 / 3)
        assert affinity["Data Science"] == pytest.approx(1 / 3)

    def test_required_courses_say_nothing_about_taste(self) -> None:
        """A student did not choose their core courses, so counting them
        measures what the degree demanded, not what they prefer."""
        progress = [
            {
                "requirementType": "core",
                "completedCourses": [{"courseNumber": f"0094000{i}"} for i in range(30)],
            },
            {
                "requirementType": "elective",
                "completedCourses": [{"courseNumber": "00320001"}],
            },
        ]
        faculties = {f"0094000{i}": "Data Science" for i in range(30)}
        faculties["00320001"] = "Humanities"

        affinity = build_elective_affinity(progress, faculties_by_number=faculties)

        assert affinity == {"Humanities": 1.0}

    def test_a_student_with_no_free_choices_yet_has_no_affinity(self) -> None:
        progress = [{"requirementType": "core", "completedCourses": [{"courseNumber": "00940001"}]}]

        assert build_elective_affinity(progress, faculties_by_number={}) == {}

    def test_courses_with_no_known_faculty_are_skipped(self) -> None:
        progress = [
            {"requirementType": "elective", "completedCourses": [{"courseNumber": "00940001"}]}
        ]

        assert build_elective_affinity(progress, faculties_by_number={}) == {}


class TestPoolMomentum:
    def test_counts_what_the_student_has_already_taken_from_a_pool(self) -> None:
        assert pool_momentum(
            ["00960235", "00960222", "00970222"], completed={"00960235", "00970222"}
        ) == (2, 3)

    def test_a_pool_they_have_not_started_has_no_momentum(self) -> None:
        assert pool_momentum(["00960235"], completed=set()) == (0, 1)

    def test_an_empty_pool_is_not_a_division_by_zero(self) -> None:
        assert pool_momentum([], completed={"00960235"}) == (0, 0)

    def test_course_numbers_are_normalised_on_both_sides(self) -> None:
        assert pool_momentum(["960235"], completed={"00960235"}) == (1, 1)


class TestDescribeReadiness:
    def test_reports_a_prerequisite_the_student_barely_passed(self) -> None:
        """A course whose prerequisite they scraped is a specific, structural
        risk -- unlike a general "you find this subject hard", which is not a
        reason to steer anyone away."""
        readiness = describe_readiness(
            "00940411 ו-00940412", grades={"00940411": 92.0, "00940412": 57.0}
        )

        assert readiness["weakestPrerequisiteGrade"] == 57.0
        assert readiness["weakestPrerequisiteCourse"] == "00940412"

    def test_a_comfortably_prepared_student_gets_the_strong_grade(self) -> None:
        readiness = describe_readiness("00940411", grades={"00940411": 92.0})

        assert readiness["weakestPrerequisiteGrade"] == 92.0

    def test_only_prerequisites_the_student_actually_took_are_considered(self) -> None:
        """An alternative they did not take is not evidence of anything."""
        readiness = describe_readiness(
            "00940411 או 00940412", grades={"00940412": 61.0}
        )

        assert readiness["weakestPrerequisiteCourse"] == "00940412"

    def test_a_course_with_no_prerequisites_has_nothing_to_report(self) -> None:
        assert describe_readiness(None, grades={}) is None

    def test_unparseable_prerequisite_text_reports_nothing(self) -> None:
        assert describe_readiness("see the faculty handbook", grades={}) is None

    def test_prerequisites_with_no_recorded_grade_report_nothing(self) -> None:
        assert describe_readiness("00940411", grades={}) is None
