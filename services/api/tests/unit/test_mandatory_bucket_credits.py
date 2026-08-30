"""Unit tests for reconciling a mandatory bucket's credits."""

from __future__ import annotations

from app.services.graduation_progress_calculator import reconcile_mandatory_bucket_credits


def _entry(credits):
    return {"catalogCredits": credits}


def test_an_unrepresented_slot_cannot_become_progress() -> None:
    """This track requires one further mathematics course chosen from seven, and
    such a slot appears in no remaining-course list. Deriving completion as
    `min - remaining` turned that gap into 10.5 credits the student had not
    earned: 81.0 of 87.0 reported against 70.5 actually assigned.
    """
    completed, remaining, status = reconcile_mandatory_bucket_credits(
        min_credits=87.0,
        completed_courses=[_entry(70.5)],
        remaining_courses=[_entry(3.0), _entry(3.0)],
    )

    assert completed == 70.5
    assert remaining == 16.5
    assert status == "in_progress"


def test_the_derivation_still_applies_when_it_does_not_overstate() -> None:
    """Where the remaining courses do account for the gap, the derived figure
    is the better one -- it credits work the assignment could not place."""
    completed, remaining, _ = reconcile_mandatory_bucket_credits(
        min_credits=87.0,
        completed_courses=[_entry(84.0)],
        remaining_courses=[_entry(3.0)],
    )

    assert completed == 84.0
    assert remaining == 3.0


def test_nothing_remaining_means_the_bucket_is_satisfied() -> None:
    completed, remaining, status = reconcile_mandatory_bucket_credits(
        min_credits=87.0, completed_courses=[_entry(70.5)], remaining_courses=[]
    )

    assert (completed, remaining, status) == (87.0, 0.0, "satisfied")


def test_remaining_courses_with_no_catalogued_credits_fall_back_to_the_sum() -> None:
    completed, remaining, status = reconcile_mandatory_bucket_credits(
        min_credits=87.0,
        completed_courses=[_entry(80.0)],
        remaining_courses=[{"courseNumber": "02360343"}],
    )

    assert completed == 80.0
    assert remaining == 7.0
    assert status == "in_progress"
