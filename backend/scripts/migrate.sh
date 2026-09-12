#!/bin/sh
set -eux
# Применение Alembic-миграций. Запускается одноразовым compose-сервисом `migrations`
# до старта `backend` и `worker`.
echo "[migrate] migrations directory listing:"
ls -la /app/migrations/versions/ | tail -n 20
# Ревизия — ВСЕГДА последняя строка вывода alembic: любые лог-строки
# (INFO alembic, предупреждения библиотек при импорте env.py) оказываются
# выше, и парсинг «первой строки» ловил мусор вместо ревизии.
_alembic_rev() {
    _rev=$(alembic "$1" 2>/dev/null | tail -n 1 | awk '{print $1}')
    echo "${_rev:-}"
}
echo "[migrate] alembic heads (target):"
HEADS=$(_alembic_rev heads | sort -u)
echo "$HEADS"
echo "[migrate] current revision before upgrade:"
BEFORE=$(_alembic_rev current)
echo "${BEFORE:-<none>}"
echo "[migrate] applying alembic upgrade head..."
_MIGRATE_MAX_RETRIES=5
_MIGRATE_RETRY_DELAY=5
_migrate_attempt=0
until alembic upgrade head; do
  _migrate_attempt=$((_migrate_attempt + 1))
  if [ "$_migrate_attempt" -ge "$_MIGRATE_MAX_RETRIES" ]; then
    echo "[migrate] FAIL: alembic upgrade head failed after $_MIGRATE_MAX_RETRIES attempts" >&2
    exit 1
  fi
  echo "[migrate] attempt $_migrate_attempt failed, retrying in ${_MIGRATE_RETRY_DELAY}s..." >&2
  sleep "$_MIGRATE_RETRY_DELAY"
done
echo "[migrate] revision after upgrade:"
AFTER=$(_alembic_rev current)
echo "${AFTER:-<none>}"
# Sanity-check: фактическая ревизия БД должна совпадать с head, иначе фейлим контейнер,
# чтобы compose НЕ запустил backend/worker на устаревшей схеме.
for H in $HEADS; do
  if [ "$AFTER" = "$H" ]; then
    echo "[migrate] OK: db at head $H"
    # Идемпотентная синхронизация пароля DB-роли learning_app с окружением:
    # миграция 102 ставит пароль только в момент применения, повторно alembic
    # её не запустит — «добавили LEARNING_DB_PASSWORD в .env позже» без этого
    # шага ломало learning-роуты (роль без пароля). Скрипт сам warning'ует
    # и завершается успешно, если переменная не задана (dev/тесты).
    if python -m scripts.ensure_learning_db_role; then
      exit 0
    fi
    echo "[migrate] FAIL: learning_app role sync failed" >&2
    exit 1
  fi
done
echo "[migrate] FAIL: db revision '$AFTER' does not match any head: $HEADS" >&2
exit 1
