"""Unit tests for transcript review service."""

from __future__ import annotations

import pytest

from app.services.transcript_review_service import (
    _existing_signatures,
    _grade_key,
    build_transcript_review,
    review_rows_for_commit,
)
from tests.fixtures.completed_course_fixtures import seed_production_course_fixture


def test_grade_key_normalizes_decimal_and_non_numeric_grades():
    assert _grade_key(85.5) == "85.5"
    assert _grade_key("עבר") == "עבר"


def test_existing_signatures_skips_records_missing_course_id_or_semester():
    assert _existing_signatures([{"courseId": "", "semesterCode": "2024-1", "grade": 90}]) == set()
    assert _existing_signatures([{"courseId": "abc", "semesterCode": "", "grade": 90}]) == set()


from app.services.transcript_review_service import build_transcript_review, review_rows_for_commit


@pytest.mark.asyncio
async def test_build_transcript_review_marks_duplicate(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    parse_preview = {
        "courses": [
            {
                "courseNumber": course["courseNumber"],
                "semesterCode": "2024-1",
                "grade": 85,
                "creditsEarned": 4,
                "confidence": 0.95,
                "title": "Discrete Math",
            }
        ],
        "warnings": [],
        "parseMetadata": {"extractor": "test"},
    }
    existing = [
        {
            "courseId": course["courseId"],
            "semesterCode": "2024-1",
            "grade": 85,
        }
    ]

    review = await build_transcript_review(
        mongo_database,
        parse_preview=parse_preview,
        completed_course_records=existing,
    )

    assert review.duplicateCount == 1
    assert review.rows[0].status == "duplicate"
    assert review_rows_for_commit(review) == []


@pytest.mark.asyncio
async def test_build_transcript_review_marks_matched(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    parse_preview = {
        "courses": [
            {
                "courseNumber": course["courseNumber"],
                "semesterCode": "2023-2",
                "grade": 90,
                "creditsEarned": 4,
                "confidence": 0.95,
            }
        ],
        "warnings": [],
        "parseMetadata": {},
    }

    review = await build_transcript_review(
        mongo_database,
        parse_preview=parse_preview,
        completed_course_records=[],
    )

    assert review.matchedCount == 1
    assert review.rows[0].status == "matched"
    assert len(review_rows_for_commit(review)) == 1


@pytest.mark.asyncio
async def test_build_transcript_review_marks_unmatched_for_invalid_course_number(mongo_database):
    parse_preview = {
        "courses": [
            {
                "courseNumber": "not-a-number",
                "semesterCode": "2024-1",
                "grade": 85,
                "creditsEarned": 4,
            }
        ],
        "warnings": [],
        "parseMetadata": {},
    }

    review = await build_transcript_review(
        mongo_database, parse_preview=parse_preview, completed_course_records=[]
    )

    assert review.unmatchedCount == 1
    assert review.rows[0].status == "unmatched"
    assert review.rows[0].selected is False
    assert "Invalid course number format" in review.rows[0].notes
    assert review_rows_for_commit(review) == []


@pytest.mark.asyncio
async def test_build_transcript_review_marks_unmatched_when_course_not_in_catalog(mongo_database):
    parse_preview = {
        "courses": [
            {
                "courseNumber": "00940345",
                "semesterCode": "2024-1",
                "grade": 85,
                "creditsEarned": 4,
            }
        ],
        "warnings": [],
        "parseMetadata": {},
    }

    review = await build_transcript_review(
        mongo_database, parse_preview=parse_preview, completed_course_records=[]
    )

    assert review.unmatchedCount == 1
    assert "Course not found in catalog" in review.rows[0].notes


@pytest.mark.asyncio
async def test_build_transcript_review_marks_uncertain_for_low_confidence(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    parse_preview = {
        "courses": [
            {
                "courseNumber": course["courseNumber"],
                "semesterCode": "2024-1",
                "grade": 85,
                "creditsEarned": 4,
                "confidence": 0.5,
            }
        ],
        "warnings": [],
        "parseMetadata": {},
    }

    review = await build_transcript_review(
        mongo_database, parse_preview=parse_preview, completed_course_records=[]
    )

    assert review.uncertainCount == 1
    assert "Low parser confidence" in review.rows[0].notes


@pytest.mark.asyncio
async def test_build_transcript_review_marks_uncertain_for_row_warnings(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    parse_preview = {
        "courses": [
            {
                "courseNumber": course["courseNumber"],
                "semesterCode": "2024-1",
                "grade": 85,
                "creditsEarned": 4,
                "confidence": 0.95,
                "warnings": ["OCR uncertain on this row"],
            }
        ],
        "warnings": [],
        "parseMetadata": {},
    }

    review = await build_transcript_review(
        mongo_database, parse_preview=parse_preview, completed_course_records=[]
    )

    assert review.uncertainCount == 1
    assert "Parser reported warnings for this row" in review.rows[0].notes


@pytest.mark.asyncio
async def test_build_transcript_review_marks_uncertain_for_title_mismatch(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    parse_preview = {
        "courses": [
            {
                "courseNumber": course["courseNumber"],
                "semesterCode": "2024-1",
                "grade": 85,
                "creditsEarned": 4,
                "confidence": 0.95,
                "title": "Completely Unrelated Course Name",
            }
        ],
        "warnings": [],
        "parseMetadata": {},
    }

    review = await build_transcript_review(
        mongo_database, parse_preview=parse_preview, completed_course_records=[]
    )

    assert review.uncertainCount == 1
    assert "Course name does not exactly match catalog" in review.rows[0].notes


@pytest.mark.asyncio
async def test_build_transcript_review_skips_non_dict_entries(mongo_database):
    parse_preview = {
        "courses": ["not-a-dict"],
        "warnings": [],
        "parseMetadata": {},
    }

    review = await build_transcript_review(
        mongo_database, parse_preview=parse_preview, completed_course_records=[]
    )

    assert review.rows == []
