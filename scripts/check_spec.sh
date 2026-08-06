#!/usr/bin/env bash
# S4 — API surface governance gate.
#
# 1. Spectral: lint the committed OpenAPI spec against .spectral.yaml
#    (oas:recommended + custom rules). Fails on any `error` severity.
# 2. oasdiff: detect breaking changes of the current spec vs the committed
#    baseline (docs/specs/openapi.base.json). Fails on any breaking change.
#
# Usage:
#   scripts/check_spec.sh                 # lint + breaking check
#   scripts/check_spec.sh --refresh-base  # promote current spec as new baseline
#
# Requires: spectral CLI on PATH (or npmx), oasdiff binary on PATH.
# CI installs both (see .github/workflows/ci.yml "spec-quality" job).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPEC="$ROOT/docs/specs/openapi.json"
BASE="$ROOT/docs/specs/openapi.base.json"
RULESET="$ROOT/.spectral.yaml"

SPECTRAL_BIN="${SPECTRAL_BIN:-}"
OASDIFF_BIN="${OASDIFF_BIN:-oasdiff}"

if [ "${1:-}" = "--refresh-base" ]; then
  cp "$SPEC" "$BASE"
  echo "Baseline updated: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo n/a) — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit 0
fi

echo "== Spectral lint ($SPEC)"
SPECTRAL_CMD="${SPECTRAL_BIN:-}"
if [ -z "$SPECTRAL_CMD" ]; then
  if command -v spectral >/dev/null 2>&1; then
    SPECTRAL_CMD=spectral
  else
    SPECTRAL_CMD="npx --yes @stoplight/spectral-cli"
  fi
fi
# shellcheck disable=SC2086
$SPECTRAL_CMD lint "$SPEC" --ruleset "$RULESET" --fail-severity error
echo "   OK"

echo "== oasdiff breaking vs baseline ($BASE)"
if ! command -v "$OASDIFF_BIN" >/dev/null 2>&1; then
  echo "!! '$OASDIFF_BIN' not on PATH — download from https://github.com/Tufin/oasdiff/releases" >&2
  exit 2
fi
if [ ! -f "$BASE" ]; then
  echo "!! no baseline at $BASE — run scripts/check_spec.sh --refresh-base" >&2
  exit 2
fi
"$OASDIFF_BIN" breaking --fail-on ERR "$BASE" "$SPEC"
echo "  OK (no breaking changes)"

echo "Spec governance checks passed."