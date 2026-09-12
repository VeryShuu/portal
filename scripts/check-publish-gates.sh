#!/usr/bin/env bash
# Ensure the publication barrier retains the exact required same-workflow checks.
set -euo pipefail

workflow_path="${1:-.forgejo/workflows/ci.yml}"

if [[ ! -f "$workflow_path" ]]; then
  echo "::error::Workflow not found: $workflow_path" >&2
  exit 1
fi

expected_gates=(
  backend-lint
  backend-unit
  backend-integration
  frontend-lint
  frontend-unit
  frontend-e2e
  compose-smoke
  screenshot-unit
  secrets-scan
  backend-coverage
  drift-checks
  fake-db-allowlist
  shellcheck
  bats
  quality-gates
  tests-generated-drift
  playwright-sync-check
  monitoring-config
  validate-release-tag
)

# This deliberately parses only the compact YAML list used by this workflow.
# A general YAML parser is unnecessary in the runner image, while an exact
# allowlist means a removed, renamed, duplicated, or unexpected gate fails
# before publication policy can silently drift.
mapfile -t actual_gates < <(awk '
  /^  publish-images:/ { in_publish = 1; next }
  in_publish && /^    needs:/ { in_needs = 1; next }
  in_needs && /^    [[:alpha:]][[:alnum:]_-]*:/ { exit }
  in_needs && /^[[:space:]]*-[[:space:]]+[[:alnum:]_-]+[[:space:]]*$/ {
    line = $0
    sub(/^[[:space:]]*-[[:space:]]+/, "", line)
    sub(/[[:space:]]+$/, "", line)
    print line
  }
' "$workflow_path")

if [[ ${#actual_gates[@]} -eq 0 ]]; then
  echo "::error::publish-images.needs is missing or empty" >&2
  exit 1
fi

declare -A expected_seen=()
declare -A actual_seen=()
for gate in "${expected_gates[@]}"; do
  expected_seen["$gate"]=1
done

failed=0
for gate in "${actual_gates[@]}"; do
  if [[ -n ${actual_seen[$gate]+x} ]]; then
    echo "::error::publish-images.needs contains duplicate gate: $gate" >&2
    failed=1
  fi
  actual_seen["$gate"]=1
  if [[ -z ${expected_seen[$gate]+x} ]]; then
    echo "::error::publish-images.needs contains unexpected gate: $gate" >&2
    failed=1
  fi
done

for gate in "${expected_gates[@]}"; do
  if [[ -z ${actual_seen[$gate]+x} ]]; then
    echo "::error::publish-images.needs is missing required gate: $gate" >&2
    failed=1
  fi
done

if [[ $failed -ne 0 ]]; then
  exit 1
fi

echo "publish-images has the expected ${#expected_gates[@]} same-workflow gates."
