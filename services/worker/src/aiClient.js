"use strict";

async function callAiInfer({ baseUrl, token, jobType, input, timeoutMs }) {
  let response;
  try {
    response = await fetch(`${baseUrl}/infer`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-internal-service-token": token,
      },
      body: JSON.stringify({ jobType, input }),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    if (err && err.name === "TimeoutError") {
      return { timedOut: true };
    }
    return { networkError: true };
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  return { status: response.status, ok: response.ok, body };
}

module.exports = { callAiInfer };
