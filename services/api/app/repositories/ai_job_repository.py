"""User-owned AI job repository (async AI pipeline)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.semester_plan_repository import parse_object_id


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


async def ensure_ai_job_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.ai_jobs_collection]
    await collection.create_index(
        [("userId", 1), ("createdAt", -1)],
        name="ai_jobs_user_created_at",
    )
    await collection.create_index(
        [("status", 1), ("createdAt", 1)],
        name="ai_jobs_status_created_at",
    )


def build_ai_job_document(
    user_id: str,
    job_type: str,
    input_snapshot: dict[str, Any],
) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for AI job")

    now = datetime.now(timezone.utc)
    return {
        "userId": parsed_user_id,
        "jobType": job_type,
        "input": input_snapshot,
        "status": "pending",
        "result": None,
        "error": None,
        "attempts": 0,
        "queuedAt": now,
        "startedAt": None,
        "completedAt": None,
        "createdAt": now,
        "updatedAt": now,
    }


async def create_ai_job(
    database: AsyncIOMotorDatabase,
    user_id: str,
    job_type: str,
    input_snapshot: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    document = build_ai_job_document(user_id, job_type, input_snapshot)
    insert_result = await database[settings.ai_jobs_collection].insert_one(document)
    return {"_id": insert_result.inserted_id, **document}


async def mark_ai_job_failed_to_enqueue(
    database: AsyncIOMotorDatabase,
    job_id: Any,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    await database[settings.ai_jobs_collection].update_one(
        {"_id": job_id},
        {
            "$set": {
                "status": "failed",
                "error": {
                    "code": "queue_unavailable",
                    "message": "AI job queue is temporarily unavailable",
                },
                "completedAt": now,
                "updatedAt": now,
            }
        },
    )


async def find_ai_jobs_by_user_id(
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
        return {"jobs": [], "total": 0, "page": 1, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 100)
    skip = (safe_page - 1) * safe_limit

    collection = database[settings.ai_jobs_collection]
    query = {"userId": parsed_user_id}

    cursor = collection.find(query).sort("createdAt", -1).skip(skip).limit(safe_limit)
    jobs = [document async for document in cursor]
    total = await collection.count_documents(query)

    return {
        "jobs": jobs,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
    }


async def find_ai_job_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    job_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_job_id = parse_object_id(job_id)
    parsed_user_id = parse_object_id(user_id)
    if parsed_job_id is None or parsed_user_id is None:
        return None

    return await database[settings.ai_jobs_collection].find_one(
        {"_id": parsed_job_id, "userId": parsed_user_id}
    )


def to_public_ai_job_summary(job_document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job_document:
        return None

    return {
        "id": str(job_document["_id"]),
        "jobType": job_document.get("jobType"),
        "status": job_document.get("status"),
        "createdAt": _format_datetime(job_document.get("createdAt")),
        "updatedAt": _format_datetime(job_document.get("updatedAt")),
    }


def to_public_ai_job(job_document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job_document:
        return None

    return {
        "id": str(job_document["_id"]),
        "jobType": job_document.get("jobType"),
        "status": job_document.get("status"),
        "input": job_document.get("input") or {},
        "result": job_document.get("result"),
        "error": job_document.get("error"),
        "attempts": job_document.get("attempts", 0),
        "queuedAt": _format_datetime(job_document.get("queuedAt")),
        "startedAt": _format_datetime(job_document.get("startedAt")),
        "completedAt": _format_datetime(job_document.get("completedAt")),
        "createdAt": _format_datetime(job_document.get("createdAt")),
        "updatedAt": _format_datetime(job_document.get("updatedAt")),
    }
