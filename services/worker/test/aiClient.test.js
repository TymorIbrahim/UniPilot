"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { callAiInfer } = require("../src/aiClient");

function withStubbedFetch(impl, run) {
  const original = globalThis.fetch;
  globalThis.fetch = impl;
  return run().finally(() => {
    globalThis.fetch = original;
  });
}

test("callAiInfer builds the request and returns a normalized success shape", async () => {
  let capturedUrl;
  let capturedInit;

  await withStubbedFetch(
    async (url, init) => {
      capturedUrl = url;
      capturedInit = init;
      return {
        status: 200,
        ok: true,
        json: async () => ({ success: true, data: { result: { narrative: "x", stats: {} } } }),
      };
    },
    async () => {
      const outcome = await callAiInfer({
        baseUrl: "http://ai:3001",
        token: "secret-token",
        jobType: "academic_risk_narrative",
        input: { analysisId: "abc" },
        timeoutMs: 5000,
      });

      assert.equal(capturedUrl, "http://ai:3001/infer");
      assert.equal(capturedInit.method, "POST");
      assert.equal(capturedInit.headers["x-internal-service-token"], "secret-token");
      assert.equal(capturedInit.headers["Content-Type"], "application/json");
      assert.deepEqual(JSON.parse(capturedInit.body), {
        jobType: "academic_risk_narrative",
        input: { analysisId: "abc" },
      });

      assert.equal(outcome.status, 200);
      assert.equal(outcome.ok, true);
      assert.equal(outcome.body.data.result.narrative, "x");
    }
  );
});

test("callAiInfer returns status/ok for a 4xx response", async () => {
  await withStubbedFetch(
    async () => ({
      status: 400,
      ok: false,
      json: async () => ({ success: false, data: null, error: "Unsupported jobType: x" }),
    }),
    async () => {
      const outcome = await callAiInfer({
        baseUrl: "http://ai:3001",
        token: "t",
        jobType: "x",
        input: {},
        timeoutMs: 5000,
      });
      assert.equal(outcome.status, 400);
      assert.equal(outcome.ok, false);
    }
  );
});

test("callAiInfer returns status/ok for a 5xx response", async () => {
  await withStubbedFetch(
    async () => ({
      status: 500,
      ok: false,
      json: async () => {
        throw new Error("no body");
      },
    }),
    async () => {
      const outcome = await callAiInfer({
        baseUrl: "http://ai:3001",
        token: "t",
        jobType: "academic_risk_narrative",
        input: {},
        timeoutMs: 5000,
      });
      assert.equal(outcome.status, 500);
      assert.equal(outcome.ok, false);
      assert.equal(outcome.body, null);
    }
  );
});

test("callAiInfer returns networkError on a thrown fetch error", async () => {
  await withStubbedFetch(
    async () => {
      throw new Error("connection refused");
    },
    async () => {
      const outcome = await callAiInfer({
        baseUrl: "http://ai:3001",
        token: "t",
        jobType: "academic_risk_narrative",
        input: {},
        timeoutMs: 5000,
      });
      assert.deepEqual(outcome, { networkError: true });
    }
  );
});

test("callAiInfer returns timedOut when the abort signal fires", async () => {
  await withStubbedFetch(
    async () => {
      const err = new Error("timed out");
      err.name = "TimeoutError";
      throw err;
    },
    async () => {
      const outcome = await callAiInfer({
        baseUrl: "http://ai:3001",
        token: "t",
        jobType: "academic_risk_narrative",
        input: {},
        timeoutMs: 5000,
      });
      assert.deepEqual(outcome, { timedOut: true });
    }
  );
});
