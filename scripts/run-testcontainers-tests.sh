#!/usr/bin/env bash
# Run backend integration tests that use testcontainers (self-provisioning
# Postgres/Redis via Docker API) from inside an ephemeral container.
#
# Эти 4 тест-файла НЕ запускаются из обычного dev-контейнера (portal-backend-1),
# потому что testcontainers нужен доступ к docker.sock, а dev-overlay намеренно
# его не пробрасывает (см. docs/testing.md §«Две категории integration-тестов»).
# Этот скрипт запускает ephemeral-контейнер в host-сети с проброшенным сокетом,
# где testcontainers корректно поднимает sibling-контейнеры Postgres/Redis.
#
# Какие файлы покрывает:
#   tests/integration/test_migrations.py        — все 84 миграции на чистой БД (✓ работает)
#   tests/integration/test_migrations_nightly.py — nightly-версия (✓ работает с NIGHTLY=true)
#   tests/integration/test_local_auth.py        — dual-auth / SSO / bootstrap-admin (✓ работает)
#   tests/integration/test_helpdesk_ingress.py  — email-polling ingress (⚠️ ГИБРИДНЫЙ:
#     требует и testcontainers-IMAP, и portal-БД через DATABASE_URL; для него нужны
#     доп. env DATABASE_URL/REDIS_URL/SECRET_KEY на опубликованные dev-сервисы —
#     запускайте отдельно: см. конец файла)
#
# Usage:
#   ./scripts/run-testcontainers-tests.sh                              # дефолтный набор (3 чистых файла)
#   ./scripts/run-testcontainers-tests.sh tests/integration/test_migrations.py  # конкретный файл
#   ./scripts/run-testcontainers-tests.sh -k test_migration_revision_round_trip  # pytest-фильтр
#   NIGHTLY=true ./scripts/run-testcontainers-tests.sh                 # включить nightly-тесты
#
# Требования:
#   - запущенный Docker daemon (docker.sock на хосте)
#   - собранный образ portal-backend:dev (через setup.sh → «Разработка»)
#   - не требует локального python/deps — всё внутри контейнера
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

IMAGE="${PORTAL_DEV_IMAGE:-portal-backend:dev}"

# Проверяем, что образ собран (setup.sh → «Разработка» его создаёт).
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "❌ Образ $IMAGE не найден." >&2
  echo "   Сначала поднимите dev-стек: ./setup.sh → пункт «Разработка»." >&2
  exit 1
fi

# Проверяем docker.sock (WSL2: стандартный путь; при нестандартном — переопределить DOCKER_SOCKET).
DOCKER_SOCKET="${DOCKER_SOCKET:-/var/run/docker.sock}"
if [[ ! -S "$DOCKER_SOCKET" ]]; then
  echo "❌ docker.sock не найден в $DOCKER_SOCKET." >&2
  echo "   Если у вас нестандартный путь (WSL2 Docker Desktop иногда использует" >&2
  echo "   /mnt/wsl/docker-desktop/shared-sockets/docker.sock) — задайте DOCKER_SOCKET." >&2
  exit 1
fi

# По умолчанию — чистые testcontainers-файлы (полностью self-contained, поднимают
# собственную БД через Docker API). test_helpdesk_ingress.py исключён — он гибридный
# (нужен и testcontainers-IMAP, и DATABASE_URL на portal-БД), см. замечание в шапке.
# Аргументы скрипта пробрасываются в pytest как есть.
if [[ $# -eq 0 ]]; then
  PYTEST_ARGS=(tests/integration/test_migrations.py tests/integration/test_local_auth.py)
else
  PYTEST_ARGS=("$@")
fi

echo "==> Запуск testcontainers-тестов в ephemeral-контейнере (image=$IMAGE)"
echo "    Pytest args: ${PYTEST_ARGS[*]}"
echo

# Ключевые параметры:
#   --network host              — testcontainers-сеть видна через localhost хоста
#                                 (не применимо к живому portal-backend, т.к. ломает DNS
#                                  имён сервисов postgres/redis/screenshot-service; здесь
#                                  ephemeral-контейнер, поэтому безопасно)
#   -v docker.sock              — testcontainers обращается к Docker API
#   -v backend:/app             — тесты и app-код (read-only не делаем: pytest пишет .pytest_cache)
#   TESTCONTAINERS_RYUK_DISABLED — отключает reaper-контейнер (он не нужен для short-lived run,
#                                  и его создание иногда спотыкается о сеть)
#   DATABASE_URL/REDIS_URL      — на всякий случай; testcontainers их не использует,
#                                  но некоторые фикстуры могут читать env до старта контейнера
exec docker run --rm \
  --network host \
  -v "$DOCKER_SOCKET:/var/run/docker.sock" \
  -v "$ROOT_DIR/backend:/app" \
  -w /app \
  -e INTEGRATION_DB=true \
  -e INTEGRATION_REDIS=true \
  -e TESTCONTAINERS_RYUK_DISABLED=true \
  -e NIGHTLY="${NIGHTLY:-false}" \
  portal-backend:dev \
  bash -c "python -m pytest --no-header --no-cov -p no:cacheprovider \"\$@\"" -- "${PYTEST_ARGS[@]}"
