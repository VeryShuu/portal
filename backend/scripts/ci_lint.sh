#!/usr/bin/env bash
# Локальная копия CI job'а «backend / ruff + mypy» (1:1, те же команды).
#
# Зачем: ruff/mypy/radon зафискированы на точные версии (==) в pyproject.toml,
# но локальный python может иметь ДРУГИЕ версии → локальная проверка расходится
# с CI (см. сессию 2026-07-24: mypy 2.0.0 vs CI 2.3.0 дали разные результаты).
# Этот скрипт создаёт/переиспользует изолированный venv с ТОЧНО теми же версиями,
# что `pip install -e ".[dev]"` ставит в CI, и гоняет те же команды.
#
# Использование:
#   ./scripts/ci_lint.sh          # ruff check + ruff format --check + mypy (как CI)
#   ./scripts/ci_lint.sh --recreate  # пересоздать venv (после обновления deps)
#
# Venv кэшируется в .venv-ci/ (в .gitignore). Первый запуск ~30с, последующие ~3с.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV=".venv-ci"
RECREATE=0
[[ "${1:-}" == "--recreate" ]] && RECREATE=1

# ── 1. Venv с точными deps (как pip install -e ".[dev]" в CI) ──────────────────
if [[ $RECREATE -eq 1 && -d "$VENV" ]]; then
    echo "→ Пересоздаю $VENV (--recreate)..."
    rm -rf "$VENV"
fi
if [[ ! -d "$VENV" ]]; then
    echo "→ Создаю изолированный venv $VENV (первый запуск)..."
    python3 -m venv "$VENV"
    echo "→ Устанавливаю deps (pip install -e .[dev]) — как CI..."
    "$VENV/bin/pip" install -q -e ".[dev]" 2>&1 | tail -2
fi

# ── 2. Проверка: версии совпадают с pyproject (иначе update нужен) ─────────────
echo "→ Версии инструментов:"
"$VENV/bin/ruff" --version
"$VENV/bin/mypy" --version
"$VENV/bin/radon" --version 2>/dev/null || true

# ── 3. Те же команды, что CI (job backend-lint, steps 5-7) ─────────────────────
echo
echo "═══ ruff check . ═══"
"$VENV/bin/ruff" check .

echo
echo "═══ ruff format --check . ═══"
"$VENV/bin/ruff" format --check .

echo
echo "═══ mypy . ═══"
"$VENV/bin/mypy" .

echo
echo "✅ Все CI-lint проверки пройдены (локально = CI)."
