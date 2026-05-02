#!/bin/sh
set -eux
# Применение Alembic-миграций. Запускается одноразовым compose-сервисом `migrations`
# до старта `backend` и `worker`.
echo "[migrate] current revision before upgrade:"
alembic current || true
echo "[migrate] applying alembic upgrade head..."
alembic upgrade head
echo "[migrate] revision after upgrade:"
alembic current
