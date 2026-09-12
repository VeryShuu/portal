#!/usr/bin/env bash
# check-drift.sh — единая точка входа для генерации и проверки всех
# авто-генерируемых артефактов (drift-checks), блокирующих мёрдж при рассинхроне.
#
# Артефакты (по одному на CI-джобу):
#   1. openapi.json                      ← backend/scripts/export_openapi.py
#   2. frontend/src/api/types.gen.d.ts   ← npm run gen:types (openapi-typescript)
#   3. docs/tests.generated.md           ← scripts/list_tests.sh
#   4. docs/db-schema.generated.md       ← backend/scripts/generate_db_schema_doc.py (PA-007)
#
# Если любой из них отстаёт от кода — CI падает и блокирует мёрж.
# Этот скрипт ловит все три локально ДО пуша, одной командой.
#
# Использование:
#   ./scripts/check-drift.sh             # регенерирует + проверяет (по умолчанию)
#   ./scripts/check-drift.sh --fix       # то же, явно
#   ./scripts/check-drift.sh --check     # как CI: регенерирует во временную копию
#                                        # и сравнивает с рабочим деревом, дерево
#                                        # не изменяет (PA-005: раньше --check только
#                                        # смотрел git diff и был ложно-зелёным)
#
# Статус-коды:
#   0 — всё синхронно (или починено в режиме --fix)
#   1 — найден drift (только в режиме --check)
#   2 — ошибка окружения (нет python/pytest/node_modules или регенерация упала)

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:---fix}"
case "$MODE" in
  --fix)    ACTION="regenerate+check" ;;
  --check)  ACTION="check-only (как CI)" ;;
  -h|--help)
    sed -n '2,28p' "$0"
    exit 0 ;;
  *)
    echo "Неизвестный флаг: $MODE" >&2
    echo "Использование: $0 [--fix|--check]" >&2
    exit 2 ;;
esac

# Цветной вывод (если терминал поддерживает)
if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; BOLD='\033[1m'; NC='\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; BOLD=''; NC=''
fi

DRIFT_FOUND=0

# ---------------------------------------------------------------------------
# Инструментарий: сначала CI-эквивалентное окружение.
# Урок 2026-08-16 (PR #58): системный python3 без deps бэкенда молча
# «зелёнил» экспорт. Если собран .venv-ci (scripts/ci_lint.sh) — берём
# его python/pytest (те же версии, что в CI).
# ---------------------------------------------------------------------------
PY_SRC="PATH (system)"
if [ -x "$ROOT/backend/.venv-ci/bin/python" ]; then
  export PATH="$ROOT/backend/.venv-ci/bin:$PATH"
  PY_SRC="backend/.venv-ci"
fi

check_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo -e "${RED}✗ $1 не найден в PATH${NC}" >&2
    echo "  Для backend: настрой venv или используй docker compose exec backend" >&2
    echo "  (либо собери CI-окружение: cd backend && ./scripts/ci_lint.sh)" >&2
    return 1
  fi
}

if ! check_tool python3; then exit 2; fi

# backend требует env-переменные для импорта app (Settings), даже при экспорте схемы.
# Берём безопасные значения как в CI (.forgejo/workflows/ci.yml::drift-checks).
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://user:pass@localhost:5432/portal}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export SECRET_KEY="${SECRET_KEY:-ci-secret-key-for-openapi-export-only-32+chars-padding}"
export ENVIRONMENT="${ENVIRONMENT:-test}"

regen_openapi() {
  ( cd "$ROOT/backend" && python3 scripts/export_openapi.py --output "$ROOT/openapi.json" >/dev/null )
}

regen_types() {
  ( cd "$ROOT/frontend" && npm run gen:types >/dev/null )
}

regen_tests() {
  bash "$ROOT/scripts/list_tests.sh" >/dev/null
}

regen_db_schema() {
  ( cd "$ROOT/backend" && python3 -m scripts.generate_db_schema_doc --output "$ROOT/docs/db-schema.generated.md" >/dev/null )
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# check_or_fix <название> <путь-к-артефакту> <функция-регенерации>
#   --check: снимок → регенерация → сравнение → восстановление дерева.
#   --fix:   регенерация на месте → отчёт «обновлён/синхронен».
check_or_fix() {
  local title="$1" path="$2" regen="$3"
  local snap=""
  if [ "$ACTION" = "check-only (как CI)" ]; then
    snap="$TMP/$(basename "$path").snap"
    cp "$path" "$snap"
  fi
  if ! "$regen"; then
    [ -n "$snap" ] && cp "$snap" "$path"
    echo -e "${RED}✗ регенерация $title упала (stderr выше)${NC}" >&2
    exit 2
  fi
  if [ "$ACTION" = "check-only (как CI)" ]; then
    if cmp -s "$path" "$snap"; then
      echo -e "  ${GREEN}✓ $(basename "$path") синхронен${NC}"
    else
      echo -e "  ${RED}✗ $(basename "$path") рассинхронен (регенерация ≠ рабочее дерево)${NC}"
      local excerpt
      excerpt="$(diff -u "$snap" "$path" | head -15 || true)"
      # shellcheck disable=SC2001  # отступ многострочного diff-фрагмента
      sed 's/^/    /' <<< "$excerpt"
      DRIFT_FOUND=1
    fi
    cp "$snap" "$path"   # рабочее дерево не трогаем
  else
    if git diff --quiet -- "$path"; then
      echo -e "  ${GREEN}✓ $(basename "$path") синхронен${NC}"
    else
      echo -e "  ${YELLOW}↻ $(basename "$path") обновлён${NC}"
    fi
  fi
}

echo -e "${BOLD}Инструменты: python/pytest из ${PY_SRC}; режим: ${ACTION}${NC}"

# ---------------------------------------------------------------------------
# Этап 1: openapi.json  (backend FastAPI → JSON)
# ---------------------------------------------------------------------------
echo -e "${BOLD}━━━ [1/4] openapi.json (backend) ━━━${NC}"

check_or_fix "openapi.json" "$ROOT/openapi.json" regen_openapi

# ---------------------------------------------------------------------------
# Этап 2: frontend/src/api/types.gen.d.ts  (openapi.json → TypeScript)
# ---------------------------------------------------------------------------
echo -e "${BOLD}━━━ [2/4] types.gen.d.ts (frontend) ━━━${NC}"

# node_modules нужен в ОБОИХ режимах: тихий пропуск в --fix так же оставлял
# stale-артефакт, как и git diff-only --check (PA-005). Кроме того, vitest
# list в tests.generated.md (PA-006) требует окружения frontend.
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo -e "${RED}✗ frontend/node_modules отсутствует — регенерация неполна${NC}" >&2
  echo "  cd frontend && npm ci   (и повтори ./scripts/check-drift.sh)" >&2
  exit 2
fi

check_or_fix "types.gen.d.ts" "$ROOT/frontend/src/api/types.gen.d.ts" regen_types

# ---------------------------------------------------------------------------
# Этап 3: docs/tests.generated.md  (pytest --collect-only + тест-кейсы FE)
# ---------------------------------------------------------------------------
echo -e "${BOLD}━━━ [3/4] tests.generated.md (backend + frontend) ━━━${NC}"

# В обоих режимах осмысленная регенерация требует pytest: без него
# list_tests.sh кладёт в документ заглушку, которую легко закоммитить.
if ! command -v pytest >/dev/null 2>&1; then
  echo -e "${RED}✗ pytest недоступен — инвентарь тестов не сгенерировать${NC}" >&2
  echo "  cd backend && ./scripts/ci_lint.sh   (соберёт .venv-ci с pytest)" >&2
  exit 2
fi

check_or_fix "tests.generated.md" "$ROOT/docs/tests.generated.md" regen_tests

# ---------------------------------------------------------------------------
# Этап 4: docs/db-schema.generated.md  (SQLAlchemy models → Markdown) (PA-007)
# ---------------------------------------------------------------------------
echo -e "${BOLD}━━━ [4/4] db-schema.generated.md (backend models) ━━━${NC}"

check_or_fix "db-schema.generated.md" "$ROOT/docs/db-schema.generated.md" regen_db_schema

# ---------------------------------------------------------------------------
# Итог
# ---------------------------------------------------------------------------
echo
if [ "$DRIFT_FOUND" -eq 1 ]; then
  echo -e "${RED}${BOLD}✗ DRIFT обнаружен${NC}"
  echo -e "${RED}  Перегенерируй: ${BOLD}./scripts/check-drift.sh${NC}"
  echo -e "${RED}  (или вручную команды выше) и закоммить результат.${NC}"
  exit 1
fi

if [ "$ACTION" = "regenerate+check" ]; then
  echo -e "${GREEN}${BOLD}✓ Все артефакты синхронны (было: регенерация, теперь чисто)${NC}"
else
  echo -e "${GREEN}${BOLD}✓ Все артефакты синхронны (check-only)${NC}"
fi
echo -e "  Команда запущена в режиме: ${BOLD}$ACTION${NC}"

# Покажем git-статус по артефактам, если что-то поменялось (--fix)
CHANGED=$(git diff --name-only -- openapi.json frontend/src/api/types.gen.d.ts docs/tests.generated.md docs/db-schema.generated.md 2>/dev/null || true)
if [ -n "$CHANGED" ] && [ "$ACTION" = "regenerate+check" ]; then
  echo
  echo -e "${YELLOW}Изменённые файлы (закоммить их):${NC}"
  while IFS= read -r line; do echo "  $line"; done <<< "$CHANGED"
fi
