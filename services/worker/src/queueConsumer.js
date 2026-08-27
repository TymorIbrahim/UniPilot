"use strict";

const { ObjectId } = require("mongodb");

const { callAiInfer } = require("./aiClient");
const {
  buildInferRequest,
  classifyInferError,
  shouldRetry,
  validateInferResponse,
  buildProcessingPatch,
  buildCompletedPatch,
  buildFailedPatch,
} = require("./jobPure");

const MAX_ATTEMPTS = 2;
const RETRY_DELAY_MS = 500;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function processJob(jobId, { collection, aiConfig }) {
  const job = await collection.findOne({ _id: new ObjectId(jobId) });
  if (!job) {
    console.warn(`[worker] job ${jobId} not found, skipping`);
    return;
  }

  if (job.status !== "pending") {
    console.warn(`[worker] job ${jobId} is not pending (status=${job.status}), skipping`);
    return;
  }

  await collection.updateOne({ _id: job._id }, { $set: buildProcessingPatch() });

  const request = buildInferRequest(job);
  let attempts = 0;
  let outcome;

  while (attempts < MAX_ATTEMPTS) {
    attempts += 1;
    outcome = await callAiInfer({
      baseUrl: aiConfig.baseUrl,
      token: aiConfig.token,
      jobType: request.jobType,
      input: request.input,
      timeoutMs: aiConfig.timeoutMs,
    });

    if (outcome.status !== undefined && outcome.ok) {
      break;
    }

    const errorKind = classifyInferError(outcome);
    if (!shouldRetry(attempts, MAX_ATTEMPTS, errorKind)) {
      break;
    }
    await sleep(RETRY_DELAY_MS);
  }

  if (outcome && outcome.status !== undefined && outcome.ok) {
    const validation = validateInferResponse(request.jobType, outcome.body);
    if (!validation.ok) {
      await collection.updateOne(
        { _id: job._id },
        { $set: buildFailedPatch("invalid_result", validation.reason, attempts) }
      );
      return;
    }

    await collection.updateOne(
      { _id: job._id },
      { $set: buildCompletedPatch(validation.result, attempts) }
    );
    return;
  }

  const code = outcome && outcome.timedOut ? "timeout" : outcome && outcome.networkError ? "network_error" : "ai_service_error";
  const message = outcome && outcome.body && outcome.body.error ? String(outcome.body.error) : "AI inference call failed";
  await collection.updateOne(
    { _id: job._id },
    { $set: buildFailedPatch(code, message, attempts) }
  );
}

async function runConsumerLoop({ redis, collection, aiConfig, queueName, shouldStop }) {
  while (!shouldStop()) {
    let popped;
    try {
      popped = await redis.blpop(queueName, 5);
    } catch (err) {
      console.error("[worker] BLPOP failed, retrying shortly", err);
      await sleep(1000);
      continue;
    }

    if (!popped) {
      continue;
    }

    const [, jobId] = popped;
    try {
      await processJob(jobId, { collection, aiConfig });
    } catch (err) {
      console.error(`[worker] unexpected error processing job ${jobId}`, err);
    }
  }
}

module.exports = { processJob, runConsumerLoop };
