"""Unit tests for operational facts buried in course notes."""

from __future__ import annotations

import pytest

from app.planning.course_notes import requires_manual_registration


@pytest.mark.parametrize(
    "notes",
    [
        "הקורס הינו ברישום ידני באישור המרצה. יש לשלוח מייל בקשה לרישום",
        "רישום ידני במזכירות תחבורה",
        "מקצוע צמוד: 980603 רישום ידני. יש לפנות למרצת הקורס",
        "הרישום לקרוס הינו ידני באישור המרצה.",
    ],
)
def test_manual_registration_is_recognised(notes) -> None:
    """The student cannot enrol through the normal system at all -- planning
    the course without knowing that is how a plan fails to become a timetable."""
    assert requires_manual_registration(notes) is True


@pytest.mark.parametrize(
    "notes",
    [
        None,
        "",
        "ההרצאה בקורס משותפת עם ההרצאה בקורס 460747",
        "מרצה הקourse: יוסי קשת",
    ],
)
def test_ordinary_notes_are_not_flagged(notes) -> None:
    """The rest of the notes are prose about shared lectures and lecturers,
    where a keyword would guess more than it knows."""
    assert requires_manual_registration(notes) is False
