"""AI job routes (async AI pipeline)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.dependencies.auth import AuthContext, require_auth
from app.middleware.auth_rate_limiter import enforce_job_rate_limit
from app.db.mongo import get_database
from app.repositories.ai_job_repository import (
    ensure_ai_job_indexes,
    to_public_ai_job,
    to_public_ai_job_summary,
)
from app.schemas.ai_job import EnqueueAiJobRequest
from app.schemas.semester_plan import OBJECT_ID_PATTERN
from app.services.ai_job_service import (
    enqueue_ai_job,
    get_ai_job_for_user,
    list_ai_jobs_for_user,
)

router = APIRouter(prefix="/ai-jobs", tags=["ai-jobs"])

_ai_job_indexes_ready = False

LIST_QUERY_ALLOWED = frozenset({"page", "limit"})


def reset_ai_job_indexes_state() -> None:
    global _ai_job_indexes_ready
    _ai_job_indexes_ready = False


async def _ensure_ai_job_indexes_once() -> None:
    global _ai_job_indexes_ready

    if _ai_job_indexes_ready:
        return

    database = await get_database()
    await ensure_ai_job_indexes(database)
    _ai_job_indexes_ready = True


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def validate_job_id_param(job_id: str) -> str:
    if not OBJECT_ID_PATTERN.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Identifier must be a valid ObjectId")
    return job_id


def _handle_enqueue_ai_job_error(result: dict[str, Any]) -> None:
    if result["status"] == "analysis_not_found":
        raise HTTPException(status_code=404, detail="Academic risk analysis not found")
    if result["status"] == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")
    if result["status"] == "degree_not_selected":
        raise HTTPException(
            status_code=400,
            detail="A degree must be selected on the student profile before requesting an AI job",
        )
    if result["status"] == "degree_not_found":
        raise HTTPException(
            status_code=400,
            detail="Referenced degree was not found in the catalog",
        )
    if result["status"] == "queue_unavailable":
        raise HTTPException(
            status_code=503,
            detail="AI job queue is temporarily unavailable",
        )


@router.post("", status_code=202)
async def enqueue_ai_job_route(
    request: Request,
    payload: EnqueueAiJobRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_job_rate_limit(request, auth.user_id)
    await _ensure_ai_job_indexes_once()
    database = await get_database()

    result = await enqueue_ai_job(database, auth.user_id, payload.model_dump())
    _handle_enqueue_ai_job_error(result)

    return success_response({"aiJob": to_public_ai_job(result["job"])})


@router.get("")
async def list_ai_jobs_route(
    request: Request,
    auth: AuthContext = Depends(require_auth),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    unknown = set(request.query_params.keys()) - LIST_QUERY_ALLOWED
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown query parameter(s): {', '.join(sorted(unknown))}",
        )

    database = await get_database()
    list_result = await list_ai_jobs_for_user(
        database,
        auth.user_id,
        {"page": page, "limit": limit},
    )

    return success_response(
        {
            "aiJobs": [
                summary
                for job in list_result["jobs"]
                if (summary := to_public_ai_job_summary(job)) is not None
            ],
            "pagination": {
                "total": list_result["total"],
                "page": list_result["page"],
                "limit": list_result["limit"],
            },
        }
    )


@router.get("/{job_id}")
async def get_ai_job_route(
    job_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_job_id_param(job_id)

    database = await get_database()
    result = await get_ai_job_for_user(database, auth.user_id, job_id)

    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="AI job not found")

    return success_response({"aiJob": to_public_ai_job(result["job"])})
