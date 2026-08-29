"""User-owned completed courses repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.services.completed_course_attempts import MAX_COURSE_ATTEMPTS, resolve_available_attempt

UpdateStatus = Literal["updated", "not_found", "not_editable"]
DeleteStatus = Literal["deleted", "not_found", "not_editable"]


def parse_object_id(value: str | None) -> ObjectId | None:
    if value is None:
        return None
    try:
        return ObjectId(str(value))
    except Exception:
        return None


LEGACY_UNIQUE_ATTEMPT_INDEX = "completed_courses_unique_user_course_attempt"
UNIQUE_ATTEMPT_INDEX = "completed_courses_unique_user_course_number_attempt"
UNIQUE_ATTEMPT_KEY = [("userId", 1), ("courseId", 1), ("courseNumber", 1), ("attempt", 1)]


async def _ensure_unique_attempt_index(collection: Any) -> None:
    """One row per (student, course, attempt), where "course" may be a number only.

    `courseId` alone was the key, which silently forbade a student from holding
    two transcript rows the catalog does not carry: both get a null `courseId`,
    Mongo indexes the absent field as null, and the second insert collides with
    the first. Adding `courseNumber` to the key separates them while staying
    strictly weaker than the old constraint for rows that DO have a course id --
    the number is derived from the id, so no pair that was rejected before is
    accepted now.

    Dropping the old index by name is idempotent: a fresh database never has it,
    and one that does gets it replaced exactly once.
    """
    existing = await collection.index_information()
    if LEGACY_UNIQUE_ATTEMPT_INDEX in existing:
        await collection.drop_index(LEGACY_UNIQUE_ATTEMPT_INDEX)
    await collection.create_index(UNIQUE_ATTEMPT_KEY, unique=True, name=UNIQUE_ATTEMPT_INDEX)


async def ensure_completed_course_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.completed_courses_collection]
    await _ensure_unique_attempt_index(collection)
    await collection.create_index(
        [("userId", 1), ("semesterCode", 1)],
        name="completed_courses_user_semester",
    )
    await collection.create_index(
        [("userId", 1), ("recordedAt", -1)],
        name="completed_courses_user_recorded_at",
    )


async def resolve_course_number(
    database: AsyncIOMotorDatabase,
    course_id: ObjectId,
    *,
    settings: Settings | None = None,
) -> str | None:
    """The course's catalog number, for denormalising onto the transcript row.

    `None` when the course is not in the catalog, which is not a new failure --
    such a row is already unreadable, because `courseId` is its only identity.
    """
    settings = settings or get_settings()
    course = await database[settings.courses_collection].find_one(
        {"_id": course_id}, {"courseNumber": 1}
    )
    number = (course or {}).get("courseNumber")
    return str(number) if number else None


def build_completed_course_document(
    user_id: str, record_data: dict[str, Any], course_number: str | None = None
) -> dict[str, Any]:
    """One transcript row, ready to insert.

    `course_number` is DENORMALISED here on purpose, duplicating what `courseId`
    already points at. Without it a transcript row's only identity is an
    ObjectId into another collection, and 28% of live rows reference a `courses`
    document that no longer exists -- 38 of 145 students have no readable row at
    all. Those rows carry no course number, no offering and empty metadata, so
    what the student studied is simply unrecoverable.

    `semester_plans.plannedCourses` already stores both, and that redundancy is
    the only reason any of the broken rows could be repaired. This makes the
    transcript as durable as the plan.

    A course number is stable in a way `_id` is not: it is the registrar's
    identifier, it survives a catalog re-promotion, and it is what
    `productionKey` is derived from.
    """
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for completed course")

    parsed_course_id = parse_object_id(record_data.get("courseId"))
    if parsed_course_id is None and not course_number:
        # A row with neither is unidentifiable; a row with a number but no id is
        # a course the catalog has never carried, and the registrar's own sheet
        # is authority enough for its credits.
        raise ValueError("Completed course needs a catalog id or a course number")

    now = datetime.now(timezone.utc)

    return {
        "userId": parsed_user_id,
        "courseId": parsed_course_id,
        # OMITTED rather than stored as None when the catalog has no such course:
        # an absent field reads as "unknown", where a null reads as "known to be
        # nothing" and would satisfy an `$exists` check that means to find rows
        # carrying a real number.
        **({"courseNumber": course_number} if course_number else {}),
        "courseOfferingId": None,
        "semesterCode": record_data["semesterCode"],
        "grade": record_data["grade"],
        "gradePoints": record_data.get("gradePoints"),
        "creditsEarned": record_data["creditsEarned"],
        "attempt": record_data.get("attempt", 1),
        "source": record_data.get("source", "manual"),
        "metadata": record_data.get("metadata") or {},
        "recordedAt": now,
        "createdAt": now,
        "updatedAt": now,
    }


async def find_used_attempts_for_course(
    database: AsyncIOMotorDatabase,
    user_id: str,
    course_id: str | None,
    *,
    course_number: str | None = None,
    settings: Settings | None = None,
) -> set[int]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return set()

    parsed_course_id = parse_object_id(course_id)
    if parsed_course_id is not None:
        query: dict[str, Any] = {"userId": parsed_user_id, "courseId": parsed_course_id}
    elif course_number:
        # Retakes of a course the catalog does not carry still need distinct
        # attempt numbers, and the number is the only identity such a row has.
        query = {"userId": parsed_user_id, "courseId": None, "courseNumber": course_number}
    else:
        return set()

    records = await database[settings.completed_courses_collection].find(
        query,
        {"attempt": 1},
    ).to_list(length=MAX_COURSE_ATTEMPTS)

    return {int(record.get("attempt") or 1) for record in records}


async def create_completed_course(
    database: AsyncIOMotorDatabase,
    user_id: str,
    record_data: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    raw_course_id = record_data.get("courseId")
    course_id = str(raw_course_id) if raw_course_id is not None else None
    # Supplied by the caller only for a row the catalog cannot resolve; for
    # every other row the number is read back from the catalog below, which
    # keeps it authoritative rather than whatever the transcript happened to say.
    fallback_number = record_data.get("courseNumber")
    used_attempts = await find_used_attempts_for_course(
        database,
        user_id,
        course_id,
        course_number=fallback_number,
        settings=settings,
    )
    resolved_attempt = resolve_available_attempt(
        used_attempts,
        record_data.get("attempt", 1),
    )
    resolved_record_data = {**record_data, "attempt": resolved_attempt}
    parsed_course_id = parse_object_id(course_id)
    course_number = (
        await resolve_course_number(database, parsed_course_id, settings=settings)
        if parsed_course_id is not None
        else fallback_number
    )
    document = build_completed_course_document(user_id, resolved_record_data, course_number)
    insert_result = await database[settings.completed_courses_collection].insert_one(document)
    return {
        "_id": insert_result.inserted_id,
        **document,
    }


async def find_completed_courses_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    page: int = 1,
    limit: int = 50,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return {"records": [], "total": 0, "page": page, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 100)
    skip = (safe_page - 1) * safe_limit

    collection = database[settings.completed_courses_collection]
    query = {"userId": parsed_user_id}

    records = (
        await collection.find(query)
        .sort("recordedAt", -1)
        .skip(skip)
        .limit(safe_limit)
        .to_list(length=safe_limit)
    )
    total = await collection.count_documents(query)

    return {
        "records": records,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
    }


async def find_completed_courses_for_statistics(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Every transcript row, projected to just what course statistics need.

    Deliberately narrow: course number, grade, and the two metadata flags that
    say whether a row carries a real score. No user id leaves this query, so an
    aggregate built from it cannot be traced back to a student even by accident,
    and the rows are small enough to aggregate in the caller.
    """
    settings = settings or get_settings()
    return (
        await database[settings.completed_courses_collection]
        .find(
            {},
            {
                "_id": 0,
                "courseNumber": 1,
                "grade": 1,
                "metadata.importedCourseNumber": 1,
                "metadata.exemption": 1,
                "metadata.passGrade": 1,
            },
        )
        .to_list(length=None)
    )


async def find_all_completed_courses_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return []

    return (
        await database[settings.completed_courses_collection]
        .find({"userId": parsed_user_id})
        .sort("recordedAt", -1)
        .to_list(length=10_000)
    )


async def find_completed_course_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    record_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_record_id = parse_object_id(record_id)
    parsed_user_id = parse_object_id(user_id)
    if parsed_record_id is None or parsed_user_id is None:
        return None

    return await database[settings.completed_courses_collection].find_one(
        {"_id": parsed_record_id, "userId": parsed_user_id}
    )


async def update_completed_course_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    record_id: str,
    user_id: str,
    updates: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    existing_record = await find_completed_course_by_id_and_user_id(
        database,
        record_id,
        user_id,
        settings=settings,
    )
    if not existing_record:
        return {"status": "not_found"}

    if existing_record.get("source") != "manual":
        return {"status": "not_editable", "record": existing_record}

    update_document: dict[str, Any] = {"updatedAt": datetime.now(timezone.utc)}

    if "semesterCode" in updates:
        update_document["semesterCode"] = updates["semesterCode"]
    if "grade" in updates:
        update_document["grade"] = updates["grade"]
    if "gradePoints" in updates:
        update_document["gradePoints"] = updates["gradePoints"]
    if "creditsEarned" in updates:
        update_document["creditsEarned"] = updates["creditsEarned"]
    if "metadata" in updates:
        update_document["metadata"] = updates["metadata"]

    update_result = await database[settings.completed_courses_collection].find_one_and_update(
        {
            "_id": existing_record["_id"],
            "userId": existing_record["userId"],
            "source": "manual",
        },
        {"$set": update_document},
        return_document=True,
    )

    if not update_result:
        return {"status": "not_found"}

    return {"status": "updated", "record": update_result}


async def delete_imported_completed_courses_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> int:
    """Remove all PDF-imported transcript rows for a user (manual rows are kept)."""
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return 0

    result = await database[settings.completed_courses_collection].delete_many(
        {"userId": parsed_user_id, "source": "imported"},
    )
    return int(result.deleted_count)


async def delete_completed_course_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    record_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    existing_record = await find_completed_course_by_id_and_user_id(
        database,
        record_id,
        user_id,
        settings=settings,
    )
    if not existing_record:
        return {"status": "not_found"}

    if existing_record.get("source") != "manual":
        return {"status": "not_editable", "record": existing_record}

    delete_result = await database[settings.completed_courses_collection].delete_one(
        {
            "_id": existing_record["_id"],
            "userId": existing_record["userId"],
            "source": "manual",
        }
    )

    if not delete_result.deleted_count:
        return {"status": "not_found"}

    return {"status": "deleted"}


def _format_datetime(value: datetime | Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


def to_public_completed_course(
    record_document: dict[str, Any] | None,
    course_summary: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    if not record_document:
        return None

    course_id = record_document.get("courseId")
    stored_number = record_document.get("courseNumber")
    stored_title = (record_document.get("metadata") or {}).get("importedTitle")

    return {
        "id": str(record_document["_id"]),
        # None, not "None": a row imported from a transcript for a course the
        # catalog does not carry has no catalog id, and stringifying the absence
        # produces an id-shaped value that reads as real.
        "courseId": str(course_id) if course_id is not None else None,
        # Falls back to what the row itself stores. The catalog summary is
        # missing whenever the course was never ingested or has since been
        # dropped, and without this the student sees a transcript line with no
        # course on it at all.
        "courseNumber": (course_summary.get("number") if course_summary else None) or stored_number,
        "courseTitle": (course_summary.get("title") if course_summary else None) or stored_title,
        "semesterCode": record_document["semesterCode"],
        "grade": record_document["grade"],
        "gradePoints": record_document.get("gradePoints"),
        "creditsEarned": record_document["creditsEarned"],
        "attempt": record_document["attempt"],
        "source": record_document["source"],
        "metadata": record_document.get("metadata") or {},
        "recordedAt": _format_datetime(record_document["recordedAt"]),
        "createdAt": _format_datetime(record_document["createdAt"]),
        "updatedAt": _format_datetime(record_document["updatedAt"]),
    }
