"""Persist imported transcript rows after catalog resolution."""

from __future__ import annotations

from typing import Any

from pymongo.errors import DuplicateKeyError

from app.repositories import catalog_repository
from app.planning.prerequisite_resolver import canonical_course_number
from app.repositories.completed_course_repository import (
    create_completed_course,
    delete_imported_completed_courses_by_user_id,
    ensure_completed_course_indexes,
    find_all_completed_courses_by_user_id,
    to_public_completed_course,
)
from app.services.transcript_import_normalization import (
    resolve_import_credits,
    resolve_import_grade_points,
)
from app.schemas.transcript_import import CommitTranscriptImportRequest
from app.services.grade_evaluation import parse_numeric_grade


def _record_identity(course_id: str | None, course_number: str | None) -> str:
    """What makes a transcript row the same row on a second import.

    Falls back to the course number for a course the catalog does not carry.
    Keying on `str(courseId)` alone made every such row identify as the literal
    "None", so importing two of them deduplicated the second one away.
    """
    if course_id:
        return str(course_id)
    return f"number:{course_number}"


def _existing_record_identity(record: dict[str, Any]) -> str:
    return _record_identity(
        str(record["courseId"]) if record.get("courseId") is not None else None,
        record.get("courseNumber") or (record.get("metadata") or {}).get("importedCourseNumber"),
    )


def _import_grade_key(course_id: str, semester_code: str, grade: Any) -> tuple[str, str, str]:
    numeric = parse_numeric_grade(grade)
    if numeric is not None and numeric == int(numeric):
        normalized_grade = str(int(numeric))
    elif numeric is not None:
        normalized_grade = str(numeric)
    else:
        normalized_grade = str(grade)
    return (course_id, semester_code, normalized_grade)


async def commit_transcript_import(
    database,
    user_id: str,
    payload: CommitTranscriptImportRequest,
) -> dict[str, Any]:
    await ensure_completed_course_indexes(database)

    replaced_count = 0
    if payload.replaceExisting:
        replaced_count = await delete_imported_completed_courses_by_user_id(database, user_id)

    existing_records = await find_all_completed_courses_by_user_id(database, user_id)
    existing_signatures = {
        (
            _existing_record_identity(record),
            str(record.get("semesterCode")),
            _import_grade_key(
                _existing_record_identity(record),
                str(record.get("semesterCode")),
                record.get("grade"),
            )[2],
            float(record.get("creditsEarned") or 0),
        )
        for record in existing_records
    }
    existing_grade_keys = {
        _import_grade_key(
            _existing_record_identity(record),
            str(record.get("semesterCode")),
            record.get("grade"),
        )
        for record in existing_records
    }

    created: list[dict[str, Any]] = []
    skipped_duplicates: list[str] = []
    unresolved: list[dict[str, str]] = []

    for row in payload.courses:
        normalized_number = canonical_course_number(row.courseNumber)
        if not normalized_number:
            unresolved.append(
                {
                    "courseNumber": row.courseNumber,
                    "semesterCode": row.semesterCode,
                    "reason": "Invalid course number",
                }
            )
            continue

        # A course the catalog has never carried is still a course the student
        # passed: the registrar's sheet says so, and it says how many credits it
        # was worth. Dropping the row made the reported total disagree with the
        # transcript it was imported from -- 129.5 against a sheet that states
        # 131.5 -- and the student was never told which course went missing.
        # The row goes in without a catalog id; requirement buckets skip it,
        # because there is no catalog entry to decide which bucket it belongs to.
        course = await catalog_repository.find_course_by_number(database, normalized_number)
        if not course:
            unresolved.append(
                {
                    "courseNumber": normalized_number,
                    "semesterCode": row.semesterCode,
                    "reason": "Course not found in catalog; credits taken from the transcript",
                }
            )

        course_id = str(course["_id"]) if course else None
        identity = _record_identity(course_id, normalized_number)
        attempt = row.attempt or 1

        credits_earned = resolve_import_credits(row, course)
        grade_points = resolve_import_grade_points(row)
        grade_key = _import_grade_key(identity, row.semesterCode, row.grade)
        signature = (
            identity,
            row.semesterCode,
            grade_key[2],
            float(credits_earned),
        )
        if payload.skipDuplicates and signature in existing_signatures:
            skipped_duplicates.append(row.courseNumber)
            continue
        if payload.skipDuplicates and grade_key in existing_grade_keys:
            skipped_duplicates.append(row.courseNumber)
            continue

        metadata: dict[str, Any] = {
            "importSource": "transcript-pdf",
            "importedCourseNumber": normalized_number,
        }
        for warning in row.warnings or []:
            lowered = warning.lower()
            if "pass grade" in lowered:
                metadata["passGrade"] = True
            if "exemption" in lowered:
                metadata["exemption"] = True
        if row.title:
            metadata["importedTitle"] = row.title

        record_data = {
            "courseId": course_id,
            "courseNumber": normalized_number,
            "semesterCode": row.semesterCode,
            "grade": row.grade,
            "gradePoints": grade_points,
            "creditsEarned": credits_earned,
            "attempt": attempt,
            "source": "imported",
            "metadata": metadata,
        }

        try:
            record = await create_completed_course(database, user_id, record_data)
        except DuplicateKeyError:
            skipped_duplicates.append(row.courseNumber)
            continue

        existing_signatures.add(signature)
        existing_grade_keys.add(grade_key)
        course_summary = catalog_repository.course_summary_from_document(course)
        public_record = to_public_completed_course(record, course_summary)
        if public_record:
            created.append(public_record)

    return {
        "created": created,
        "skippedDuplicates": skipped_duplicates,
        "unresolved": unresolved,
        "createdCount": len(created),
        "skippedCount": len(skipped_duplicates),
        "unresolvedCount": len(unresolved),
        "replacedCount": replaced_count,
    }
