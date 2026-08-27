"""AI job request schemas (async AI pipeline)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.student_profile import validate_object_id

AI_JOB_TYPES = ("academic_risk_narrative", "course_recommendation_narrative")
AiJobType = Literal["academic_risk_narrative", "course_recommendation_narrative"]
AiJobStatus = Literal["pending", "processing", "completed", "failed"]


class EnqueueAiJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobType: AiJobType
    analysisId: str | None = None

    @field_validator("analysisId")
    @classmethod
    def validate_analysis_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_object_id(value)

    @model_validator(mode="after")
    def validate_analysis_id_matches_job_type(self) -> "EnqueueAiJobRequest":
        if self.jobType == "academic_risk_narrative" and not self.analysisId:
            raise ValueError("analysisId is required for jobType=academic_risk_narrative")
        if self.jobType == "course_recommendation_narrative" and self.analysisId:
            raise ValueError("analysisId is not used for jobType=course_recommendation_narrative")
        return self
