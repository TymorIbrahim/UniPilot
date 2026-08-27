"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  computeCourseRecommendationNarrative,
  courseListSummary,
} = require("../../src/jobTypes/courseRecommendationNarrative");

test("courseListSummary joins courses with title fallback to courseNumber", () => {
  const summary = courseListSummary([
    { courseNumber: "00940101", title: "Algebra" },
    { courseNumber: "00940202", title: null },
  ]);
  assert.equal(summary, "Algebra (00940101); 00940202 (00940202)");
});

test("computeCourseRecommendationNarrative reports nothing recommended when both lists are empty", () => {
  const result = computeCourseRecommendationNarrative({
    degreeCode: "023023-1-000",
    completionPercentage: 65,
    creditsRemaining: 40,
    recommendedMandatoryCourses: [],
    recommendedElectiveCourses: [],
  });

  assert.equal(
    result.narrative,
    "You are 65% through your degree with 40 credit(s) remaining, but no currently unlocked courses were found to recommend right now."
  );
  assert.deepEqual(result.stats, { mandatoryCount: 0, electiveCount: 0, completionPercentage: 65 });
});

test("computeCourseRecommendationNarrative lists mandatory and elective courses", () => {
  const result = computeCourseRecommendationNarrative({
    degreeCode: "023023-1-000",
    completionPercentage: 30,
    creditsRemaining: 90,
    recommendedMandatoryCourses: [{ courseNumber: "00940101", title: "Algebra", credits: 3.0 }],
    recommendedElectiveCourses: [{ courseNumber: "00940411", title: "Data Science", credits: 3.5 }],
  });

  assert.equal(
    result.narrative,
    "You are 30% through your degree with 90 credit(s) remaining. " +
      "Recommended mandatory courses: Algebra (00940101). " +
      "Recommended electives: Data Science (00940411)."
  );
  assert.deepEqual(result.stats, { mandatoryCount: 1, electiveCount: 1, completionPercentage: 30 });
});

test("computeCourseRecommendationNarrative handles mandatory-only recommendations", () => {
  const result = computeCourseRecommendationNarrative({
    completionPercentage: 10,
    creditsRemaining: 120,
    recommendedMandatoryCourses: [{ courseNumber: "00940101", title: "Algebra", credits: 3.0 }],
    recommendedElectiveCourses: [],
  });

  assert.match(result.narrative, /Recommended mandatory courses: Algebra \(00940101\)\.$/);
  assert.doesNotMatch(result.narrative, /Recommended electives/);
});

test("computeCourseRecommendationNarrative defaults missing fields", () => {
  const result = computeCourseRecommendationNarrative({});

  assert.equal(
    result.narrative,
    "You are 0% through your degree with 0 credit(s) remaining, but no currently unlocked courses were found to recommend right now."
  );
  assert.deepEqual(result.stats, { mandatoryCount: 0, electiveCount: 0, completionPercentage: 0 });
});

test("computeCourseRecommendationNarrative is deterministic across repeated calls", () => {
  const input = {
    completionPercentage: 55,
    creditsRemaining: 50,
    recommendedMandatoryCourses: [{ courseNumber: "00940101", title: "Algebra", credits: 3.0 }],
    recommendedElectiveCourses: [],
  };

  const first = computeCourseRecommendationNarrative(input);
  const second = computeCourseRecommendationNarrative(input);
  assert.deepEqual(first, second);
});
