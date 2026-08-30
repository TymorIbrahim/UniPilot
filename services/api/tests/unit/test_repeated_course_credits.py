"""Unit tests for a course legitimately taken more than once.

`03940803` (physical education - ball games) appears twice on a real transcript,
one credit each, both counted in the Technion's stated total of 98 -- the same
activity taken again with a more advanced group. Collapsing it to a single
attempt lost a credit and left the PE requirement showing 1.0 of 2.0.
"""

from __future__ import annotations

from app.services.graduation_progress_calculator import build_effective_completions


PE_PREFIXES = ("039408", "039409")


def _record(course_id, *, attempt, grade, credits, number="03940803", semester="2024-1"):
    return {
        "courseId": course_id,
        "courseNumber": number,
        "attempt": attempt,
        "grade": grade,
        "creditsEarned": credits,
        "semesterCode": semester,
        "metadata": {},
    }


def _effective(records):
    return build_effective_completions(records, repeatable_prefixes=PE_PREFIXES)


def test_two_passing_enrolments_earn_their_credits_twice() -> None:
    records = [
        _record("pe", attempt=1, grade=95.0, credits=1.0, semester="2024-1"),
        _record("pe", attempt=2, grade=96.0, credits=1.0, semester="2024-2"),
    ]

    effective = _effective(records)

    assert len(effective) == 1  # still one course
    assert effective["pe"]["creditsEarned"] == 2.0


def test_a_failed_attempt_adds_nothing() -> None:
    """A retake after a failure is one creditable enrolment, not two."""
    records = [
        _record("pe", attempt=1, grade=40.0, credits=1.0),
        _record("pe", attempt=2, grade=96.0, credits=1.0),
    ]

    assert _effective(records)["pe"]["creditsEarned"] == 1.0


def test_a_course_outside_the_repeatable_pools_is_a_retake() -> None:
    """Passing with 70 and retaking for 82 earns the credits once. Row by row
    this is indistinguishable from the PE case, so the difference has to come
    from the requirement the course serves."""
    records = [
        _record("alg", attempt=1, grade=70.0, credits=3.0, number="02340247"),
        _record("alg", attempt=2, grade=82.0, credits=3.5, number="02340247"),
    ]

    assert _effective(records)["alg"]["creditsEarned"] == 3.5


def test_repeatability_is_read_from_the_catalogue_not_assumed() -> None:
    """With no repeatable pool declared, nothing repeats."""
    records = [
        _record("pe", attempt=1, grade=95.0, credits=1.0),
        _record("pe", attempt=2, grade=96.0, credits=1.0),
    ]

    assert build_effective_completions(records)["pe"]["creditsEarned"] == 1.0


def test_the_reported_grade_is_the_latest_attempt() -> None:
    records = [
        _record("pe", attempt=1, grade=95.0, credits=1.0),
        _record("pe", attempt=2, grade=96.0, credits=1.0),
    ]

    assert _effective(records)["pe"]["grade"] == 96.0


def test_a_single_enrolment_is_unchanged() -> None:
    assert _effective([_record("pe", attempt=1, grade=95.0, credits=1.0)])["pe"][
        "creditsEarned"
    ] == 1.0


def test_a_zero_credit_repeat_adds_nothing() -> None:
    records = [
        _record("pe", attempt=1, grade=95.0, credits=1.0),
        _record("pe", attempt=2, grade=96.0, credits=0.0),
    ]

    assert _effective(records)["pe"]["creditsEarned"] == 1.0
