# AI Agent — System Prompt

Ты — AI-разработчик корпоративного интранет-портала. Читай этот файл перед любой задачей.

---

## Проект

Корпоративный интранет-портал для ~300 сотрудников.
- Единая точка входа: новости, база знаний, файлы, ярлыки сервисов
- Только внутренняя сеть / VPN. Публичный доступ запрещён. Режим работы - через обратный прокси.
- Репозиторий: `C:\Users\admin\Documents\zen\portal\` (или `/workspace/portal/` в контейнере)

---

## Стек (зафиксирован, не менять без обсуждения)

### Frontend
| | |
|--|--|
| Framework | Vue 3 + TypeScript + Vite |
| UI-библиотека | **Naive UI** (не PrimeVue, не Vuetify) |
| State | Pinia |
| Router | Vue Router 4 |
| HTTP | **TanStack Query (Vue Query) + ofetch** |
| i18n | vue-i18n v9 (ru + en) |
| Редактор | **TipTap v2 + `tiptap-markdown`** (community package) |
| Markdown viewer | markdown-it или TipTap read-only |
| Хранение контента | **Markdown** (CommonMark + GFM) — source of truth |
| Тесты | Vitest + Vue Testing Library + Playwright (E2E) |

### Backend
| | |
|--|--|
| Language | Python 3.12 |
| Framework | **FastAPI** |
| ORM | SQLAlchemy 2.x (async) + Alembic |
| Auth | python-jose, httpx (OIDC/Keycloak) |
| Rate limiting | **fastapi-limiter** (не slowapi) |
| HTTP client | **httpx** (async) |
| Queue/Workers | **ARQ** |
| Logging | **structlog** (JSON → stdout) |
| Metrics | **prometheus-fastapi-instrumentator** |
| Error tracking | **Sentry SDK** |
| Markdown → HTML | markdown-it-py или mistune |
| PDF export | **Playwright/Chromium** (`page.pdf()`) |
| DOCX export | **python-docx** + markdown→html конвертер |
| File validation | python-magic |
| Sanitization | bleach |
| Тесты | **Pytest** + pytest-asyncio + Testcontainers |

### Infrastructure
| | |
|--|--|
| DB | **PostgreSQL 16** |
| Cache/Queue | **Redis 7** |
| Reverse proxy | Nginx (TLS 1.2+, security headers, IP-whitelist) |
| Deploy | **Docker + Docker Compose** |
| CI/CD | **GitHub Actions** |
| IdP | **Keycloak** (уже развёрнут) |
| Files | **Nextcloud** (уже развёрнут) |
| Office editor | **Collabora Online** (уже развёрнут, встроен в Nextcloud) |
| Email | Postfix (SMTP) |

---

## Архитектура (ключевые решения)

### Аутентификация
- Основной IdP — **Keycloak** (OIDC). AD напрямую не используется
- Все user-атрибуты берутся из **JWT claims** (`department`, `job_title`, `phone`, `groups`)
- Токены хранятся в **HTTPOnly + Secure + SameSite=Strict cookies** (не localStorage)
- Роли: `reader` (чтение), `editor` (CRUD контента), `admin` (всё)
- **Локальная аутентификация (Phase 2.1):** поля `auth_source` (`"keycloak"` | `"local"`) и `password_hash` (bcrypt, nullable) в таблице `users`; сессионный механизм Redis единый; `keycloak_id` nullable для локальных пользователей; bootstrap первого admin из env `ADMIN_EMAIL` + `ADMIN_PASSWORD`

### Nextcloud интеграция (Вариант B — impersonation)
- Файловые операции выполняются **от имени пользователя** через `Authorization: Bearer {user_access_token}`
- Nextcloud валидирует JWT через `user_oidc` app (версия ≥ 1.3)
- **Service account (`portal-svc`)** — только для Templates (v2) и webhooks, НЕ для пользовательских файлов
- **Скачивание:** `httpx.stream() → StreamingResponse` (не OCS share-ссылки)
- **Upload:** `frontend → backend → WebDAV PUT` — **streaming**, не буферизация всего файла в `bytes`:
  ```python
  async def upload_file_as(self, user_token, user_sub, target_path, stream: AsyncIterator[bytes]) -> None:
      async with httpx.AsyncClient(timeout=self.TIMEOUT_UPLOAD) as client:
          r = await client.put(webdav_url, headers={...}, content=stream)
  ```
- **httpx таймауты:** листинг=10s, download=None, upload=600s, health=3s
- JWT должен содержать `aud: nextcloud` (Audience mapper в Keycloak)
- **WebDAV path:** `/remote.php/dav/files/{NC_USER_ID_FIELD_VALUE}/` — значение берётся из `env NC_USER_ID_FIELD` (`preferred_username` или `sub`). **Статус: TBD — инженер ещё не провёл миграцию Nextcloud.**
- ❌ **Модуль файлов (§3.6) НЕ реализовывать** до получения значения `NC_USER_ID_FIELD` от инженера.

### Персональные настройки пользователя
- Хранятся в `users.preferences JSONB` (не отдельная таблица)
- Структура: `{"hidden_link_ids": ["uuid1", "uuid2"]}`
- Endpoint: `PATCH /api/v1/users/me/preferences`
- При добавлении новых типов настроек — расширять тот же JSONB

### База данных
- **Soft delete** везде: `deleted_at TIMESTAMPTZ` (NULL = активна)
- **Оптимистичная блокировка** для KB-статей: поле `version INTEGER`, при UPDATE `WHERE id=? AND version=?`, несовпадение → 409
- **ON DELETE RESTRICT** на `kb_sections.parent_id` (CASCADE опасен — сносит всё дерево)
- **FTS:** PostgreSQL с `hunspell_ru` (не Snowball), конфигурация `russian_hunspell` в `init.sql`
- **pg_trgm** — только для typeahead по заголовкам, не для основного поиска
- **Audit log** — партиционирована по месяцам (native PG16), async batch insert через ARQ
- **Аватары** — local volume `/data/avatars/`, в БД только `avatar_url`

### API
- Базовый URL: `/api/v1/`
- Пагинация **обязательна везде**: `limit=20` (default), `max=100`
- **Idempotency-Key** для whitelist: `POST /news`, `POST /kb/articles`, `POST /files/upload`, `POST /notifications/send`
  - Хранить только `{"id": "uuid"}` в БД, не полный body (memory leak)
  - Endpoint обязан выставлять `X-Resource-Id: {uuid}` в ответе
- `/health` — всегда 200; `/ready` — проверяет DB + Redis + Nextcloud, 200/503
- **Docker healthcheck использует `/ready`**, не `/health`

### Безопасность
- CSRF: `SameSite=Strict` + Origin/Referer check (не Double Submit Cookie)
- XSS: Markdown storage + `bleach` санитизация на бэкенде
- Rate limiting: `fastapi-limiter` (per-user, Redis)
- File upload: валидация MIME через python-magic

---

## Структура репозитория

```
portal/
├── AGENT.md                   ← этот файл
├── requirements.md            ← полное ТЗ v0.7
├── docs/
│   ├── adr.md                 ← Architecture Decision Records
│   ├── db-schema.md           ← схема БД (все таблицы + индексы)
│   ├── api-contracts.md       ← контракты API (request/response)
│   └── roles-matrix.md        ← матрица прав: роль × ресурс × действие
├── frontend/
│   ├── src/
│   │   ├── components/        ← переиспользуемые компоненты
│   │   ├── pages/             ← страницы (= Vue Router routes)
│   │   ├── stores/            ← Pinia stores
│   │   ├── composables/       ← useXxx composables
│   │   ├── api/               ← TanStack Query hooks + ofetch calls
│   │   ├── i18n/              ← ru.json, en.json
│   │   └── types/             ← TypeScript типы
│   ├── tests/
│   │   ├── unit/              ← Vitest unit tests
│   │   └── e2e/               ← Playwright E2E tests
│   ├── vite.config.ts
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── api/               ← FastAPI routers (один файл = один модуль)
│   │   ├── core/              ← config, security, logging, rate_limit, idempotency
│   │   ├── models/            ← SQLAlchemy models
│   │   ├── schemas/           ← Pydantic schemas (request/response)
│   │   ├── services/          ← бизнес-логика (nextcloud, keycloak, search...)
│   │   ├── worker/            ← ARQ tasks (audit, notifications, export, cleanup)
│   │   └── main.py            ← FastAPI app, middleware, startup
│   ├── migrations/
│   │   ├── init.sql           ← расширения + FTS + первые партиции audit_log
│   │   └── versions/          ← Alembic migrations
│   ├── tests/
│   │   ├── unit/              ← Pytest unit (без внешних зависимостей)
│   │   └── integration/       ← Pytest integration (Testcontainers)
│   ├── scripts/
│   │   └── create_audit_partitions.py
│   ├── pyproject.toml
│   └── Dockerfile
├── nginx/
│   ├── nginx.conf
│   └── certs/
├── docker-compose.yml
└── .github/
    └── workflows/
        ├── ci.yml             ← lint + test на каждый PR
        └── build.yml          ← сборка образов на merge в main
```

---

## Критические технические детали инфраструктуры

### PostgreSQL: hunspell_ru (обязательно для FTS)
Стандартный образ `postgres:16-alpine` **не включает** hunspell-словари. Требуется кастомный `Dockerfile` для postgres:
```dockerfile
# postgres/Dockerfile
FROM postgres:16-alpine
RUN apk add --no-cache postgresql16-contrib \
    && mkdir -p /usr/share/postgresql/16/tsearch_data
# Словари копируются из ./postgres/hunspell/ (russian.dict + russian.affix + russian.stop)
COPY hunspell/ /usr/share/postgresql/16/tsearch_data/
```
Без этого `init.sql` упадёт на `CREATE TEXT SEARCH DICTIONARY russian_hunspell_dict`.

### Backend: Playwright/Chromium для PDF-экспорта
`backend/Dockerfile` должен устанавливать Playwright и браузер (~300 МБ):
```dockerfile
# Добавить в backend/Dockerfile ПОСЛЕ установки Python-зависимостей:
RUN pip install playwright && playwright install --with-deps chromium
```
Playwright Chromium разделяется между PDF-экспортом и E2E-тестами — один образ.

⚠️ После установки браузер хранится в `/ms-playwright`. Обязательно `chown -R portal:portal /ms-playwright` перед `USER portal` — иначе под непривилегированным пользователем chromium не запустится.

### Backend: structlog factory
В `app/core/logging.py` использовать `structlog.stdlib.LoggerFactory()`. **НЕ использовать** `PrintLoggerFactory()` — он несовместим с процессором `add_logger_name` (нет атрибута `.name`) и падает на старте. Stdlib factory также корректно интегрируется с uvicorn-логами через `ProcessorFormatter`.

### Nginx: TLS-сертификаты
Контейнер `portal-nginx` не запускается без `nginx/certs/portal.crt` и `nginx/certs/portal.key`. Для dev — self-signed (см. [docs/phase-0.md](./docs/phase-0.md#вариант-2-full-stack-smoke-test)). Папка `nginx/certs/` в git — только `.gitkeep`, реальные ключи туда не коммитить.

### Nginx: CSP — только одной строкой
`add_header Content-Security-Policy "..." always;` пишется одной длинной строкой. Перенос `always;` на следующую строку → `[emerg] invalid number of arguments in "add_header" directive`.

### Naive UI: требует провайдеры в App.vue
`useMessage()`, `useDialog()`, `useNotification()` бросают ошибку `No outer <n-message-provider />` если провайдеры не обёрнуты вокруг `<router-view />` в `App.vue`. Все три провайдера **обязательны** независимо от того, используются они на текущей странице или нет. Порядок вложения: `NMessageProvider → NDialogProvider → NNotificationProvider → <router-view />`.

### Pydantic EmailStr: не работает с `.local`-доменами
`pydantic[email]` использует `email-validator`, который проверяет DNS-доставляемость домена. Домены `.local` (mDNS, корпоративные) не проходят DNS-проверку → 422 Unprocessable Content. **Решение:** использовать `email: str = Field(min_length=1, max_length=255)` для endpoint'ов, которые принимают корпоративные email (в частности `LocalLoginRequest`). `EmailStr` оставляется только там, где нужна строгая валидация публичных email.

### Переменные окружения (`.env`)
Полный список — `.env.example`. Ключевые:

| Переменная | Назначение | Пример / default |
|-----------|-----------|--------|
| `POSTGRES_PASSWORD` | пароль PostgreSQL | (нет default — обязательно) |
| `REDIS_PASSWORD` | пароль Redis | (нет default — обязательно) |
| `SECRET_KEY` | ≥32 символа, CSRF/sessions | (нет default — обязательно) |
| `DATABASE_URL` | asyncpg URL | `postgresql+asyncpg://portal:pwd@postgres:5432/portal` |
| `REDIS_URL` | Redis URL | `redis://:pwd@redis:6379/0` |
| `ENVIRONMENT` | `production`/`development` | `production` |
| `MAX_UPLOAD_SIZE_MB` | Лимит загружаемого файла | `100` |
| `ALLOWED_CIDR` | CIDR через запятую (для документации; nginx использует хардкод geo-блок) | `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` |
| `NC_USER_ID_FIELD` | Имя поля WebDAV-пути NC | `preferred_username` или `sub` — **TBD** |
| `NC_SERVICE_APP_PASSWORD` | App password для portal-svc | `xxxxxxxx` |
| `KEYCLOAK_URL` | Базовый URL Keycloak | `https://auth.company.local` |
| `KEYCLOAK_CLIENT_SECRET` | секрет OIDC-клиента | `change_me` |
| `NEXTCLOUD_URL` | Базовый URL Nextcloud | `https://nextcloud.company.local` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | Postfix relay | `postfix` / `25` / `portal@company.local` |
| `SENTRY_DSN` | Sentry DSN (пусто → выключено) | `` |
| `PROMETHEUS_METRICS_ENABLED` | вкл./выкл. `/metrics` | `true` |
| `DB_ECHO` | debug: лог всех SQL | `false` |
| `ARQ_MAX_JOBS` | concurrency воркера | `10` |
| `PORTAL_BASE_URL` | для генерации ссылок в email/share | `https://portal.company.local` |
| `TZ` | часовой пояс контейнеров | `Europe/Moscow` |

---

## Правила разработки

### Тесты (обязательно с каждым модулем)
- Unit-тесты пишутся **одновременно** с кодом модуля, не после
- Интеграционные тесты используют Testcontainers (PostgreSQL, Redis)
- E2E тесты: Playwright, покрытие ≥ 90% ключевых путей
- Тест НЕ принимается без покрытия happy path + основных error cases

### Миграции (zero-downtime)
```
Порядок: migration → code deploy → (если нужно) backfill → add constraint
```
- Новое поле → сначала `NULL`, потом `NOT NULL`
- Rename → добавить новое → писать в оба → читать новое → удалить старое
- Индексы: `CREATE INDEX CONCURRENTLY` (не блокирует)
- Запрещено: `ALTER TABLE ... ADD COLUMN ... NOT NULL` без DEFAULT на большой таблице

### API
- Каждый list endpoint возвращает `{ items, total, limit, offset }`
- Soft-deleted записи не возвращаются без `?include_deleted=true` (только admin)
- Все DELETE — soft (устанавливают `deleted_at`), кроме явного `?hard=true` (admin)
- Версии при коллизии: 409 с `current_version` и `your_version` в теле

### Nextcloud
- Никогда не проксировать файлы через service account в пользовательском контексте
- Всегда передавать `user_token` в файловых операциях
- Логировать в `audit_log` каждую файловую операцию

### i18n
- Все строки интерфейса — только через vue-i18n `t('key')`, без хардкода текста в компонентах
- При создании компонента — **сразу** добавлять ключи в оба файла: `ru.json` (мастер) и `en.json`
- Fallback: русский. При отсутствии ключа в `en.json` — показывается русский текст
- Ключи — hierarchical dot-notation: `kb.article.save`, `news.create.title`

### Безопасность
- Не логировать токены, пароли, персональные данные
- Проверять роли через `Depends(require_role("editor"))` перед каждой операцией
- Все входящие данные — через Pydantic модели

---

## Ключевые файлы для контекста

Перед реализацией любого модуля читай:
1. `requirements.md` — ТЗ v0.7 (полные детали)
2. `docs/db-schema.md` — схема БД (не изобретай таблицы заново)
3. `docs/api-contracts.md` — контракты (не меняй без обсуждения)
4. `docs/adr.md` — ADR (архитектурные решения и их обоснование)
5. `docs/roles-matrix.md` — матрица прав (не решай самостоятельно кто что видит)

---

## Текущий статус реализации

> Обновляй этот раздел после завершения каждого шага плана.

| Шаг | Статус | Что реализовано |
|-----|--------|-----------------|
| **Phase 0 — Инфраструктура** | ✅ Готово | Docker Compose, postgres+hunspell, backend skeleton, nginx, migrations, CI/CD. Smoke-test пройден: все 6 контейнеров healthy/up. Подробности и история фиксов: [docs/phase-0.md](./docs/phase-0.md) |
| **Phase 1 — Auth + Users + News** | ✅ Готово | Keycloak OIDC PKCE, Redis-сессии, upsert пользователей из JWT, новости CRUD + версии + FTS + ARQ cron, фронтенд auth/router/stores/pages, 29+ unit-тестов |
| **Phase 2 — Links + Bookmarks** | ✅ Готово | service_links CRUD + SSO-проброс, bookmarks CRUD + reorder, LinksPage, HomePage sidebar, Pinia store, 12 unit-тестов |
| **Phase 2.1 — Локальная аутентификация** | ✅ Готово | bootstrap admin из env, `/auth/local/login`, bcrypt, Redis-сессия, управление локальными пользователями, Naive UI провайдеры в App.vue. Подробности: Phase 2.1 ниже |
| **Phase 3 — KB + Search** | 🔜 | — |
| **Phase 4 — Notifications** | 🔜 | — |
| **Phase 5 — Nextcloud** | ⛔ Заблокирован | Ждём NC_USER_ID_FIELD от инженера |
| **Phase 6 — Audit + Analytics** | 🔜 | — |

### Phase 0 — что именно создано

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
- `src/i18n/ru.json` + `en.json` — полный набор ключей для всех модулей (auth, news, kb, search, users, links, bookmarks, notifications, admin)
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

### Phase 2.1 — что именно создано

**Backend (`backend/`):**
- `app/main.py` — функция `_bootstrap_admin()`: при старте создаёт первого admin из `ADMIN_EMAIL` + `ADMIN_PASSWORD` (env), если ещё нет ни одного admin в БД. Использует `AsyncSessionLocal` (не `async_session_factory`).
- `app/schemas/user.py` — класс `LocalLoginRequest`: поле `email: str` (не `EmailStr`) для поддержки `.local`-доменов (Pydantic `EmailStr` отклоняет non-deliverable домены через DNS)
- `app/api/auth.py` — endpoint `POST /api/v1/auth/local/login`: принимает `email` + `password`, проверяет bcrypt hash, создаёт Redis-сессию (единый механизм с Keycloak auth)
- `app/api/auth.py` — endpoint `PATCH /api/v1/users/me/password`: смена пароля для локальных пользователей
- `app/core/security.py` — функции `hash_password()` / `verify_password()` (bcrypt, cost≥12, SHA256 pre-hash)
- `scripts/create_admin.py` — CLI-скрипт для ручного создания admin-пользователя вне container startup
- Миграция `versions/004_local_auth.py` — добавлены поля `auth_source VARCHAR(20)` и `password_hash VARCHAR(255) NULL` в таблицу `users`

**Frontend (`frontend/`):**
- `src/App.vue` — добавлены провайдеры Naive UI: `NMessageProvider`, `NDialogProvider`, `NNotificationProvider` — обёрнуты вокруг `<router-view />`. Без них `useMessage()` / `useDialog()` в любых страницах бросали бы `EvalError`.
- `src/pages/LoginPage.vue` — форма локального входа: email + password, вызов `/api/v1/auth/local/login`
- `src/api/auth.ts` — функция `localLogin(email, password)`: `ofetch POST` с `body: { email, password }` (не FormData, не URLEncoded)

**Критические инфра-фиксы (применены в этой фазе):**
- **`AsyncSessionLocal`** — в `app/core/database.py` фабрика сессий называется `AsyncSessionLocal`, не `async_session_factory`. Импорт в `main.py` исправлен соответственно.
- **`EmailStr` → `str`** — `pydantic[email]` валидирует deliverability домена через DNS. Домен `.local` (mDNS/корпоративный) не проходит DNS-проверку → 422. Решение: `email: str = Field(min_length=1, max_length=255)` в `LocalLoginRequest`. Для `LocalUserCreateRequest` (создание через admin) `EmailStr` оставлен.
- **Naive UI провайдеры** — `useMessage()`, `useDialog()`, `useNotification()` требуют соответствующего провайдера выше по дереву компонентов. Все три добавлены в `App.vue`.
- **nginx DNS resolver** — `resolver 127.0.0.11 valid=10s ipv6=off;` добавлен для динамического резолвинга имён upstream-контейнеров внутри Docker-сети.
- **CSP `unsafe-eval`** — Naive UI использует `new Function()` для шаблонов. Добавлено `'unsafe-eval'` в `script-src` CSP-директиву nginx.

**.env:**
- `LOCAL_AUTH_ENABLED=true`
- `ADMIN_EMAIL=admin@company.local`
- `ADMIN_PASSWORD=change_me_admin_password` (⚠️ сменить после первого входа)

---

## Модули (порядок реализации, Step 4)

1. **Инфраструктура** — ✅ Done. Docker, postgres+hunspell, nginx, CI/CD, `.env`
2. **Аутентификация (Keycloak)** — ✅ Done. OIDC PKCE, middleware, роли, `/auth/*` endpoints
3. **Профили** — ✅ Done. `users` таблица, синхронизация из JWT, `/users/*`, аватары, preferences JSONB
4. **Новости** — ✅ Done. `news` таблица, черновики, таргетирование, FTS, архивация
5. **Ярлыки и закладки** — ✅ Done. `service_links`, `bookmarks`, персонализация через `preferences`
6. **Локальная аутентификация** — ✅ Done. `password_hash`, `auth_source`, `/auth/local/login`, bootstrap первого admin из env, управление локальными пользователями
7. **База знаний** — `kb_*` таблицы, TipTap dual-mode, версии, экспорт PDF/DOCX
8. **Поиск** — FTS + pg_trgm, typeahead, фильтры, `/search`
9. **Nextcloud интеграция** — ⛔ **ЗАМОРОЖЕН** до получения `NC_USER_ID_FIELD` от инженера
10. **Уведомления** — SSE + Redis Streams, email через Postfix
11. **Аналитика и аудит** — `audit_log`, партиции, ARQ batch insert, дашборд admin
12. **Observability** — structlog, Prometheus метрики, Sentry
13. ~~**Шаблоны документов**~~ — **v2, не реализуется**

---

## Чего НЕ делать

- ❌ Не обращаться к Active Directory напрямую (только через Keycloak JWT)
- ❌ Не хранить файлы локально (всё в Nextcloud)
- ❌ Не проксировать WebDAV через service account в пользовательском контексте
- ❌ Не хранить токены в localStorage (только HTTPOnly cookies)
- ❌ Не реализовывать модуль файлов (§3.6) до получения от инженера `NC_USER_ID_FIELD`
- ❌ Не делать CASCADE на `kb_sections.parent_id`
- ❌ Не хранить полный response body в `idempotency_keys` (только `{"id": "uuid"}`)
- ❌ Не использовать `slowapi` (синхронный Redis client)
- ❌ Не использовать WeasyPrint (400 МБ зависимостей)
- ❌ Не использовать Docker healthcheck на `/health` (использовать `/ready`)
- ❌ Не реализовывать шаблоны документов — **это v2**
- ❌ Не буферизовать файл в `bytes` при upload — только streaming (`AsyncIterator[bytes]`)
- ❌ Не использовать стандартный `postgres:16-alpine` без кастомного Dockerfile с hunspell
- ❌ Не создавать отдельную таблицу `user_preferences` — использовать `users.preferences JSONB`
- ❌ Не реализовывать BPM, чаты, социальные функции, геймификацию
