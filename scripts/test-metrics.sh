#!/usr/bin/env bash
# Phase-5 monthly metrics: collected test counts + wall-time for unit suites.
#
# Targets:
#   - backend unit + security <= 90s
#   - frontend unit            <= 30s
#
# Usage:
#   ./scripts/test-metrics.sh
#   OUT=/tmp/metrics.txt ./scripts/test-metrics.sh
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-/dev/stdout}"

bk_count=""
bk_time=""
fe_count=""
fe_time=""

if command -v pytest >/dev/null 2>&1; then
  bk_count=$(cd "$ROOT/backend" && pytest tests/unit tests/security --collect-only -q 2>/dev/null \
    | tail -1 | awk '{print $1}')
  t0=$(date +%s)
  ( cd "$ROOT/backend" && pytest tests/unit tests/security --no-cov -q -p no:randomly >/dev/null 2>&1 ) || true
  bk_time=$(( $(date +%s) - t0 ))
fi

if [[ -d "$ROOT/frontend/node_modules" ]]; then
  t0=$(date +%s)
  ( cd "$ROOT/frontend" && npm run test:unit -- --run >/dev/null 2>&1 ) || true
  fe_time=$(( $(date +%s) - t0 ))
  fe_count=$(cd "$ROOT/frontend" && grep -rEc '^[[:space:]]*(it|test)\(' tests/unit 2>/dev/null \
    | awk -F: '{s+=$2} END {print s}')
fi

{
  echo "# Test metrics ($(date -Iseconds))"
  echo
  printf "%-40s %10s %10s %10s\n" "Suite" "Count" "Wall(s)" "Target(s)"
  printf "%-40s %10s %10s %10s\n" "backend unit+security" "${bk_count:-?}" "${bk_time:-?}" "90"
  printf "%-40s %10s %10s %10s\n" "frontend unit" "${fe_count:-?}" "${fe_time:-?}" "30"
} > "$OUT"

if [[ "$OUT" != "/dev/stdout" ]]; then
  cat "$OUT"
fi
