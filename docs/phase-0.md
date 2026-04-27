# Phase 0 — Инфраструктура

> **Статус:** ✅ готово (см. [`AGENTS.md`](../AGENTS.md) → раздел «Текущий статус реализации»).

Документ собирает практические заметки по фазе 0, на которую ссылается `AGENTS.md`.
Подробности по более поздним фазам — в [`implementation-details.md`](./implementation-details.md).

---

## Что сделано в Phase 0

- Docker Compose со всеми сервисами (postgres, redis, backend, worker, frontend, nginx).
- PostgreSQL 16 на кастомном образе с hunspell-ru словарём (`postgres/Dockerfile`).
- Redis 7-alpine с requirepass + maxmemory `allkeys-lru`.
- Backend skeleton: FastAPI + SQLAlchemy 2.x async + Alembic, structlog, Sentry, Prometheus.
- Worker: ARQ.
- Frontend skeleton: Vue 3 + Vite + Naive UI + Pinia + TanStack Query + vue-i18n.
- Nginx как обратный прокси, TLS, IP-whitelist (geo), security headers, CSP.
- GitHub Actions: `ci.yml` (lint + unit + integration + e2e + load), `build.yml` (образы),
  `security.yml` (gitleaks, pip-audit, npm audit, Trivy).
- Миграция `init.sql` (расширения `pgcrypto`, `unaccent`, `pg_trgm`, hunspell FTS-конфигурация,
  партиции `audit_log`).

---

## Smoke-test (вариант 1 — backend only)

```bash
cp .env.example .env
docker compose up -d postgres redis migrations backend
docker compose logs -f migrations    # дождаться exit 0
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/ready
```

Ожидание:
- `migrations` → exit code 0 после `alembic upgrade head`.
- `backend` → healthy, `/health` 200, `/ready` 200 если PG+Redis OK.

---

## Вариант 2 — full-stack smoke-test

Для запуска полного стека (включая nginx + frontend) нужны TLS-сертификаты:

```bash
mkdir -p system_data/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout system_data/certs/portal.key \
    -out system_data/certs/portal.crt \
    -subj "/CN=localhost"
chmod 600 system_data/certs/portal.key

docker compose up -d
docker compose ps    # все 7 сервисов: postgres, redis, migrations(exited 0), backend, worker, frontend, nginx
curl -k https://localhost/health
```

Без сертификатов `portal-nginx` не стартует (см. [`AGENTS.md`](../AGENTS.md#critical-tls-сертификаты)).
В git коммитятся только заглушки (`nginx/certs/.gitkeep` устаревший — реальные ключи в `system_data/certs/`).

---

## История критичных фиксов Phase 0

| # | Проблема | Решение |
|---|----------|---------|
| 1 | `postgres:16-alpine` не содержит hunspell-словарей → `init.sql` падает на `CREATE TEXT SEARCH DICTIONARY` | Кастомный `postgres/Dockerfile` с `apt-get install hunspell-ru`. |
| 2 | Playwright/Chromium недоступен под `USER portal` в backend-образе | `chown -R portal:portal /ms-playwright` перед `USER portal`. |
| 3 | `structlog.PrintLoggerFactory()` несовместим с `add_logger_name` процессором | Использовать `structlog.stdlib.LoggerFactory()`. |
| 4 | Nginx `add_header Content-Security-Policy "..." always;` с переносом → `[emerg] invalid number of arguments` | CSP пишется одной строкой. |
| 5 | Naive UI бросает «No outer `<n-message-provider />`» | Все три провайдера `NMessageProvider → NDialogProvider → NNotificationProvider` обязательны в `App.vue`. |
| 6 | Pydantic `EmailStr` падает на `.local`-доменах | Для эндпоинтов с корпоративной почтой использовать `email: str = Field(min_length=1)`. |
| 7 | Race миграций при `--workers 2` | Миграции вынесены в отдельный compose-сервис `migrations` (`scripts/migrate.sh`). |

---

## Дальше

После Phase 0 → Phase 1 (Auth + Users + News). Подробности по последующим фазам:
- Полный список → [`AGENTS.md`](../AGENTS.md) → раздел «Текущий статус реализации».
- Детали реализации → [`implementation-details.md`](./implementation-details.md).
