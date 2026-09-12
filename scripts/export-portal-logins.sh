#!/usr/bin/env bash
# export-portal-logins.sh — CSV-выгрузка логинов портала для сверки с 1С
# (регистр соответствия «логин портала → Пользователь 1С», модуль
# «Согласование документов», docs/approvals.md §7).
#
# Формат по договорённости с 1С: колонки email,full_name; UTF-8; только
# действующие сотрудники (users.deleted_at IS NULL). Запускать на сервере
# портала (docker compose из корня деплоя):
#
#   ./scripts/export-portal-logins.sh > portal_logins.csv
#
# Для периодической сверки (приёмы/увольнения) — та же команда.

set -euo pipefail

SERVICE="${SERVICE:-postgres}"
PG_USER="${POSTGRES_USER:-portal}"
PG_DB="${POSTGRES_DB:-portal}"

docker compose exec -T "$SERVICE" psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -c \
  "COPY (
       SELECT lower(email) AS email, full_name
       FROM users
       WHERE deleted_at IS NULL AND email <> ''
       ORDER BY 1
   ) TO STDOUT WITH (FORMAT csv, HEADER true)"
