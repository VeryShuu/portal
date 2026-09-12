#!/usr/bin/env bash
# Ratchet для Vue-warnings (аудит тестирования 2026-08-21, этап 6).
#
# Запускает vitest unit-прогон, считает предупреждения [Vue warn] в выводе
# и проваливает шаг, если их больше baseline. baseline можно только понижать:
# повышение = регресс качества тестов и должно быть осознанным решением
# (см. scripts/vue-warnings-baseline.txt).
#
# Usage:
#   bash scripts/check-vue-warnings.sh              # обычный прогон
#   bash scripts/check-vue-warnings.sh --coverage   # как CI-джоба vitest
set -euo pipefail

cd "$(dirname "$0")/.."

BASELINE_FILE="scripts/vue-warnings-baseline.txt"
BASELINE=$(grep -E '^[0-9]+$' "$BASELINE_FILE" | tail -1)
if [[ -z "$BASELINE" ]]; then
  echo "::error::В $BASELINE_FILE нет строки с числом baseline" >&2
  exit 1
fi

VITEST_ARGS=(run)
if [[ "${1:-}" == "--coverage" ]]; then
  VITEST_ARGS+=(--coverage)
fi

OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT

set +e
npx vitest "${VITEST_ARGS[@]}" 2>&1 | tee "$OUT"
VITEST_RC=${PIPESTATUS[0]}
set -e

# grep -c печатает 0 даже при пустом результате (exit 1), поэтому || true
COUNT=$(grep -c '\[Vue warn\]' "$OUT" || true)

echo
echo "==> Vue-warnings ratchet: ${COUNT:-0} (baseline: ${BASELINE})"
if (( ${COUNT:-0} > BASELINE )); then
  echo "::error::Vue-warnings выросли: ${COUNT} > baseline ${BASELINE}."
  echo "    Типы новых предупреждений:"
  grep '\[Vue warn\]' "$OUT" | sed 's/.*\[Vue warn\]: //' | cut -c1-70 \
    | sort | uniq -c | sort -rn | head -10 || true
  echo "    Почини их (моки должны отдавать настоящие ref(), композаблы с"
  echo "    lifecycle-хуками — вызываться через withSetup, обязательные props —"
  echo "    передаваться) или обоснованно обнови $BASELINE_FILE."
  exit 1
fi

exit "$VITEST_RC"
