"use strict";

const RESULT_VALIDATORS = {
  academic_risk_narrative: (result) =>
    typeof result === "object" &&
    result !== null &&
    typeof result.narrative === "string" &&
    result.narrative.length > 0 &&
    typeof result.stats === "object" &&
    result.stats !== null,
};

function buildInferRequest(job) {
  return {
    jobType: job.jobType,
    input: job.input,
  };
}

function classifyInferError({ status, networkError, timedOut } = {}) {
  if (networkError || timedOut) {
    return "transient";
  }
  if (typeof status === "number" && status >= 500) {
    return "transient";
  }
  return "permanent";
}

function shouldRetry(attempt, maxAttempts, errorKind) {
  if (errorKind !== "transient") {
    return false;
  }
  return attempt < maxAttempts;
}

function validateInferResponse(jobType, body) {
  const validator = RESULT_VALIDATORS[jobType];
  if (!validator) {
    return { ok: false, reason: `Unsupported jobType: ${jobType}` };
  }

  const result = body && body.data ? body.data.result : undefined;
  if (!validator(result)) {
    return { ok: false, reason: "AI service returned an invalid result shape" };
  }

  return { ok: true, result };
}

function buildProcessingPatch(now = () => new Date()) {
  const timestamp = now();
  return { status: "processing", startedAt: timestamp, updatedAt: timestamp };
}

function buildCompletedPatch(result, attempts, now = () => new Date()) {
  const timestamp = now();
  return {
    status: "completed",
    result,
    error: null,
    attempts,
    completedAt: timestamp,
    updatedAt: timestamp,
  };
}

function buildFailedPatch(code, message, attempts, now = () => new Date()) {
  const timestamp = now();
  return {
    status: "failed",
    result: null,
    error: { code, message },
    attempts,
    completedAt: timestamp,
    updatedAt: timestamp,
  };
}

module.exports = {
  RESULT_VALIDATORS,
  buildInferRequest,
  classifyInferError,
  shouldRetry,
  validateInferResponse,
  buildProcessingPatch,
  buildCompletedPatch,
  buildFailedPatch,
};
