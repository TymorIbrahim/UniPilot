const express = require("express");
const { MongoClient } = require("mongodb");
const Redis = require("ioredis");

const { runConsumerLoop } = require("./queueConsumer");

const port = Number(process.env.WORKER_PORT) || 3002;
const queueName = process.env.WORKER_QUEUE_NAME || "ai_jobs";
const mongoUri = process.env.MONGO_URI;
const redisUrl = process.env.REDIS_URL;
const aiServiceUrl = process.env.AI_SERVICE_URL || "http://ai:3001";
const internalServiceToken = process.env.INTERNAL_SERVICE_TOKEN || "";
const inferTimeoutMs = Number(process.env.WORKER_INFER_TIMEOUT_MS) || 5000;

const mongoClient = new MongoClient(mongoUri);
const redis = new Redis(redisUrl, { maxRetriesPerRequest: null, lazyConnect: true });
const consumerRedis = new Redis(redisUrl, { maxRetriesPerRequest: null, lazyConnect: true });

let stopping = false;
let consumerLoopPromise = null;

async function checkHealth() {
  const health = { service: "worker", status: "ok", timestamp: new Date().toISOString(), queue: queueName };

  try {
    await redis.ping();
  } catch {
    health.status = "degraded";
    health.redis = "disconnected";
  }

  try {
    await mongoClient.db().command({ ping: 1 });
  } catch {
    health.status = "degraded";
    health.mongo = "disconnected";
  }

  return health;
}

const app = express();

app.get("/health", async (_req, res) => {
  const health = await checkHealth();
  res.status(health.status === "ok" ? 200 : 503).json(health);
});

async function main() {
  await mongoClient.connect();
  await redis.connect();
  await consumerRedis.connect();

  const db = mongoClient.db();
  const collection = db.collection("ai_jobs");

  const server = app.listen(port, "0.0.0.0", () => {
    console.log(`[worker] listening on port ${port}`);
  });

  consumerLoopPromise = runConsumerLoop({
    redis: consumerRedis,
    collection,
    aiConfig: { baseUrl: aiServiceUrl, token: internalServiceToken, timeoutMs: inferTimeoutMs },
    queueName,
    shouldStop: () => stopping,
  });

  async function shutdown(signal) {
    console.log(`[worker] received ${signal}, shutting down`);
    stopping = true;
    await consumerLoopPromise;
    server.close();
    await consumerRedis.quit();
    await redis.quit();
    await mongoClient.close();
    process.exit(0);
  }

  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

main().catch((err) => {
  console.error("[worker] fatal startup error", err);
  process.exit(1);
});
