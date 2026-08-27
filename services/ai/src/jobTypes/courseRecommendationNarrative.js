"use strict";

function courseListSummary(courses) {
  return courses.map((course) => `${course.title || course.courseNumber} (${course.courseNumber})`).join("; ");
}

function buildNarrative(input) {
  const { completionPercentage, creditsRemaining, recommendedMandatoryCourses, recommendedElectiveCourses } = input;
  const totalRecommended = recommendedMandatoryCourses.length + recommendedElectiveCourses.length;

  if (totalRecommended === 0) {
    return (
      `You are ${completionPercentage}% through your degree with ${creditsRemaining} credit(s) remaining, ` +
      `but no currently unlocked courses were found to recommend right now.`
    );
  }

  let narrative = `You are ${completionPercentage}% through your degree with ${creditsRemaining} credit(s) remaining.`;

  if (recommendedMandatoryCourses.length > 0) {
    narrative += ` Recommended mandatory courses: ${courseListSummary(recommendedMandatoryCourses)}.`;
  }
  if (recommendedElectiveCourses.length > 0) {
    narrative += ` Recommended electives: ${courseListSummary(recommendedElectiveCourses)}.`;
  }

  return narrative;
}

function computeCourseRecommendationNarrative(input) {
  const normalizedInput = {
    completionPercentage: input.completionPercentage || 0,
    creditsRemaining: input.creditsRemaining || 0,
    recommendedMandatoryCourses: input.recommendedMandatoryCourses || [],
    recommendedElectiveCourses: input.recommendedElectiveCourses || [],
  };

  const narrative = buildNarrative(normalizedInput);

  return {
    narrative,
    stats: {
      mandatoryCount: normalizedInput.recommendedMandatoryCourses.length,
      electiveCount: normalizedInput.recommendedElectiveCourses.length,
      completionPercentage: normalizedInput.completionPercentage,
    },
  };
}

module.exports = { computeCourseRecommendationNarrative, courseListSummary };
