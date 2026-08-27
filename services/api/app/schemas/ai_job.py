"""AI job request schemas (async AI pipeline)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.student_profile import validate_object_id

AI_JOB_TYPES = ("academic_risk_narrative",)
AiJobType = Literal["academic_risk_narrative"]
AiJobStatus = Literal["pending", "processing", "completed", "failed"]


class EnqueueAiJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobType: AiJobType
    analysisId: str

    @field_validator("analysisId")
    @classmethod
    def validate_analysis_id(cls, value: str) -> str:
        return validate_object_id(value)
