#!/bin/sh
set -e
# Применение Alembic-миграций. Запускается одноразовым compose-сервисом `migrations`
# до старта `backend` и `worker`.
exec alembic upgrade head
