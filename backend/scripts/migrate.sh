#!/bin/sh
set -eux
# Применение Alembic-миграций. Запускается одноразовым compose-сервисом `migrations`
# до старта `backend` и `worker`.
echo "[migrate] migrations directory listing:"
ls -la /app/migrations/versions/ | tail -n 20
echo "[migrate] alembic heads (target):"
HEADS=$(alembic heads | awk '{print $1}' | sort -u)
echo "$HEADS"
echo "[migrate] current revision before upgrade:"
BEFORE=$(alembic current 2>/dev/null | awk 'NR==1{print $1}' || true)
echo "${BEFORE:-<none>}"
echo "[migrate] applying alembic upgrade head..."
alembic upgrade head
echo "[migrate] revision after upgrade:"
AFTER=$(alembic current 2>/dev/null | awk 'NR==1{print $1}' || true)
echo "${AFTER:-<none>}"
# Sanity-check: фактическая ревизия БД должна совпадать с head, иначе фейлим контейнер,
# чтобы compose НЕ запустил backend/worker на устаревшей схеме.
for H in $HEADS; do
  if [ "$AFTER" = "$H" ]; then
    echo "[migrate] OK: db at head $H"
    exit 0
  fi
done
echo "[migrate] FAIL: db revision '$AFTER' does not match any head: $HEADS" >&2
exit 1
