"""Unit tests for whether a candidate course can join a draft semester.

A course that cannot coexist with what the student has already picked is
exactly as unactionable as one the term does not offer -- and the shelves
already filter that case.
"""

from __future__ import annotations

from app.planning.schedule_fit import (
    build_occupied_schedule,
    can_schedule_alongside,
    option_slot,
)


def _group(day, time_range, *, type_="lecture", group="10"):
    return {
        "day": day,
        "time": time_range,
        "type": type_,
        "group": group,
    }


def _offering(number, groups, *, exams=None):
    return {
        "courseNumber": number,
        "academicYear": 2025,
        "semesterCode": 200,
        "scheduleGroups": groups,
        "examDates": exams or {},
    }


class TestOptionSlot:
    def test_reads_a_day_and_time_range_into_minutes(self) -> None:
        slot = option_slot({"day": "Sunday", "timeRange": "10:30-12:30"})

        assert slot["day"] == "Sunday"
        assert (slot["startMinutes"], slot["endMinutes"]) == (630, 750)

    def test_an_option_with_no_usable_time_has_no_slot(self) -> None:
        assert option_slot({"day": "Sunday", "timeRange": ""}) is None
        assert option_slot({"day": None, "timeRange": "10:30-12:30"}) is None


class TestCanScheduleAlongside:
    def test_an_empty_draft_conflicts_with_nothing(self) -> None:
        occupied = build_occupied_schedule({}, planned_course_numbers=set())

        assert can_schedule_alongside(
            _offering("00940111", [_group("Sunday", "10:30-12:30")]),
            course_number="00940111",
            occupied=occupied,
        ) is True

    def test_a_course_whose_only_group_clashes_is_rejected(self) -> None:
        offerings = {"00940222": _offering("00940222", [_group("Sunday", "10:30-12:30")])}
        occupied = build_occupied_schedule(offerings, planned_course_numbers={"00940222"})

        assert can_schedule_alongside(
            _offering("00940111", [_group("Sunday", "11:30-13:30")]),
            course_number="00940111",
            occupied=occupied,
        ) is False

    def test_a_second_group_at_another_time_rescues_the_course(self) -> None:
        """Most courses run several lecture groups. Rejecting a course because
        ONE of its groups clashes would exclude nearly everything."""
        offerings = {"00940222": _offering("00940222", [_group("Sunday", "10:30-12:30")])}
        occupied = build_occupied_schedule(offerings, planned_course_numbers={"00940222"})

        candidate = _offering(
            "00940111",
            [
                _group("Sunday", "11:30-13:30", group="10"),
                _group("Tuesday", "09:30-11:30", group="20"),
            ],
        )

        assert can_schedule_alongside(
            candidate, course_number="00940111", occupied=occupied
        ) is True

    def test_every_lesson_type_must_find_a_free_slot(self) -> None:
        """A free lecture is no use if the only tutorial clashes."""
        offerings = {"00940222": _offering("00940222", [_group("Monday", "10:30-12:30")])}
        occupied = build_occupied_schedule(offerings, planned_course_numbers={"00940222"})

        candidate = _offering(
            "00940111",
            [
                _group("Sunday", "09:30-11:30", type_="lecture"),
                _group("Monday", "10:30-12:30", type_="tutorial"),
            ],
        )

        assert can_schedule_alongside(
            candidate, course_number="00940111", occupied=occupied
        ) is False

    def test_the_chosen_groups_must_not_clash_with_each_other(self) -> None:
        """Checking each type against the draft alone would accept a course
        whose own lecture and tutorial run at the same hour."""
        occupied = build_occupied_schedule({}, planned_course_numbers=set())

        candidate = _offering(
            "00940111",
            [
                _group("Sunday", "10:30-12:30", type_="lecture", group="10"),
                _group("Sunday", "10:30-12:30", type_="tutorial", group="20"),
            ],
        )

        assert can_schedule_alongside(
            candidate, course_number="00940111", occupied=occupied
        ) is False

    def test_a_course_with_no_published_schedule_is_not_excluded(self) -> None:
        """Absence of a timetable is not evidence of a clash, and refusing to
        show the course would hide it for a reason that is not true."""
        occupied = build_occupied_schedule({}, planned_course_numbers=set())

        assert can_schedule_alongside(
            _offering("00940111", []), course_number="00940111", occupied=occupied
        ) is True


class TestExamConflicts:
    def test_two_courses_examined_the_same_day_conflict(self) -> None:
        offerings = {
            "00940222": _offering(
                "00940222", [_group("Sunday", "10:30-12:30")], exams={"מועד א": "2026-02-10"}
            )
        }
        occupied = build_occupied_schedule(offerings, planned_course_numbers={"00940222"})

        candidate = _offering(
            "00940111", [_group("Tuesday", "09:30-11:30")], exams={"מועד א": "2026-02-10"}
        )

        assert can_schedule_alongside(
            candidate, course_number="00940111", occupied=occupied
        ) is False

    def test_different_exam_days_are_fine(self) -> None:
        offerings = {
            "00940222": _offering(
                "00940222", [_group("Sunday", "10:30-12:30")], exams={"מועד א": "2026-02-10"}
            )
        }
        occupied = build_occupied_schedule(offerings, planned_course_numbers={"00940222"})

        candidate = _offering(
            "00940111", [_group("Tuesday", "09:30-11:30")], exams={"מועד א": "2026-02-17"}
        )

        assert can_schedule_alongside(
            candidate, course_number="00940111", occupied=occupied
        ) is True


class TestBuildOccupiedSchedule:
    def test_only_planned_courses_occupy_the_week(self) -> None:
        offerings = {
            "00940222": _offering("00940222", [_group("Sunday", "10:30-12:30")]),
            "00940333": _offering("00940333", [_group("Monday", "10:30-12:30")]),
        }

        occupied = build_occupied_schedule(offerings, planned_course_numbers={"00940222"})

        assert [slot["day"] for slot in occupied.slots] == ["Sunday"]

    def test_a_planned_course_with_alternative_groups_reserves_none_of_them(self) -> None:
        """Until the student picks a group, no single hour is committed --
        treating every alternative as occupied would block the whole week."""
        offerings = {
            "00940222": _offering(
                "00940222",
                [_group("Sunday", "10:30-12:30", group="10"), _group("Monday", "10:30-12:30", group="20")],
            )
        }

        occupied = build_occupied_schedule(offerings, planned_course_numbers={"00940222"})

        assert occupied.slots == []
