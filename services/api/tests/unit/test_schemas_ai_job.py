"""Behavioral tests for AI job request schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.ai_job import EnqueueAiJobRequest

VALID_ANALYSIS_ID = "665f2b0f2a3f7b2a1a9a7f11"


class TestEnqueueAiJobRequest:
    def test_valid_request_accepted(self):
        req = EnqueueAiJobRequest(jobType="academic_risk_narrative", analysisId=VALID_ANALYSIS_ID)
        assert req.jobType == "academic_risk_narrative"
        assert req.analysisId == VALID_ANALYSIS_ID

    def test_invalid_analysis_id_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            EnqueueAiJobRequest(jobType="academic_risk_narrative", analysisId="not-an-object-id")
        assert "valid ObjectId" in str(exc_info.value)

    def test_unknown_job_type_rejected(self):
        with pytest.raises(ValidationError):
            EnqueueAiJobRequest(jobType="something_else", analysisId=VALID_ANALYSIS_ID)

    def test_missing_job_type_rejected(self):
        with pytest.raises(ValidationError):
            EnqueueAiJobRequest(analysisId=VALID_ANALYSIS_ID)

    def test_missing_analysis_id_rejected(self):
        with pytest.raises(ValidationError):
            EnqueueAiJobRequest(jobType="academic_risk_narrative")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            EnqueueAiJobRequest.model_validate(
                {
                    "jobType": "academic_risk_narrative",
                    "analysisId": VALID_ANALYSIS_ID,
                    "extra": "field",
                }
            )
