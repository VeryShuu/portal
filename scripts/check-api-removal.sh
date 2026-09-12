#!/usr/bin/env bash
# Phase-5 guard: when a public Python symbol or a TS export is removed in a
# commit, grep tests/ for surviving references. Catches the Bookmarks→Links
# style regression where deleted modules were still imported by stale tests.
#
# Usage (manual):
#   ./scripts/check-api-removal.sh                # diff against HEAD~1
#   ./scripts/check-api-removal.sh origin/main    # diff against origin/main
#
# Exit code 0 = no surviving references; 1 = potential stale test references.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE="${1:-HEAD~1}"

removed_py=$(git diff "$BASE"...HEAD -- 'backend/app/**/*.py' \
  | grep -E '^-(def |class |async def )' \
  | sed -E 's/^-(async )?(def|class) +([A-Za-z_][A-Za-z0-9_]*).*/\3/' \
  | sort -u || true)

removed_ts=$(git diff "$BASE"...HEAD -- 'frontend/src/**/*.ts' 'frontend/src/**/*.vue' \
  | grep -E '^-export (function|const|class|interface|type|default function) ' \
  | sed -E 's/^-export (function|const|class|interface|type|default function) ([A-Za-z_][A-Za-z0-9_]*).*/\2/' \
  | sort -u || true)

status=0

if [[ -n "$removed_py" ]]; then
  echo "==> Removed Python symbols:"
  echo "$removed_py" | sed 's/^/    /'
  echo "==> Surviving references in backend/tests/:"
  while IFS= read -r sym; do
    [[ -z "$sym" ]] && continue
    hits=$(grep -rnE "\b${sym}\b" backend/tests/ 2>/dev/null || true)
    if [[ -n "$hits" ]]; then
      echo "    $sym:"
      echo "$hits" | sed 's/^/        /'
      status=1
    fi
  done <<< "$removed_py"
fi

if [[ -n "$removed_ts" ]]; then
  echo "==> Removed TS/Vue exports:"
  echo "$removed_ts" | sed 's/^/    /'
  echo "==> Surviving references in frontend/tests/:"
  while IFS= read -r sym; do
    [[ -z "$sym" ]] && continue
    hits=$(grep -rnE "\b${sym}\b" frontend/tests/ 2>/dev/null || true)
    if [[ -n "$hits" ]]; then
      echo "    $sym:"
      echo "$hits" | sed 's/^/        /'
      status=1
    fi
  done <<< "$removed_ts"
fi

if [[ $status -eq 0 ]]; then
  echo "OK: no stale test references to removed symbols."
fi
exit $status
