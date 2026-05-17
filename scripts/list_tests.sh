#!/usr/bin/env bash
# REVIEW-2.8: автогенерация списка тестов в docs/tests.generated.md.
#
# Использование:
#   ./scripts/list_tests.sh            # обновить docs/tests.generated.md
#   OUT=/tmp/tests.md ./scripts/list_tests.sh
#
# Зависимости: pytest (через backend venv) и установленный vitest (frontend).

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-$ROOT/docs/tests.generated.md}"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

{
  echo "# Список тестов (auto-generated)"
  echo
  echo "> Сгенерировано \`scripts/list_tests.sh\` — не редактируйте вручную."
  echo "> Регенерируйте после добавления/удаления тестов."
  echo

  echo "## Backend (pytest --collect-only)"
  echo
  echo '```'
  if command -v pytest >/dev/null 2>&1; then
    ( cd "$ROOT/backend" && pytest --collect-only -q 2>/dev/null \
        | grep -E '::' \
        | sort \
        | uniq ) || echo "(pytest collection failed; check backend venv)"
  else
    echo "(pytest not installed in PATH)"
  fi
  echo '```'
  echo

  echo "## Frontend Vitest (tests/unit/*.spec.ts)"
  echo
  echo '```'
  find "$ROOT/frontend/tests/unit" -maxdepth 2 -name '*.spec.ts' -printf '%P\n' 2>/dev/null \
    | sort
  echo '```'
  echo

  echo "## Frontend Playwright E2E (tests/e2e/*.spec.ts)"
  echo
  echo '```'
  find "$ROOT/frontend/tests/e2e" -maxdepth 2 -name '*.spec.ts' -printf '%P\n' 2>/dev/null \
    | sort
  echo '```'
  echo

  echo "## k6 Load (load/*.js)"
  echo
  echo '```'
  find "$ROOT/load" -maxdepth 1 -name '*.js' -printf '%P\n' 2>/dev/null | sort
  echo '```'
} >"$TMP"

mv "$TMP" "$OUT"
trap - EXIT
echo "wrote $OUT"
