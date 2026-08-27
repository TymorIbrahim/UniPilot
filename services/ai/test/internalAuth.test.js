"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { requireInternalServiceToken } = require("../src/internalAuth");

function fakeReq(headerValue) {
  return {
    get(name) {
      if (name === "x-internal-service-token") {
        return headerValue;
      }
      return undefined;
    },
  };
}

function fakeRes() {
  const res = {
    statusCode: null,
    body: null,
    status(code) {
      res.statusCode = code;
      return res;
    },
    json(payload) {
      res.body = payload;
      return res;
    },
  };
  return res;
}

test("rejects a missing token with 401", () => {
  const middleware = requireInternalServiceToken("secret");
  const res = fakeRes();
  let nextCalled = false;

  middleware(fakeReq(undefined), res, () => {
    nextCalled = true;
  });

  assert.equal(res.statusCode, 401);
  assert.equal(res.body.success, false);
  assert.equal(nextCalled, false);
});

test("rejects a wrong token with 401", () => {
  const middleware = requireInternalServiceToken("secret");
  const res = fakeRes();
  let nextCalled = false;

  middleware(fakeReq("wrong-token"), res, () => {
    nextCalled = true;
  });

  assert.equal(res.statusCode, 401);
  assert.equal(nextCalled, false);
});

test("calls next on a matching token", () => {
  const middleware = requireInternalServiceToken("secret");
  const res = fakeRes();
  let nextCalled = false;

  middleware(fakeReq("secret"), res, () => {
    nextCalled = true;
  });

  assert.equal(nextCalled, true);
  assert.equal(res.statusCode, null);
});

test("passes through when no token is configured", () => {
  const middleware = requireInternalServiceToken("");
  const res = fakeRes();
  let nextCalled = false;

  middleware(fakeReq(undefined), res, () => {
    nextCalled = true;
  });

  assert.equal(nextCalled, true);
});
