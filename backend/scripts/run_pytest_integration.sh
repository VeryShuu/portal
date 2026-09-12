#!/bin/sh
# DSN-based integration-тесты внутри живого portal-backend-1.
#
# Аудит тестирования 2026-08-23 (P1.3): прежний `pytest tests/` запускал ВЕСЬ
# набор, включая testcontainers-файлы — им нужен docker.sock, который в
# dev-контейнере намеренно отсутствует → docker.errors.DockerException.
# Скрипт запускает ровно один контур: DSN-integration (реальные PG/Redis
# dev-стека через DATABASE_URL/REDIS_URL контейнера).
#
# Review-2 (P2): test_helpdesk_ingress.py НЕ testcontainers (его IMAP-часть
# мокается, тесту нужна только portal-БД — 8 passed из dev-контейнера) —
# исключён из списка только test_migrations*.py.
#
# Testcontainers-контур (свой Postgres/Redis через Docker API) — отдельный
# скрипт из корня репо: ./scripts/run-testcontainers-tests.sh
set -e
cd /app
exec env INTEGRATION_DB=true INTEGRATION_REDIS=true \
    python -m pytest tests/integration \
    --ignore=tests/integration/test_migrations.py \
    --ignore=tests/integration/test_migrations_nightly.py \
    -q --no-header -p no:cacheprovider --no-cov "$@"
