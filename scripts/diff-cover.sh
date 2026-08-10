#!/usr/bin/env bash
# Diff-coverage гейт: проверяет, что новый/изменённый код в PR покрыт тестами.
#
# В отличие от абсолютного покрытия (coverage report --fail-under=N, который
# меряет весь кодовую базу целиком), diff-cover смотрит только на строки,
# добавленные/изменённые в текущей ветке относительно main. Это останавливает
# регресс: нельзя добавить непокрытый код, если общий % всё равно проходит порог.
#
# Поддерживает оба контура:
#   ./scripts/diff-cover.sh backend     # backend/coverage.xml (coverage.py, Cobertura-XML)
#   ./scripts/diff-cover.sh frontend    # frontend/coverage/lcov.info (vitest coverage-v8, LCOV)
#
# КРИТИЧНО (путь-мэтчинг): diff-cover сравнивает пути из coverage-отчёта с путями
# из `git diff`. Git отдаёт пути относительно repo-root (frontend/src/...,
# backend/app/...), а coverage-отчёты хранят пути относительно директории контура
# (src/..., app/...). diff-cover (GitPathTool.relative_path) приводит git-пути к
# виду относительно CWD. Поэтому скрипт ОБЯЗАН запускаться из директории контура.
#
# Переменные окружения:
#   THRESHOLD        (default 80) — минимальный % покрытия нового кода.
#   COMPARE_BRANCH   (default origin/main) — базовая ветка для diff.
#
# Пререквизиты:
#   - pip install "diff-cover>=9.2.0,<10"
#   - сгенерировать coverage-отчёт:
#       backend:  cd backend && pytest tests/unit --cov=app --cov-report=xml
#       frontend: cd frontend && npm run test:coverage
#   - в CI: артефакты backend-coverage / frontend-coverage уже содержат отчёты.
#
# Пример локального запуска (как в CI):
#   ./scripts/diff-cover.sh backend
#   ./scripts/diff-cover.sh frontend
set -euo pipefail

usage() {
  echo "Usage: $0 <backend|frontend>" >&2
  echo "  THRESHOLD=70 $0 backend    # переопределить порог" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
CONTOUR="$1"
THRESHOLD="${THRESHOLD:-80}"
COMPARE_BRANCH="${COMPARE_BRANCH:-origin/main}"

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

case "$CONTOUR" in
  backend)
    COV_FILE="$ROOT/backend/coverage.xml"
    WORK_DIR="$ROOT/backend"
    ;;
  frontend)
    COV_FILE="$ROOT/frontend/coverage/lcov.info"
    WORK_DIR="$ROOT/frontend"
    ;;
  *)
    echo "Error: неизвестный контур '$CONTOUR' (ожидалось backend|frontend)" >&2
    usage
    ;;
esac

if ! command -v diff-cover >/dev/null 2>&1; then
  echo "diff-cover не установлен; установите: pip install 'diff-cover>=9.2.0,<10'" >&2
  exit 2
fi

if [[ ! -f "$COV_FILE" ]]; then
  echo "Coverage-отчёт не найден: $COV_FILE" >&2
  case "$CONTOUR" in
    backend)  echo "Сгенерируйте: cd backend && pytest tests/unit --cov=app --cov-report=xml" >&2 ;;
    frontend) echo "Сгенерируйте: cd frontend && npm run test:coverage" >&2 ;;
  esac
  exit 2
fi

# Запуск ИЗ директории контура — иначе путь-мэтчинг ломается (см. комментарий в шапке).
cd "$WORK_DIR"
echo "─── diff-coverage: $CONTOUR (threshold ${THRESHOLD}%, compare ${COMPARE_BRANCH}) ───"
diff-cover "$COV_FILE" \
  --compare-branch "$COMPARE_BRANCH" \
  --fail-under "$THRESHOLD" \
  --show-uncovered
