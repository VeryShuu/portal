#!/usr/bin/env bash
# REVIEW-2.8: автогенерация списка тестов в docs/tests.generated.md.
#
# Использование:
#   ./scripts/list_tests.sh            # обновить docs/tests.generated.md
#   OUT=/tmp/tests.md ./scripts/list_tests.sh
#
# Зависимости: pytest (через backend venv); Vitest-инвентарь — npx vitest
# (frontend/node_modules), остальное — find/grep.

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
    # pytest 9 in WSL can fail while tearing down captured output after an
    # otherwise successful collection. ``-s`` disables capture; collection is
    # still quiet and produces stable node IDs for this generated document.
    ( cd "$ROOT/backend" && pytest --collect-only -q -s 2>/dev/null \
        | grep -E '::' \
        | sort \
        | uniq ) || echo "(pytest collection failed; check backend venv)"
  else
    echo "(pytest not installed in PATH)"
  fi
  echo '```'
  echo

  echo "## Frontend Vitest — тест-кейсы (vitest list, tests/unit)"
  echo
  echo "> Полные ID из \`vitest list\` (файл > describe > тест), а не только имена"
  echo "> файлов (PA-006): удаление/переименование отдельного теста теперь"
  echo "> меняет инвентарь. Сортировка — для стабильного diff."
  echo
  echo '```'
  if [ -d "$ROOT/frontend/node_modules" ] && command -v npx >/dev/null 2>&1; then
    ( cd "$ROOT/frontend" && npx vitest list tests/unit 2>/dev/null | sort ) \
      || echo "(vitest list failed; cd frontend && npm ci)"
  else
    echo "(vitest not available; cd frontend && npm ci)"
  fi
  echo '```'
  echo

  echo "## Frontend Playwright E2E (tests/e2e/*.spec.ts)"
  echo
  echo '```'
  find "$ROOT/frontend/tests/e2e" -maxdepth 2 -name '*.spec.ts' -printf '%P\n' 2>/dev/null \
    | sort
  echo '```'
  echo

  echo "## Frontend Playwright E2E — тест-кейсы (review-2/3, P2)"
  echo
  echo "> Имена тестов внутри спек: drift-гейт ловит и удаление отдельного"
  echo "> теста (45 → 44 passed раньше не замечал ни один гейт). Дубликаты"
  echo "> одинаковых имён НЕ схлопываются (uniq -c показывает количество),"
  echo "> кавычки — одинарные и двойные; поддержка алиасов импорта (PA-006:"
  echo "> 'import { test as setup }' → вызовы setup('...') в auth.setup.ts)."
  echo
  echo '```'
  # test('...') / test.describe('...') по всем e2e-файлам (включая setup),
  # с одинарными и двойными кавычками; ведущие пробелы нормализуем.
  # Алиасы: 'import { test as setup }' переименовывает test — собираем их
  # и добавляем в паттерн, иначе setup-кейсы выпадают из инвентаря.
  ALIASES=$(grep -hoE "import[[:space:]]*\{[^}]*test[[:space:]]+as[[:space:]]+[A-Za-z_\$]+" \
    "$ROOT"/frontend/tests/e2e/*.ts 2>/dev/null \
    | grep -oE "[A-Za-z_\$]+$" | sort -u | tr '\n' '|' | sed 's/|$//') || ALIASES=""
  PATTERN="^[[:space:]]*(test\.describe|test"
  if [ -n "$ALIASES" ]; then PATTERN="$PATTERN|$ALIASES"; fi
  PATTERN="$PATTERN)(\.describe)?\(['\"][^'\"]+['\"]"
  grep -hoE "$PATTERN" \
    "$ROOT"/frontend/tests/e2e/*.ts 2>/dev/null \
    | sed -E "s/^[[:space:]]*//" | sort | uniq -c | sed -E "s/^ *([0-9]+) /\1× /"
  echo '```'
  echo

  echo "## Screenshot-service (pytest, корень screenshot-service/)"
  echo
  echo "> Review-2/3, P2: раньше job покрывался только cookie_utils — удаление"
  echo "> test_main.py не замечал ни один drift-гейт; имена включают async-"
  echo "> методы (в первой редакции схлопывались в одну строку «def test_»)."
  echo
  echo '```'
  grep -hoE "^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+test_[A-Za-z0-9_]+|^[[:space:]]*class[[:space:]]+Test[A-Za-z0-9_]+" \
    "$ROOT"/screenshot-service/test_*.py 2>/dev/null \
    | sed -E "s/^[[:space:]]*//" | sort | uniq -c | sed -E "s/^ *([0-9]+) /\1× /"
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
