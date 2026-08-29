"""Tests for the cheesefork semester-offering archive reader."""

from __future__ import annotations

import json

import pytest

from app.sources.cheesefork_archive import (
    ArchiveTerm,
    normalise_course_number,
    normalise_records,
    parse_archive_payload,
)

NUM = "מספר מקצוע"


class TestArchiveTerm:
    def test_index_and_semester_code_track_the_technion_term(self) -> None:
        assert ArchiveTerm(2022, 200).index == 1
        assert ArchiveTerm(2022, 201).index == 2
        assert ArchiveTerm(2022, 202).index == 3
        assert ArchiveTerm(2022, 202).semester_code == "2022-3"

    def test_filename_matches_the_existing_exports(self) -> None:
        assert ArchiveTerm(2025, 201).filename == "courses_2025_201.json"

    def test_the_old_host_index_is_zero_padded(self) -> None:
        """`courses_202203`, not `courses_20223`.

        The unpadded form 404s, and the fetcher reads a 404 as "no archive for
        this term" -- so the whole pre-2023 range looked simply unavailable.
        """
        sap, ug = ArchiveTerm(2022, 202).urls()
        assert sap.endswith("courses_2022_202.min.js")
        assert ug.endswith("courses_202203.min.js")


class TestNormaliseCourseNumber:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("02340114", "02340114"),  # already current
            ("234114", "02340114"),  # legacy 6-digit
            ("324046", "03240046"),  # 6-digit, faculty 324
            ("2340114", "02340114"),  # lost leading zero
            (" 02340114 ", "02340114"),
            (2340114, "02340114"),  # numeric round-trip
        ],
    )
    def test_converts_to_eight_digits(self, raw, expected) -> None:
        assert normalise_course_number(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "abc", "123", "1234567890123"])
    def test_refuses_what_it_cannot_place(self, raw) -> None:
        """A number nothing can join on is worse than an absent one: it matches
        no course anywhere and only inflates the counts."""
        assert normalise_course_number(raw) is None


class TestParseArchivePayload:
    def test_reads_the_bare_array_the_new_host_serves(self) -> None:
        body = 'var courses_from_rishum = [{"general": {"' + NUM + '": "02340114"}}];'
        assert parse_archive_payload(body)[0]["general"][NUM] == "02340114"

    def test_reads_plain_json(self) -> None:
        body = json.dumps([{"general": {NUM: "02340114"}}], ensure_ascii=False)
        assert parse_archive_payload(body)[0]["general"][NUM] == "02340114"

    def test_keeps_hebrew_intact_through_the_javascript_string_literal(self) -> None:
        """The old host wraps its JSON in a single-quoted JS string.

        Decoding that with `unicode_escape` looks right and returns mojibake,
        because the bytes are already UTF-8 -- every Hebrew key and title comes
        back mangled, and the course numbers still parse, so it fails quietly.
        """
        inner = json.dumps(
            [{"general": {NUM: "324046", "שם מקצוע": "ברלין בקולנוע"}}],
            ensure_ascii=False,
        ).replace("'", "\\'")
        body = f"var courses_from_rishum = JSON.parse('{inner}');"

        records = parse_archive_payload(body)

        assert records[0]["general"]["שם מקצוע"] == "ברלין בקולנוע"

    def test_handles_an_escaped_apostrophe_in_a_title(self) -> None:
        inner = json.dumps(
            [{"general": {NUM: "324046", "שם מקצוע": "מבוא ל'הנדסה'"}}],
            ensure_ascii=False,
        ).replace("'", "\\'")
        body = f"var courses_from_rishum = JSON.parse('{inner}');"

        assert parse_archive_payload(body)[0]["general"]["שם מקצוע"] == "מבוא ל'הנדסה'"


class TestNormaliseRecords:
    def test_rewrites_legacy_numbers_and_keeps_everything_else(self) -> None:
        records = normalise_records(
            [{"general": {NUM: "234114", "שם מקצוע": "מבוא"}, "schedule": [{"x": 1}]}]
        )

        assert records[0]["general"][NUM] == "02340114"
        assert records[0]["general"]["שם מקצוע"] == "מבוא"
        assert records[0]["schedule"] == [{"x": 1}]

    def test_drops_a_record_with_no_general_block(self) -> None:
        assert normalise_records([{"schedule": []}]) == []

    def test_drops_a_record_whose_general_is_not_a_mapping(self) -> None:
        assert normalise_records([{"general": "nope"}]) == []

    def test_drops_a_record_whose_number_cannot_be_normalised(self) -> None:
        assert normalise_records([{"general": {NUM: "abc"}}]) == []

    def test_does_not_mutate_the_input(self) -> None:
        source = [{"general": {NUM: "234114"}}]
        normalise_records(source)
        assert source[0]["general"][NUM] == "234114"
