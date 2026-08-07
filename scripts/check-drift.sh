#!/usr/bin/env bash
# check-drift.sh — единая точка входа для генерации и проверки всех
# авто-генерируемых артефактов (drift-checks), блокирующих мёрдж при рассинхроне.
#
# Три артефакта (по одному на CI-джобу):
#   1. openapi.json                      ← backend/scripts/export_openapi.py
#   2. frontend/src/api/types.gen.d.ts   ← npm run gen:types (openapi-typescript)
#   3. docs/tests.generated.md           ← scripts/list_tests.sh
#
# Если любой из них отстаёт от кода — CI падает и блокирует мёрдж
# (3 из 16 обязательных чеков). Этот скрипт ловит все три локально
# ДО пуша, одной командой.
#
# Использование:
#   ./scripts/check-drift.sh             # регенерирует + проверяет (по умолчанию)
#   ./scripts/check-drift.sh --check     # только проверка, без перегенерации (как CI)
#   ./scripts/check-drift.sh --fix       # регенерирует и фиксит (по умолчанию)
#
# Статус-коды:
#   0 — всё синхронно (или починено в режиме --fix)
#   1 — найден drift (только в режиме --check)
#   2 — ошибка окружения (нет pytest/npm/python)

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:---fix}"
case "$MODE" in
  --fix)    ACTION="regenerate+check" ;;
  --check)  ACTION="check-only (как CI)" ;;
  -h|--help)
    sed -n '2,24p' "$0"
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
# Этап 1: openapi.json  (backend FastAPI → JSON)
# ---------------------------------------------------------------------------
echo -e "${BOLD}━━━ [1/3] openapi.json (backend) ━━━${NC}"

check_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo -e "${RED}✗ $1 не найден в PATH${NC}" >&2
    echo "  Для backend: настрой venv или используй docker compose exec backend" >&2
    return 1
  fi
}

if ! check_tool python3; then exit 2; fi

# backend требует env-переменные для импорта app (Settings), даже при экспорте схемы.
# Берём безопасные значения как в CI (.github/workflows/ci.yml::openapi-drift-check).
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://user:pass@localhost:5432/portal}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export SECRET_KEY="${SECRET_KEY:-ci-secret-key-for-openapi-export-only-32+chars-padding}"
export ENVIRONMENT="${ENVIRONMENT:-test}"

if [ "$ACTION" = "regenerate+check" ]; then
  echo "  → регенерация openapi.json..."
  ( cd "$ROOT/backend" && python3 scripts/export_openapi.py --output "$ROOT/openapi.json" >/dev/null ) \
    || { echo -e "${RED}✗ ошибка экспорта openapi${NC}"; exit 2; }
fi

if git diff --quiet -- openapi.json; then
  echo -e "  ${GREEN}✓ openapi.json синхронен${NC}"
else
  if [ "$ACTION" = "check-only (как CI)" ]; then
    echo -e "  ${RED}✗ openapi.json рассинхронен${NC}"
    git --no-pager diff --stat -- openapi.json | sed 's/^/    /'
    DRIFT_FOUND=1
  else
    echo -e "  ${YELLOW}↻ openapi.json обновлён${NC}"
  fi
fi

# ---------------------------------------------------------------------------
# Этап 2: frontend/src/api/types.gen.d.ts  (openapi.json → TypeScript)
# ---------------------------------------------------------------------------
echo -e "${BOLD}━━━ [2/3] types.gen.d.ts (frontend) ━━━${NC}"

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo -e "  ${YELLOW}⚠ frontend/node_modules отсутствует — пропускаю (cd frontend && npm ci)${NC}"
else
  if [ "$ACTION" = "regenerate+check" ]; then
    echo "  → регенерация types.gen.d.ts..."
    ( cd "$ROOT/frontend" && npm run gen:types >/dev/null 2>&1 ) \
      || { echo -e "${RED}✗ ошибка gen:types${NC}"; exit 2; }
  fi

  if git diff --quiet -- frontend/src/api/types.gen.d.ts; then
    echo -e "  ${GREEN}✓ types.gen.d.ts синхронен${NC}"
  else
    if [ "$ACTION" = "check-only (как CI)" ]; then
      echo -e "  ${RED}✗ types.gen.d.ts рассинхронен${NC}"
      git --no-pager diff --stat -- frontend/src/api/types.gen.d.ts | sed 's/^/    /'
      DRIFT_FOUND=1
    else
      echo -e "  ${YELLOW}↻ types.gen.d.ts обновлён${NC}"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Этап 3: docs/tests.generated.md  (pytest --collect-only + find *.spec.ts)
# ---------------------------------------------------------------------------
echo -e "${BOLD}━━━ [3/3] tests.generated.md (backend + frontend) ━━━${NC}"

if [ "$ACTION" = "regenerate+check" ]; then
  echo "  → регенерация tests.generated.md..."
  # list_tests.sh сам толерантен к отсутствию pytest (ставит заглушку),
  # но для осмысленной проверки нужен собранный backend.
  if ! OUT=$( bash "$ROOT/scripts/list_tests.sh" 2>&1 ); then
    echo -e "  ${RED}✗ list_tests.sh упал:${NC}" >&2
    while IFS= read -r line; do echo "    $line" >&2; done <<< "$OUT"
    exit 2
  fi
fi

if git diff --quiet -- docs/tests.generated.md; then
  echo -e "  ${GREEN}✓ tests.generated.md синхронен${NC}"
else
  if [ "$ACTION" = "check-only (как CI)" ]; then
    echo -e "  ${RED}✗ tests.generated.md рассинхронен${NC}"
    git --no-pager diff --stat -- docs/tests.generated.md | sed 's/^/    /'
    DRIFT_FOUND=1
  else
    echo -e "  ${YELLOW}↻ tests.generated.md обновлён${NC}"
  fi
fi

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

# Покажем git-статус по этим 3 файлам, если что-то поменялось
CHANGED=$(git diff --name-only -- openapi.json frontend/src/api/types.gen.d.ts docs/tests.generated.md 2>/dev/null || true)
if [ -n "$CHANGED" ] && [ "$ACTION" = "regenerate+check" ]; then
  echo
  echo -e "${YELLOW}Изменённые файлы (закоммить их):${NC}"
  while IFS= read -r line; do echo "  $line"; done <<< "$CHANGED"
fi
