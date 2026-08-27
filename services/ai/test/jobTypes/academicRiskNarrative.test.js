"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  computeAcademicRiskNarrative,
  buildRiskTypeBreakdown,
} = require("../../src/jobTypes/academicRiskNarrative");

test("buildRiskTypeBreakdown counts and sorts by riskType", () => {
  const breakdown = buildRiskTypeBreakdown([
    { riskType: "overload" },
    { riskType: "prerequisite" },
    { riskType: "overload" },
  ]);
  assert.deepEqual(Object.keys(breakdown), ["overload", "prerequisite"]);
  assert.equal(breakdown.overload, 2);
  assert.equal(breakdown.prerequisite, 1);
});

test("computeAcademicRiskNarrative reports no risks for an empty analysis", () => {
  const result = computeAcademicRiskNarrative({
    analysisId: "abc",
    semesterCode: "2025-2",
    summary: { totalRisks: 0, highestSeverity: null, counts: { low: 0, medium: 0, high: 0 } },
    risks: [],
  });

  assert.equal(result.narrative, "No academic risks were found for 2025-2.");
  assert.equal(result.stats.totalRisks, 0);
  assert.deepEqual(result.stats.riskTypeBreakdown, {});
});

test("computeAcademicRiskNarrative builds a narrative for a single risk", () => {
  const result = computeAcademicRiskNarrative({
    analysisId: "abc",
    semesterCode: "2025-2",
    summary: { totalRisks: 1, highestSeverity: "high", counts: { low: 0, medium: 0, high: 1 } },
    risks: [{ riskType: "overload", severity: "high", title: "Overloaded semester" }],
  });

  assert.equal(
    result.narrative,
    "Academic risk analysis for 2025-2 found 1 risk(s), with the highest severity being high. " +
      "Breakdown: 0 low, 0 medium, 1 high severity. Key concerns: Overloaded semester. " +
      "Risk types: overload (1)."
  );
  assert.deepEqual(result.stats.riskTypeBreakdown, { overload: 1 });
});

test("computeAcademicRiskNarrative handles mixed severities and multiple risk types deterministically", () => {
  const result = computeAcademicRiskNarrative({
    analysisId: "abc",
    semesterCode: "2025-2",
    summary: {
      totalRisks: 3,
      highestSeverity: "high",
      counts: { low: 1, medium: 1, high: 1 },
    },
    risks: [
      { riskType: "overload", severity: "high", title: "Overloaded semester" },
      { riskType: "prerequisite", severity: "medium", title: "Missing prereq" },
      { riskType: "prerequisite", severity: "low", title: "Weak prereq history" },
    ],
  });

  assert.equal(
    result.narrative,
    "Academic risk analysis for 2025-2 found 3 risk(s), with the highest severity being high. " +
      "Breakdown: 1 low, 1 medium, 1 high severity. " +
      "Key concerns: Overloaded semester; Missing prereq; Weak prereq history. " +
      "Risk types: overload (1), prerequisite (2)."
  );
  assert.deepEqual(result.stats.riskTypeBreakdown, { overload: 1, prerequisite: 2 });
});

test("computeAcademicRiskNarrative falls back to 'your plan' when semesterCode is missing", () => {
  const result = computeAcademicRiskNarrative({
    analysisId: "abc",
    semesterCode: null,
    summary: { totalRisks: 0, highestSeverity: null, counts: { low: 0, medium: 0, high: 0 } },
    risks: [],
  });

  assert.equal(result.narrative, "No academic risks were found for your plan.");
});

test("computeAcademicRiskNarrative defaults missing summary and risks", () => {
  const result = computeAcademicRiskNarrative({ analysisId: "abc", semesterCode: "2025-2" });

  assert.equal(result.narrative, "No academic risks were found for 2025-2.");
  assert.deepEqual(result.stats.counts, { low: 0, medium: 0, high: 0 });
  assert.equal(result.stats.highestSeverity, null);
});

test("computeAcademicRiskNarrative is deterministic across repeated calls", () => {
  const input = {
    analysisId: "abc",
    semesterCode: "2025-2",
    summary: { totalRisks: 1, highestSeverity: "medium", counts: { low: 0, medium: 1, high: 0 } },
    risks: [{ riskType: "overload", severity: "medium", title: "Heavy load" }],
  };

  const first = computeAcademicRiskNarrative(input);
  const second = computeAcademicRiskNarrative(input);
  assert.deepEqual(first, second);
});
