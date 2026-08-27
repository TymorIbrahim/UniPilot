"""AI job orchestration (async AI pipeline)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.semester_planner import build_candidate_pools, prerequisites_met
from app.repositories.ai_job_repository import (
    create_ai_job,
    find_ai_job_by_id_and_user_id,
    mark_ai_job_failed_to_enqueue,
)
from app.services.ai_job_queue import resolve_ai_job_queue_store
from app.services.graduation_progress_calculator import build_effective_completions

RECOMMENDATION_CANDIDATE_LIMIT = 5


def build_academic_risk_narrative_input(analysis_document: dict[str, Any]) -> dict[str, Any]:
    summary = analysis_document.get("summary") or {}
    risks = analysis_document.get("risks") or []

    return {
        "analysisId": str(analysis_document["_id"]),
        "semesterCode": analysis_document.get("semesterCode"),
        "summary": {
            "totalRisks": summary.get("totalRisks", 0),
            "highestSeverity": summary.get("highestSeverity"),
            "counts": summary.get("counts") or {"low": 0, "medium": 0, "high": 0},
        },
        "risks": [
            {
                "riskType": risk.get("riskType"),
                "severity": risk.get("severity"),
                "title": risk.get("title"),
            }
            for risk in risks
        ],
    }


def build_course_recommendation_input(context: dict[str, Any]) -> dict[str, Any]:
    effective_completions = build_effective_completions(context["completedCourseRecords"])
    completed_course_ids = set(effective_completions.keys())

    pools = build_candidate_pools(
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        hard_requirements=context["hardRequirements"],
        pool_documents=context["poolDocuments"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        program_code=context["degree"].get("programCode"),
        completed_course_ids=completed_course_ids,
    )

    def takeable(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "courseNumber": course.get("number"),
                "title": course.get("title"),
                "credits": course.get("credits"),
            }
            for course in candidates
            if prerequisites_met(course, completed_course_ids)
        ][:RECOMMENDATION_CANDIDATE_LIMIT]

    graduation_progress = context["graduationProgress"]
    return {
        "degreeCode": context["degree"].get("programCode"),
        "completionPercentage": graduation_progress.get("completionPercentage", 0),
        "creditsRemaining": graduation_progress.get("creditsRemaining", 0),
        "recommendedMandatoryCourses": takeable(pools["mandatoryCandidates"]),
        "recommendedElectiveCourses": takeable(pools["electiveCandidates"]),
    }


async def enqueue_ai_job(
    database: AsyncIOMotorDatabase,
    user_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    job_type = payload["jobType"]

    if job_type == "academic_risk_narrative":
        from app.repositories.academic_risk_repository import (
            find_academic_risk_analysis_by_id_and_user_id,
        )

        analysis = await find_academic_risk_analysis_by_id_and_user_id(
            database,
            payload["analysisId"],
            user_id,
        )
        if not analysis:
            return {"status": "analysis_not_found"}
        input_snapshot = build_academic_risk_narrative_input(analysis)
    else:
        from app.services.semester_plan_service import load_planning_context

        context = await load_planning_context(database, user_id)
        if context["status"] != "ok":
            return {"status": context["status"]}
        input_snapshot = build_course_recommendation_input(context)

    job = await create_ai_job(database, user_id, job_type, input_snapshot)

    try:
        await resolve_ai_job_queue_store().enqueue(str(job["_id"]))
    except Exception:
        await mark_ai_job_failed_to_enqueue(database, job["_id"])
        return {"status": "queue_unavailable"}

    return {"status": "ok", "job": job}


async def list_ai_jobs_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    pagination: dict[str, Any],
) -> dict[str, Any]:
    from app.repositories.ai_job_repository import find_ai_jobs_by_user_id

    return await find_ai_jobs_by_user_id(
        database,
        user_id,
        page=pagination.get("page") or 1,
        limit=pagination.get("limit") or 50,
    )


async def get_ai_job_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    job_id: str,
) -> dict[str, Any]:
    job = await find_ai_job_by_id_and_user_id(database, job_id, user_id)
    if not job:
        return {"status": "not_found"}

    return {"status": "ok", "job": job}
