// Spectral custom function: every operation must declare at least one
// 4xx/5xx response so generated clients get a typed error path.
"use strict";

module.exports = function (targetVal, opts, paths) {
  const responses = targetVal || {};
  const keys = Object.keys(responses);
  const hasError = keys.some((k) => /^[45]\d\d$/.test(k));
  if (hasError) return;
  return [
    {
      message: `Operation must declare at least one 4xx/5xx response (got: ${keys.join(", ") || "none"})`,
      path: [...paths.path, "responses"],
    },
  ];
};
