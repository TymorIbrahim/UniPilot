"""Unit tests for keeping other degree levels off a student's rows."""

from __future__ import annotations

import pytest

from app.planning.study_level import (
    GRADUATE,
    PRE_ACADEMIC,
    SHARED,
    UNDERGRADUATE,
    allowed_frameworks,
    is_appropriate_level,
)


def _allowed(program_type):
    return allowed_frameworks(program_type)


class TestAllowedFrameworks:
    @pytest.mark.parametrize("raw", ["BSc", "bsc", " BSC "])
    def test_the_program_type_is_read_case_insensitively(self, raw) -> None:
        assert _allowed(raw) == frozenset({UNDERGRADUATE, SHARED})

    def test_a_graduate_student_keeps_undergraduate_courses(self) -> None:
        """MSc and PhD students routinely take undergraduate courses as
        completion requirements, so the restriction is not symmetric."""
        assert UNDERGRADUATE in _allowed("MSc")
        assert UNDERGRADUATE in _allowed("PhD")

    def test_no_level_means_no_restriction(self) -> None:
        assert _allowed(None) is None
        assert _allowed("") is None

    def test_an_unrecognised_level_means_no_restriction(self) -> None:
        """Hiding courses on the strength of a value we do not recognise is a
        worse error than showing one too many."""
        assert _allowed("Diploma") is None


class TestIsAppropriateLevel:
    def test_an_undergraduate_is_not_offered_a_graduate_course(self) -> None:
        assert is_appropriate_level(GRADUATE, allowed=_allowed("BSc")) is False

    def test_an_undergraduate_keeps_shared_and_undergraduate_courses(self) -> None:
        assert is_appropriate_level(UNDERGRADUATE, allowed=_allowed("BSc")) is True
        assert is_appropriate_level(SHARED, allowed=_allowed("BSc")) is True

    def test_pre_academic_courses_belong_to_no_degree(self) -> None:
        """Remedial preparation for university, counting toward nothing."""
        for level in ("BSc", "MSc", "PhD"):
            assert is_appropriate_level(PRE_ACADEMIC, allowed=_allowed(level)) is False

    def test_a_graduate_student_may_be_offered_a_graduate_course(self) -> None:
        assert is_appropriate_level(GRADUATE, allowed=_allowed("MSc")) is True

    def test_a_course_that_does_not_say_what_it_is_is_kept(self) -> None:
        assert is_appropriate_level(None, allowed=_allowed("BSc")) is True
        assert is_appropriate_level("  ", allowed=_allowed("BSc")) is True

    def test_no_restriction_keeps_everything(self) -> None:
        assert is_appropriate_level(GRADUATE, allowed=None) is True
