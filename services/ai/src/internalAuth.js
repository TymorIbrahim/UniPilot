"use strict";

function requireInternalServiceToken(expectedToken) {
  const normalizedExpected = String(expectedToken || "").trim();

  return function (req, res, next) {
    if (!normalizedExpected) {
      return next();
    }

    const provided = String(req.get("x-internal-service-token") || "").trim();
    if (provided !== normalizedExpected) {
      return res.status(401).json({
        success: false,
        data: null,
        error: "Unauthorized internal service request",
      });
    }

    return next();
  };
}

module.exports = { requireInternalServiceToken };
