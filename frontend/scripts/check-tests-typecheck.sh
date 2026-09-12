#!/usr/bin/env bash
# Typecheck юнит-тестов фронтенда — строгий гейт (ноль ошибок).
#
# История (аудит-3, 2026-08-24): tests/unit (240+ spec-файлов) исторически не
# входили ни в один tsconfig — 283 ошибок типов были невидимы, а
# expectTypeOf-тесты (api-types.spec.ts) работали как no-op. Дыру закрыли
# ratchet'ом (baseline 283, только вниз) и сожгли двумя сериями:
#   - PR #128 (2026-08-25): 283 → 130
#   - PR #130 (2026-08-26): 130 → 0, гейт переведён в строгий режим
# С этого момента любая ошибка типов в tests/unit роняет CI.
#
# Guard'ы аудита-4 (P1) сохранены: крах НЕ по type-ошибкам (OOM/Killed/битый
# node_modules/npx ENOENT/конфиг-срыв) обязан давать красный прогон, а не
# ложнозелёный «0 ошибок».
#
# Usage:
#   bash scripts/check-tests-typecheck.sh          # локально
#   npm run typecheck:tests
set -euo pipefail

cd "$(dirname "$0")/.."

OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT

set +e
npx vue-tsc -p tsconfig.tests.json --noEmit 2>&1 | tee "$OUT"
TSC_RC=${PIPESTATUS[0]}
set -e

# Ошибки считаем С FILE-ПОЗИЦИЕЙ (file(line,col): error TS…): они появляются
# только если проверка реально выполнялась. Конфиг-срывы без позиции (TS5023
# unknown option и т.п.) отдельно ловит guard ниже.
# grep -c печатает 0 даже при пустом результате (exit 1), поэтому || true
COUNT=$(grep -Ec '\([0-9]+,[0-9]+\): error TS' "$OUT" || true)

# vue-tsc: 0=чисто; 1=ошибки; 2=иногда после ошибок (внутренний статус) —
# доверяем count'у при COUNT>0, но при COUNT==0 любой rc!=0 и любой rc>2 —
# инфраструктурный красный.
if (( TSC_RC > 2 )); then
  echo "::error::vue-tsc упал с rc=${TSC_RC} (инфраструктура), ошибок с позицией: ${COUNT}."
  exit 1
fi
if (( TSC_RC != 0 )) && (( COUNT == 0 )); then
  echo "::error::vue-tsc rc=${TSC_RC} без ошибок с file-позицией — крах без диагностики (OOM/конфиг?)."
  exit 1
fi
if (( TSC_RC == 0 )) && (( COUNT > 0 )); then
  echo "::error::Несогласованный прогон: rc=0, но ошибок с позицией ${COUNT}."
  exit 1
fi

echo
echo "==> tests/unit typecheck: ${COUNT} ошибок (гейт строгий, лимит 0)"
if (( COUNT > 0 )); then
  echo "::error::Ошибки типов в тестах недопустимы (гейт строгий с PR #130)."
  echo "    Топ файлов:"
  grep 'error TS' "$OUT" | sed 's/(.*//' | sort | uniq -c | sort -rn | head -10 || true
  echo "    Типизируй тест-код (моки — через satisfies/типизированные фабрики)"
  echo "    под реальные типы; не ослабляй типы тестов, чтобы «просто прошло»."
  exit 1
fi

exit 0
