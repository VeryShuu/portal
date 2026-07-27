#!/usr/bin/env bash
# Run backend integration tests against an isolated docker-compose test stack.
#
# Usage:
#   ./scripts/test-integration.sh                    # full run
#   ./scripts/test-integration.sh path/to/test.py    # subset
#
# Env overrides:
#   KEEP_STACK=1     keep postgres-test/redis-test running after the run
#   COMPOSE_FILE     defaults to docker-compose.test.yml
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.test.yml}"
PG_PORT="${PG_PORT:-5433}"
REDIS_PORT="${REDIS_PORT:-6380}"

# Bootstrap-настройки (SECRET_KEY и пр.) — из корневого .env, чтобы alembic и
# pytest могли построить Settings(). Используем `set -a` чтобы экспортировать
# все переменные файла, затем восстанавливаем режим (caller-override важнее:
# DATABASE_URL/REDIS_URL ниже намеренно перенаправляются на test-stack).
# Файл может отсутствовать (свежий checkout) — тогда ждём, что caller передаст
# нужные env сам; в противном случае alembic упадёт с понятной ошибкой.
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

# docker-compose.test.yml — генерируемый файл (как dev/staging), он не в git.
# Если его нет (свежий checkout без запуска setup.sh) — генерируем на лету.
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "==> $COMPOSE_FILE не найден — генерирую через setup.sh gen-dev-files..."
  bash setup.sh gen-dev-files
fi

cleanup() {
  if [[ "${KEEP_STACK:-0}" != "1" ]]; then
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "==> Starting test stack ($COMPOSE_FILE)..."
docker compose -f "$COMPOSE_FILE" up -d --wait

export INTEGRATION_DB=true
export DATABASE_URL="postgresql+asyncpg://test:test@localhost:${PG_PORT}/test"
export REDIS_URL="redis://localhost:${REDIS_PORT}/0"

cd "$ROOT_DIR/backend"

echo "==> Running alembic upgrade head..."
python3 -m alembic upgrade head

echo "==> Running pytest -m integration..."
if [[ $# -gt 0 ]]; then
  python3 -m pytest -m integration --no-cov "$@"
else
  python3 -m pytest tests/integration -m integration --no-cov
fi
