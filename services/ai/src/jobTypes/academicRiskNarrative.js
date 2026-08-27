"use strict";

function buildRiskTypeBreakdown(risks) {
  const counts = {};
  for (const risk of risks) {
    const key = risk.riskType || "unknown";
    counts[key] = (counts[key] || 0) + 1;
  }

  const sorted = {};
  for (const key of Object.keys(counts).sort()) {
    sorted[key] = counts[key];
  }
  return sorted;
}

function buildNarrative(input, riskTypeBreakdown) {
  const semesterLabel = input.semesterCode || "your plan";
  const totalRisks = input.summary.totalRisks || 0;
  const counts = input.summary.counts || { low: 0, medium: 0, high: 0 };
  const highestSeverity = input.summary.highestSeverity;

  if (totalRisks === 0) {
    return `No academic risks were found for ${semesterLabel}.`;
  }

  const severityLabel = highestSeverity ? highestSeverity : "unspecified";
  let narrative =
    `Academic risk analysis for ${semesterLabel} found ${totalRisks} risk(s), ` +
    `with the highest severity being ${severityLabel}. ` +
    `Breakdown: ${counts.low || 0} low, ${counts.medium || 0} medium, ${counts.high || 0} high severity.`;

  const titles = input.risks.map((risk) => risk.title).filter(Boolean);
  if (titles.length > 0) {
    narrative += ` Key concerns: ${titles.join("; ")}.`;
  }

  const typeSummary = Object.entries(riskTypeBreakdown)
    .map(([type, count]) => `${type} (${count})`)
    .join(", ");
  if (typeSummary) {
    narrative += ` Risk types: ${typeSummary}.`;
  }

  return narrative;
}

function computeAcademicRiskNarrative(input) {
  const summary = input.summary || { totalRisks: 0, highestSeverity: null, counts: { low: 0, medium: 0, high: 0 } };
  const risks = input.risks || [];
  const normalizedInput = { ...input, summary, risks };

  const riskTypeBreakdown = buildRiskTypeBreakdown(risks);
  const narrative = buildNarrative(normalizedInput, riskTypeBreakdown);

  return {
    narrative,
    stats: {
      totalRisks: summary.totalRisks || 0,
      highestSeverity: summary.highestSeverity || null,
      counts: summary.counts || { low: 0, medium: 0, high: 0 },
      riskTypeBreakdown,
    },
  };
}

module.exports = { computeAcademicRiskNarrative, buildRiskTypeBreakdown };
