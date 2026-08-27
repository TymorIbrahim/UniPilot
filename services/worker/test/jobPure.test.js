"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildInferRequest,
  classifyInferError,
  shouldRetry,
  validateInferResponse,
  buildProcessingPatch,
  buildCompletedPatch,
  buildFailedPatch,
} = require("../src/jobPure");

test("buildInferRequest extracts jobType and input", () => {
  const job = { jobType: "academic_risk_narrative", input: { analysisId: "abc" }, extra: "ignored" };
  assert.deepEqual(buildInferRequest(job), {
    jobType: "academic_risk_narrative",
    input: { analysisId: "abc" },
  });
});

test("classifyInferError treats network errors as transient", () => {
  assert.equal(classifyInferError({ networkError: true }), "transient");
});

test("classifyInferError treats timeouts as transient", () => {
  assert.equal(classifyInferError({ timedOut: true }), "transient");
});

test("classifyInferError treats 5xx as transient", () => {
  assert.equal(classifyInferError({ status: 503 }), "transient");
});

test("classifyInferError treats 4xx as permanent", () => {
  assert.equal(classifyInferError({ status: 400 }), "permanent");
});

test("classifyInferError defaults to permanent with no signal", () => {
  assert.equal(classifyInferError(), "permanent");
});

test("shouldRetry allows a transient error under the attempt cap", () => {
  assert.equal(shouldRetry(1, 2, "transient"), true);
});

test("shouldRetry denies once the attempt cap is reached", () => {
  assert.equal(shouldRetry(2, 2, "transient"), false);
});

test("shouldRetry denies permanent errors regardless of attempts", () => {
  assert.equal(shouldRetry(0, 2, "permanent"), false);
});

test("validateInferResponse accepts a well-shaped academic_risk_narrative result", () => {
  const body = {
    data: { result: { narrative: "Some narrative", stats: { totalRisks: 1 } } },
  };
  const outcome = validateInferResponse("academic_risk_narrative", body);
  assert.equal(outcome.ok, true);
  assert.equal(outcome.result.narrative, "Some narrative");
});

test("validateInferResponse rejects an unsupported jobType", () => {
  const outcome = validateInferResponse("unsupported_type", { data: { result: {} } });
  assert.equal(outcome.ok, false);
  assert.match(outcome.reason, /Unsupported jobType/);
});

test("validateInferResponse rejects a missing narrative field", () => {
  const body = { data: { result: { stats: {} } } };
  const outcome = validateInferResponse("academic_risk_narrative", body);
  assert.equal(outcome.ok, false);
});

test("validateInferResponse rejects an empty narrative string", () => {
  const body = { data: { result: { narrative: "", stats: {} } } };
  const outcome = validateInferResponse("academic_risk_narrative", body);
  assert.equal(outcome.ok, false);
});

test("validateInferResponse rejects a missing stats field", () => {
  const body = { data: { result: { narrative: "text" } } };
  const outcome = validateInferResponse("academic_risk_narrative", body);
  assert.equal(outcome.ok, false);
});

test("validateInferResponse rejects a missing body", () => {
  const outcome = validateInferResponse("academic_risk_narrative", null);
  assert.equal(outcome.ok, false);
});

test("buildProcessingPatch stamps status and timestamps with the injected clock", () => {
  const fixed = new Date("2025-01-01T00:00:00.000Z");
  const patch = buildProcessingPatch(() => fixed);
  assert.deepEqual(patch, { status: "processing", startedAt: fixed, updatedAt: fixed });
});

test("buildCompletedPatch stamps result and clears error with the injected clock", () => {
  const fixed = new Date("2025-01-01T00:00:00.000Z");
  const result = { narrative: "done", stats: {} };
  const patch = buildCompletedPatch(result, 1, () => fixed);
  assert.deepEqual(patch, {
    status: "completed",
    result,
    error: null,
    attempts: 1,
    completedAt: fixed,
    updatedAt: fixed,
  });
});

test("buildFailedPatch stamps error and clears result with the injected clock", () => {
  const fixed = new Date("2025-01-01T00:00:00.000Z");
  const patch = buildFailedPatch("timeout", "AI service timed out", 2, () => fixed);
  assert.deepEqual(patch, {
    status: "failed",
    result: null,
    error: { code: "timeout", message: "AI service timed out" },
    attempts: 2,
    completedAt: fixed,
    updatedAt: fixed,
  });
});
