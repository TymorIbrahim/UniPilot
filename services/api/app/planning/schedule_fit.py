"""Can this course join the semester the student is already building?

Why this matters to the shelves
-------------------------------
A course that cannot coexist with what is already in the draft is exactly as
unactionable as one the term does not offer -- and the shelves already filter
that case. Without this, a row can confidently recommend a course that clashes
with the three the student has just picked.

A course clashes only when EVERY arrangement of it clashes
----------------------------------------------------------
Courses run several lecture groups at different hours, plus tutorials and labs.
Rejecting a course because one of its groups overlaps the draft would exclude
nearly everything. The real question is whether some assignment -- one group per
lesson type -- avoids the occupied hours, and that includes not clashing with
ITSELF: a lecture and tutorial scheduled the same hour is not a viable course
even against an empty week.

The search is exact rather than approximate. Lesson types per course are few and
groups per type fewer, so backtracking over them costs nothing, and an
approximation here either hides courses the student could take or offers ones
they cannot.

What a planned course occupies
------------------------------
Only hours it has actually committed to. A planned course whose group the
student has not yet chosen reserves NOTHING: treating each of its alternatives
as occupied would block most of the week on behalf of a decision nobody made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.planning.exam_summary import exams_from_offering
from app.planning.lesson_events import (
    extract_lesson_options_from_offering,
    normalize_lesson_type,
)
from app.planning.prerequisite_resolver import canonical_course_number
from app.planning.weekly_schedule import parse_time_range


@dataclass(frozen=True)
class OccupiedSchedule:
    """The hours and exam days the draft semester has already committed."""

    slots: list[dict[str, Any]] = field(default_factory=list)
    exam_dates: frozenset[str] = frozenset()


def option_slot(option: dict[str, Any]) -> dict[str, Any] | None:
    """A lesson option as a day plus a start/end in minutes, or None."""
    raw = str(option.get("timeRange") or "").replace("–", "-").replace("—", "-")
    parsed = parse_time_range(raw)
    if not option.get("day") or parsed is None:
        return None
    start_minutes, end_minutes = parsed
    return {
        "day": str(option["day"]),
        "startMinutes": start_minutes,
        "endMinutes": end_minutes,
        "courseNumber": str(option.get("courseNumber") or ""),
        "eventId": str(option.get("eventId") or ""),
        "type": str(option.get("type") or "other"),
        "group": option.get("group"),
    }


def _slots_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["day"] != right["day"]:
        return False
    return left["startMinutes"] < right["endMinutes"] and right["startMinutes"] < left["endMinutes"]


def _slots_by_type(
    offering: dict[str, Any] | None,
    *,
    course_number: str,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for option in extract_lesson_options_from_offering(offering, course_number=course_number):
        if option.get("incomplete"):
            continue
        slot = option_slot(option)
        if slot is None:
            continue
        grouped.setdefault(normalize_lesson_type(str(option.get("type") or "other")), []).append(slot)
    return grouped


def build_occupied_schedule(
    offerings_by_number: dict[str, dict[str, Any]],
    *,
    planned_course_numbers: Iterable[str],
) -> OccupiedSchedule:
    """What the draft already commits: fixed hours, and every exam day."""
    planned = {
        number
        for raw in planned_course_numbers
        if (number := canonical_course_number(raw)) is not None
    }

    slots: list[dict[str, Any]] = []
    exam_dates: set[str] = set()
    for number in sorted(planned):
        offering = offerings_by_number.get(number)
        if offering is None:
            continue
        for options in _slots_by_type(offering, course_number=number).values():
            # Only a type with a single possibility is committed; where the
            # student still has a choice, no hour is reserved yet.
            if len(options) == 1:
                slots.append(options[0])
        for exam in exams_from_offering(offering, course_number=number, course_name=""):
            if exam.get("date"):
                exam_dates.add(str(exam["date"]))

    return OccupiedSchedule(slots=slots, exam_dates=frozenset(exam_dates))


def _assignment_exists(
    types: list[list[dict[str, Any]]],
    occupied: list[dict[str, Any]],
    index: int,
    chosen: list[dict[str, Any]],
) -> bool:
    if index == len(types):
        return True
    for candidate in types[index]:
        if any(_slots_overlap(candidate, slot) for slot in occupied):
            continue
        if any(_slots_overlap(candidate, slot) for slot in chosen):
            continue
        chosen.append(candidate)
        if _assignment_exists(types, occupied, index + 1, chosen):
            chosen.pop()
            return True
        chosen.pop()
    return False


def can_schedule_alongside(
    offering: dict[str, Any] | None,
    *,
    course_number: str,
    occupied: OccupiedSchedule,
) -> bool:
    """Whether some arrangement of this course fits the draft semester.

    A course with no published timetable is NOT excluded: the absence of a
    schedule is not evidence of a clash, and hiding the course would be acting
    on a reason that is not true.
    """
    for exam in exams_from_offering(offering, course_number=course_number, course_name=""):
        if exam.get("date") and str(exam["date"]) in occupied.exam_dates:
            return False

    by_type = _slots_by_type(offering, course_number=course_number)
    if not by_type:
        return True

    return _assignment_exists(
        list(by_type.values()), list(occupied.slots), 0, []
    )
