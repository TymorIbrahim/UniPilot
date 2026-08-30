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

Only moed A collides
--------------------
Every offering publishes two sittings. Moed B is the retake, sat only by a
student who failed or deferred moed A, so two courses sharing a moed B date
collide only for someone who fails both. Treating that as a clash excluded 22
of 67 candidates in one measured draft -- a third of the exclusions -- for an
event that mostly does not happen. Moed A collisions are real and filter; moed
B collisions are reported and left to the student.
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
    """Moed A days only -- the sitting every student takes."""
    retake_dates: frozenset[str] = frozenset()
    """Moed B days, reported rather than filtered on."""


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
    retake_dates: set[str] = set()
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
            if not exam.get("date"):
                continue
            target = retake_dates if str(exam.get("moed") or "") == "B" else exam_dates
            target.add(str(exam["date"]))

    return OccupiedSchedule(
        slots=slots,
        exam_dates=frozenset(exam_dates),
        retake_dates=frozenset(retake_dates),
    )


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


def retake_clashes(
    offering: dict[str, Any] | None,
    *,
    course_number: str,
    occupied: OccupiedSchedule,
) -> bool:
    """Whether this course's moed B falls on a planned course's moed B.

    Reported, not filtered on: it costs the student nothing unless they fail
    both sittings, and that is their judgement to make.
    """
    for exam in exams_from_offering(offering, course_number=course_number, course_name=""):
        if str(exam.get("moed") or "") != "B":
            continue
        if exam.get("date") and str(exam["date"]) in occupied.retake_dates:
            return True
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
        if str(exam.get("moed") or "") == "B":
            continue  # a retake clash only bites a student who fails both
        if exam.get("date") and str(exam["date"]) in occupied.exam_dates:
            return False

    by_type = _slots_by_type(offering, course_number=course_number)
    if not by_type:
        return True

    return _assignment_exists(
        list(by_type.values()), list(occupied.slots), 0, []
    )
