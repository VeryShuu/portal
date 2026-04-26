# Implementation Details

Детальный состав реализованных файлов по фазам. Обновляй при завершении фазы.

---

## Phase 0 — Инфраструктура

**Backend (`backend/`):**
- `app/main.py` — FastAPI app, structlog, Sentry SDK, Prometheus, security headers middleware, request logging middleware
- `app/core/config.py` — Pydantic Settings v2 со всеми переменными + валидаторы
- `app/core/logging.py` — structlog: JSON в prod, ConsoleRenderer в dev
- `app/core/database.py` — SQLAlchemy 2.x async engine, `AsyncSessionLocal`, `Base`, `get_db()`
- `app/api/health.py` — `GET /health` (always 200) + `GET /ready` (DB + Redis, 200/503)
- `app/models/user.py` — SQLAlchemy модель `User` (все поля из db-schema.md)
- `app/worker/main.py` — ARQ `WorkerSettings` с cron-задачами аудита (каждые 2 сек flush + ежемесячное управление партициями)
- `app/worker/tasks/audit.py` — `flush_audit_queue`, `create_next_audit_partition`, `drop_old_audit_partitions`
- `migrations/init.sql` — расширения pgcrypto/unaccent/pg_trgm, FTS `russian_hunspell`, DO-блок создания первых 3 партиций `audit_log`
- `migrations/env.py` — Alembic async env (читает DATABASE_URL из Settings)
- `migrations/versions/001_initial_users.py` — таблицы `users` + `idempotency_keys`
- `scripts/create_audit_partitions.py` — CLI + async функции `ensure_partitions` / `drop_old_partitions`
- `pyproject.toml` — все зависимости (FastAPI, SQLAlchemy 2.x, ARQ, structlog, Playwright, python-docx, ...)

**Infrastructure:**
- `docker-compose.yml` — 6 сервисов: postgres, redis, backend, worker, frontend, nginx; healthcheck на `/ready`
- `postgres/Dockerfile` — `postgres:16` (Debian) + `apt install hunspell-ru` → автокопирование `.dict`/`.affix` в `tsearch_data/`
- `postgres/hunspell/russian.stop` — список стоп-слов для FTS
- `nginx/nginx.conf` — TLS 1.2+, HSTS, CSP, X-Frame-Options, geo IP-whitelist, SSE-локация с `proxy_buffering off`
- `.env.example` — все переменные с комментариями

**Frontend (`frontend/`):**
- `src/main.ts` — bootstrap: Vue 3 + Pinia + vue-i18n v9 + TanStack Query
- `src/App.vue` — `NConfigProvider` (Naive UI тема + locale)
- `src/router.ts` — базовые маршруты (home, auth/callback, 404)
- `src/stores/theme.ts` — Pinia store (dark/light, localStorage)
- `src/i18n/ru.json` + `en.json` — полный набор ключей для всех модулей
- `scripts/check-i18n.js` — CI-проверка паритета ключей ru↔en

**CI/CD (`.github/workflows/`):**
- `ci.yml` — ruff + mypy + pytest unit+integration + eslint + vue-tsc + i18n:check + vitest
- `build.yml` — сборка и push трёх образов в GHCR при merge в `main`

**Тесты (`backend/tests/`):**
- `unit/test_config.py` — 7 кейсов: валидация, defaults, ошибки
- `unit/test_health.py` — 6 кейсов: liveness/readiness, mock DB+Redis fail scenarios
- `unit/test_audit_partitions.py` — 9 кейсов: naming, create, skip existing, date ranges, drop old
- `integration/test_migrations.py` — Testcontainers PG16: upgrade→check columns/indexes→downgrade→upgrade again

---

## Phase 2.1 — Локальная аутентификация

**Backend (`backend/`):**
- `app/main.py` — функция `_bootstrap_admin()`: при старте создаёт первого admin из `ADMIN_EMAIL` + `ADMIN_PASSWORD` (env), если ещё нет ни одного admin в БД. Использует `AsyncSessionLocal` (не `async_session_factory`).
- `app/schemas/user.py` — класс `LocalLoginRequest`: поле `email: str` (не `EmailStr`) для поддержки `.local`-доменов (Pydantic `EmailStr` отклоняет non-deliverable домены через DNS)
- `app/api/auth.py` — endpoint `POST /api/v1/auth/local/login`: принимает `email` + `password`, проверяет bcrypt hash, создаёт Redis-сессию (единый механизм с Keycloak auth). Отвечает **унифицированным 401** на все ошибки (нет user enumeration); rate-limit 5/15 мин/IP по `X-Real-IP`
- `app/api/users.py` — endpoint `PATCH /api/v1/users/me/password`: смена пароля (только `auth_source = "local"`); admin-эндпоинты лежат под namespace `/api/v1/users/admin/*`
- `app/core/security.py` — функции `hash_password()` / `verify_password()` (bcrypt, cost≥12, SHA256 pre-hash)
- `app/core/limiter.py` — `real_ip_identifier`: rate-limit identifier на основе `X-Real-IP` от nginx (X-Forwarded-For игнорируется — обходится клиентом)
- `scripts/create_admin.py` — CLI-скрипт для ручного создания admin: пароль читается из env `ADMIN_PASSWORD` или интерактивно через `getpass()`, **не из argv**
- Миграция `versions/004_local_auth.py` — поля `auth_source VARCHAR(20) DEFAULT 'keycloak'` и `password_hash VARCHAR(255) NULL`; `keycloak_id` стал nullable; индекс `idx_users_source`

**Frontend (`frontend/`):**
- `src/App.vue` — добавлены провайдеры Naive UI: `NMessageProvider`, `NDialogProvider`, `NNotificationProvider`
- `src/pages/LoginPage.vue` — форма локального входа: email + password, вызов `/api/v1/auth/local/login`
- `src/api/auth.ts` — функция `localLogin(email, password)`: `ofetch POST` с `body: { email, password }`

**Критические инфра-фиксы (применены в этой фазе):**
- **`AsyncSessionLocal`** — в `app/core/database.py` фабрика сессий называется `AsyncSessionLocal`, не `async_session_factory`
- **`EmailStr` → `str`** — домен `.local` не проходит DNS-проверку → 422. Решение: `email: str = Field(min_length=1, max_length=255)` в `LocalLoginRequest`
- **Naive UI провайдеры** — все три провайдера добавлены в `App.vue`
- **nginx DNS resolver** — `resolver 127.0.0.11 valid=10s ipv6=off;` добавлен для резолвинга имён upstream-контейнеров
- **CSP** — `unsafe-eval` не нужен: Naive UI работает без него
- **DOMPurify на фронте** — все `v-html` обёрнуты в `DOMPurify.sanitize(html, { FORBID_TAGS: [...], FORBID_ATTR: [...] })`
- **Bootstrap admin race** — `_bootstrap_admin()` оборачивается в `pg_advisory_xact_lock(0x504F5254414C0001)`
- **Account-linking аудит** — `_upsert_user()` пишет `auth.account_linked` (warning)
- **bookmarks reorder lock** — `pg_advisory_xact_lock(BOOK_NS, user_hash)` вместо `with_for_update(User)`

**.env (добавлены переменные):**
- `LOCAL_AUTH_ENABLED=true`
- `ADMIN_EMAIL=admin@company.local`
- `ADMIN_PASSWORD=change_me_admin_password` (⚠️ сменить после первого входа)
