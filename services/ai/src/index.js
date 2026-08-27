const express = require("express");

const { requireInternalServiceToken } = require("./internalAuth");
const { computeAcademicRiskNarrative } = require("./jobTypes/academicRiskNarrative");

const app = express();
const port = Number(process.env.AI_SERVICE_PORT) || 3001;
const internalServiceToken = process.env.INTERNAL_SERVICE_TOKEN || "";

const JOB_COMPUTE_REGISTRY = {
  academic_risk_narrative: computeAcademicRiskNarrative,
};

app.use(express.json());

app.get("/health", (_req, res) => {
  res.status(200).json({
    service: "ai",
    status: "ok",
    timestamp: new Date().toISOString()
  });
});

app.post("/infer", requireInternalServiceToken(internalServiceToken), (req, res) => {
  const { jobType, input } = req.body || {};
  const compute = JOB_COMPUTE_REGISTRY[jobType];

  if (!compute) {
    return res.status(400).json({
      success: false,
      data: null,
      error: `Unsupported jobType: ${jobType}`,
    });
  }

  const result = compute(input || {});
  return res.status(200).json({ success: true, data: { result }, error: null });
});

app.listen(port, "0.0.0.0", () => {
  console.log(`[ai] listening on port ${port}`);
});
