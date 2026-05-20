# AI Agent — System Prompt

Ты — AI-разработчик корпоративного интранет-портала с полным доступом к файлам проекта.

**Принципы работы:**
- Никаких костылей и временных решений — только качественный код по best practices.
- Пиши тесты, проверяй их до и после правок кода.
- При крупных изменениях — пересборка контейнеров без кэша (`docker compose build --no-cache <service>`).

---

## Приоритет инструкций (от высшего к низшему)

1. **Этот файл (AGENTS.md)** — специфика проекта
2. Файлы в `docs/` (db-schema, api-contracts, adr, roles-matrix)
3. Базовый системный промпт агента (общие best practices)
4. Соглашения экосистемы (PEP8, Vue style guide) — если не противоречат пп. 1–2

---

## Среда выполнения

Агент работает в **Linux / WSL2** (bash). Docker запущен через WSL2-backend.
Корень проекта на хосте: `/home/snow/portal/`.

---

## Доступные инструменты (MCP)

| Инструмент | Назначение | Когда использовать |
|---|---|---|
| **playwright** | Браузерная автоматизация | E2E-тестирование, проверка UI, скриншоты страниц портала |
| **sequential-thinking** | Структурированное пошаговое рассуждение | Сложные архитектурные решения, отладка трудновоспроизводимых багов |
| **zen-cli** | Запуск субагентов, генерация изображений | Параллельное выполнение задач, делегирование изолированных подзадач |
| **zencoder-rag-mcp** | Поиск по репозиториям и веб-поиск | Поиск паттернов в кодовой базе, поиск документации по библиотекам стека |
| **zencoder-server** | Диагностика VS Code, вопросы пользователю | Получение диагностики TypeScript/Python, уточнение требований |

---

## Команды разработки

### Backend (`cd /home/snow/portal/backend`)
| Назначение | Команда |
|---|---|
| Тесты (unit) | `pytest tests/unit` |
| Тесты (integration, нужен Docker) | `pytest tests/integration -m integration` |
| Тесты (security) | `pytest tests/security -m security` |
| Все тесты | `pytest` |
| Тесты с покрытием | `pytest --cov=app --cov-report=term-missing` |
| Lint (проверка) | `ruff check .` |
| Lint (автофикс) | `ruff check . --fix` |
| Typecheck | `mypy app` |
| Форматирование | `ruff format .` |

### Frontend (`cd /home/snow/portal/frontend`)
| Назначение | Команда |
|---|---|
| Тесты unit (однократно) | `npm run test:unit` |
| Тесты unit (watch-режим) | `npm run test:unit:watch` |
| Тесты unit с покрытием | `npm run test:coverage` |
| E2E тесты (Playwright) | `npm run test:e2e` |
| Lint (автофикс) | `npm run lint` |
| Lint (только проверка) | `npm run lint:check` |
| Typecheck | `npm run typecheck` |
| Проверка i18n-ключей | `npm run i18n:check` |
| Сборка prod | `npm run build` |
| Генерация типов из OpenAPI | `npm run gen:types` |

### Docker / инфраструктура (из корня проекта)
| Назначение | Команда |
|---|---|
| Поднять всё (prod-like) | `docker compose up -d` |
| Поднять dev | `docker compose -f docker-compose.dev.yml up -d` |
| Посмотреть логи backend | `docker compose logs -f backend` |
| Создать новую миграцию | `docker compose exec backend alembic revision --autogenerate -m "description"` |

> ⚠️ Миграции применяются **автоматически** при старте контейнера backend через `scripts/migrate.sh`. Вручную запускать `alembic upgrade head` не нужно.

---

## Перед каждой задачей

1. Прочитай этот файл — он даёт общую картину
2. В зависимости от задачи читай:
   - Работа с БД → `docs/db-schema.md`
   - Новый/изменённый API → `docs/api-contracts.md`
   - Изменение прав доступа → `docs/roles-matrix.md`
   - Спорное архитектурное решение → `docs/adr.md`
3. Не меняй API-контракты без явного подтверждения

---

## Проект

Корпоративный интранет-портал для ~300 сотрудников.
- Единая точка входа: новости, база знаний, файлы, ярлыки сервисов
- Только внутренняя сеть / VPN. Публичный доступ запрещён. Режим работы — через обратный прокси.
- Репозиторий: `/home/snow/portal/` (или `/workspace/portal/` в контейнере)

---

## Стек (зафиксирован, не менять без обсуждения)

**Frontend:** Vue 3 + TypeScript + Vite · **Naive UI** (не PrimeVue/Vuetify) · Pinia · Vue Router 4 · **TanStack Query + ofetch** · vue-i18n v9 · **TipTap v2** · контент — Markdown · Vitest + Playwright

**Backend:** Python 3.12 · **FastAPI** · SQLAlchemy 2.x async + Alembic · **ARQ** (workers) · **fastapi-limiter** (не slowapi) · httpx · structlog · Sentry · python-magic · **nh3** + DOMPurify · Pytest + Testcontainers

**Infra:** PostgreSQL 16 · Redis 7 · Nginx · Docker Compose · GitHub Actions · **Keycloak** (IdP) · **Nextcloud** (files) · **Collabora Online** (editor) · Postfix (SMTP)

---

## Coding Conventions

### Backend (Python)
- **Naming**: `snake_case` для функций/переменных, `PascalCase` для классов, `UPPER_SNAKE` для констант.
- **Новый API endpoint**: router в `app/api/<module>.py` (или подпакет `app/api/<module>/`); регистрация в `app/api/__init__.py`; Pydantic-схемы в `app/schemas/<module>.py`; зависимости (auth, role-check) — из `app/api/deps.py`.
- **Новая таблица**: SQLAlchemy-модель в `app/models/<module>.py`; Alembic-миграция через `docker compose exec backend alembic revision --autogenerate -m "..."`; обязательно `created_at`/`updated_at`/`deleted_at` (если soft-delete).
- **Бизнес-логика** — в `app/services/`, не в API-роутах.
- **Async везде**: SQLAlchemy async session, httpx.AsyncClient, ARQ для фоновых задач.

### Frontend (Vue 3 + TS)
- **Naming**: `camelCase` для переменных/функций, `PascalCase` для компонентов и типов.
- **Новый компонент**: `components/<domain>/<Name>.vue` (Composition API + `<script setup lang="ts">`).
- **Новый composable**: `composables/use<Name>.ts`, возвращает reactive state + actions.
- **Новый API-клиент**: `api/<module>.ts` (типизированный через `types.gen.d.ts`).
- **Новый query**: `queries/<module>.ts` (TanStack Query composable, ключ из `queries/keys.ts`).
- **Новый store**: `stores/<name>.ts` (Pinia setup-style).
- **i18n**: все user-facing строки через `t('key')`. Мастер — `i18n/ru.json`, ключи синхронно добавлять в `en.json`. Проверка — `npm run i18n:check`.
- **Стили**: scoped CSS в компоненте, без global utility-classes.

### Общее
- **Definition of Done**: код + тест (unit обязательно, integration если есть API/БД) + lint pass + typecheck pass + i18n проверен (frontend).
- **Перед коммитом**: `ruff check . && mypy app && pytest tests/unit` (backend); `npm run lint:check && npm run typecheck && npm run test:unit && npm run i18n:check` (frontend).
- **Миграции zero-downtime**: добавление колонок — `nullable=True` сначала, бэкфилл данных, затем `NOT NULL` отдельной миграцией.

---

## Архитектура (ключевые решения)

> Подробные обоснования — в `./docs/adr.md` (активные ADR) и `./docs/adr-archive.md`.

### Аутентификация
> Полный разбор: ADR-017 (dual-auth / Redis-сессия), ADR-035 (silent refresh), ADR-036 (auto-SSO).

- IdP — **Keycloak** (OIDC). Серверная сессия в Redis, cookie `portal_session` (HTTPOnly + SameSite=Lax). JWT в cookie не кладётся.
- Роль читается из **БД** (`users.role`) при каждом запросе — не из JWT.
- **Dual-auth:** `auth_source ∈ {"keycloak", "local"}`. Bootstrap-admin через `ADMIN_EMAIL` + `ADMIN_PASSWORD`.
- **Auto-SSO:** гость без сессии → redirect на `/api/v1/auth/login`. Loop-protection: `sso_attempts` в sessionStorage (≥2 за 30s → `/auth/error?reason=loop_detected`).
- **Локальный вход:** `/auth/local` (backdoor, без публичной ссылки). `LOCAL_AUTH_ENABLED=false` → 403.
- **Logout** удаляет только Redis-сессию + cookie; SSO-сессию Keycloak не убивает.

### Nextcloud интеграция (Вариант A — service account)
> Полный разбор: ADR-032.

- Все WebDAV-операции — через единый service account **`portal-svc`** (`Basic` App Password, не JWT).
- Права — исключительно в БД портала (`file_folder_permissions`). Nextcloud — тупое хранилище.
- WebDAV path: `/remote.php/dav/files/portal-svc/` — фиксирован.
- Upload — **streaming** (`AsyncIterator[bytes] → WebDAV PUT`), не буферизация. httpx timeouts: листинг=15s, download=None, upload=600s, health=3s.
- Collabora: backend → OCS API (portal-svc) → WOPI URL+token → frontend iframe. Сохранение через WOPI напрямую в NC.
- Audit: каждая операция → `audit_log` с реальным `user_id`.

### Фотогалерея (локальное хранилище)
> Полный разбор: ADR-030, ADR-031.

- Хранится локально в `/data/photos/` — **НЕ в Nextcloud**. AVIF-миниатюры (3 размера) через Pillow.
- ACL: `{viewer, uploader, manager}` — `app/services/photos_acl.py`. Share-токены: per-photo + per-folder (без авторизации).
- ZIP: ARQ-задача (`photo_zip_jobs`). Корзина: soft delete. Теги: M2M.

### Email (общая инфраструктура)
> Полный разбор: `./docs/email.md`.

- Все исходящие письма пишутся в таблицу **`email_outbox`** (миграция `051`,
  модель `app/models/email_outbox.py`). Caller заполняет строку в той же
  транзакции, что и бизнес-операция (outbox-pattern) — потеря писем при
  падении Redis/воркера невозможна.
- Отправляет cron-задача **`process_email_outbox`** (каждые 10 с): claim
  через `FOR UPDATE SKIP LOCKED`, MIME-сборка (для `kind=meeting` — inline
  iCal), `aiosmtplib.send`.
- Ошибки классифицируются (`app/worker/tasks/email_utils.py::classify_smtp_error`):
  `transient/permanent/unknown` → экспоненциальный backoff с jitter (cap 30 мин)
  или сразу DLQ. `OUTBOX_MAX_ATTEMPTS=6`.
- Producer’ы: meetings (`services/meetings/notifications.py`), news/kb
  (`worker/tasks/notifications.py`). Все вызывают
  `enqueue_outbox_email(...)` из `app/services/email_outbox.py`.
- Админ-UI: вкладка «Очередь Email» (`frontend/src/pages/admin/tabs/EmailOutboxTab.vue`,
  API `/api/v1/admin/email-outbox/*`) — список, фильтры, ручной retry/cancel,
  явный DLQ-алёрт.
- SMTP-настройки — `/data/branding/email-settings.json` (Admin UI → «Email»).

### Брендинг и системные настройки
- Runtime config: `/data/settings/system.json` (SMTP, Nextcloud, CIDR, nginx); `/data/secrets/keycloak-settings.json` (Keycloak — только Admin UI). Запись atomically через `os.replace()`.
- Nginx reload: `trigger_nginx_reload()` → `/data/nginx/reload-trigger` → inotify в `portal-nginx`. Sidecar `nginx-config` рендерит includes из `nginx/templates/`.
- Модули (`/data/settings/modules.json`): `photos`, `nextcloud`, `meetings`; TTL 60s, `invalidate_modules_cache()`. У `meetings` параметры: `enabled`, `calendar_start_hour`, `calendar_end_hour`, `max_recurrence_horizon_days` (default 31), `min_search_chars` (default 3), `max_invitees` (default 100).
- Брендинг: `/data/branding/` (логотип, фавиконка, фон логина).

### Admin UX (фронтенд)
- `AdminPage.vue` разбит на 4 семантические группы (`access`, `email`, `system`, `logs`) с подвкладками — навигация делается через `?tab=<name>` (legacy `/settings?tab=X` редиректится автоматически).
- Отдельная страница `SettingsPage` удалена. «Корзина» как пункт меню больше нет: trash-режим включается inline на `NewsListPage` и `PhotosIndexPage` (роуты `/trash` и `/settings` сохранены как soft-redirect для старых ссылок).
- Контекстные настройки доступны на самих страницах через шестерёнку (admin-only). Состояние drawer’а синхронизировано с URL (`?manage=<key>`) через композаблу `composables/useManageDrawer.ts`. Реализованные точки: `NewsListPage` (categories), `WorldClockWidget` (cities), `LinksAndBookmarksPage` (services), `FilesSidebar` (sync + file-icons), `KbListPage` (vault import/export), `PhotosIndexPage` (`manage=module` → `components/admin/PhotosModuleSettings.vue`), `MeetingsPage` (`manage=module` → `components/admin/MeetingsModuleSettings.vue`).
- В `ModulesTab.vue` остаются только мастер-переключатели (`enabled`) + Nextcloud + Video URL; детальные настройки модулей живут в `components/admin/*ModuleSettings.vue` и открываются drawer’ом со страницы модуля.
- Cmd+K command palette (`composables/useGlobalSearchCommands.ts`) знает про все `manage=*` команды (admin-only).

### База данных
> Полная схема: `./docs/db-schema.md` (куратируемая) + `./docs/db-schema.generated.md` (auto-gen).

- **Soft delete** везде (кроме `users`): `deleted_at TIMESTAMPTZ`. Users — hard-delete; FK → `ON DELETE SET NULL`.
- **Оптимистичная блокировка** KB-статей: `version INTEGER`, несовпадение → 409.
- **ON DELETE RESTRICT** на `kb_sections.parent_id` (CASCADE опасен).
- **FTS:** `hunspell_ru` (не Snowball). **pg_trgm** — только typeahead по заголовкам. Audit log — партиционирован по месяцам.

### API
> Полные контракты: `./docs/api-contracts.md` (куратируемая) + `./docs/api-contracts.generated.md` (auto-gen).

- **Idempotency-Key** для: `POST /news`, `POST /kb/articles`, `POST /files/upload`, `POST /notifications/send`. Хранить только `{"id": "uuid"}`, выставлять `X-Resource-Id`.

---

## Структура репозитория

```
portal/
├── AGENTS.md                  ← этот файл (операционный playbook)
├── docs/                      ← архитектурная документация (источник истины)
│   ├── adr.md / adr-archive.md          ← ADR (активные / архивные)
│   ├── db-schema.md / db-schema.generated.md    ← схема БД (curated / auto-gen)
│   ├── api-contracts.md / api-contracts.generated.md  ← API (curated / auto-gen)
│   ├── roles-matrix.md        ← матрица прав
│   ├── testing.md / deploy.md ← стратегия тестирования / production-чеклист
│   └── integration-keycloak-nextcloud.md
├── frontend/src/
│   ├── components/            ← Vue-компоненты (admin/, files/, layout/, links/, photos/, editor/, widgets/, ...)
│   ├── pages/                 ← страницы (admin/tabs/ — tab-компоненты в 4 семантических группах; photos/, meetings/, ...)
│   ├── queries/               ← TanStack Query composables (keys.ts, admin/files/kb/news/...)
│   ├── stores/                ← Pinia stores (auth, branding, files, layout, modules, notifications, photos, theme)
│   ├── composables/           ← useFilesData, useFilesUpload, useFilesBulkOps, useFilesTree, useGlobalSearch, useManageDrawer, ...
│   ├── api/                   ← типизированные API-клиенты
│   ├── i18n/                  ← ru.json (мастер), en.json
│   └── types/types.gen.d.ts   ← auto-gen из openapi.json (в .gitignore)
├── backend/app/
│   ├── api/                   ← роутеры (files/, kb/, photos/ — подпакеты; auth, news, users, ...)
│   ├── core/                  ← config, database, security, limiter, logging, metrics, sentry, system_config, ...
│   ├── middleware/            ← csrf, idempotency, session, security_headers, ...
│   ├── models/                ← SQLAlchemy models (files, kb, links, news, notification, photos, user, ...)
│   ├── schemas/               ← Pydantic schemas
│   ├── services/              ← бизнес-логика (nextcloud/, files_acl, kb_acl, photos_acl, photos_storage, ...)
│   └── worker/                ← ARQ tasks (audit, notifications, news, photos, files, metrics)
├── backend/scripts/           ← export_openapi.py, generate_db_schema_doc.py, generate_api_contracts_doc.py, create_audit_partitions.py
├── backend/migrations/        ← init.sql (hunspell + FTS) + versions/ (001..044)
├── screenshot-service/        ← aiohttp + Playwright/Chromium (PDF/screenshot; отдельный контейнер)
├── nginx/                     ← Dockerfile, Dockerfile.config (sidecar), templates/, render-config.sh
├── postgres/                  ← Dockerfile с hunspell-ru словарями
├── system_data/               ← runtime-данные (volume): nginx/, nginx_conf/, certs/, secrets/, settings/
├── docker-compose.yml         ← все сервисы; docker-compose.dev.yml генерируется on demand
├── setup.sh                   ← первичная настройка
└── openapi.json               ← OpenAPI 3.1 (генерируется: cd backend && python -m scripts.export_openapi)
```

---

## Критические технические детали

### PostgreSQL: hunspell_ru (обязательно для FTS)
`postgres/Dockerfile` устанавливает `hunspell-ru` и копирует словари в `${PGSHARE}/tsearch_data/`. Без этого `init.sql` упадёт на `CREATE TEXT SEARCH DICTIONARY russian_hunspell_dict`. Не заменять на стандартный `postgres:16`.

### Screenshot-service
Chromium вынесен из бэкенда в `screenshot-service/` (aiohttp + Playwright). Бэкенд обращается по `http://screenshot-service:9000`. Endpoints: `GET/POST /screenshot?url=...` (PNG), `POST /pdf` (HTML→PDF A4). **Не устанавливать Playwright в `backend/Dockerfile`.**

### Backend: gotchas
- **structlog:** использовать `stdlib.LoggerFactory()`, не `PrintLoggerFactory()` (несовместим с `add_logger_name`, падает на старте).
- **Nginx CSP:** `add_header Content-Security-Policy "..." always;` — одной строкой; перенос `always;` → `[emerg]`.
- **Naive UI:** три провайдера обязательны в `App.vue`: `NMessageProvider → NDialogProvider → NNotificationProvider → <router-view />`.
- **Pydantic EmailStr:** не работает с `.local`-доменами (DNS-проверка). Для корпоративного email использовать `email: str = Field(min_length=1, max_length=255)`.
- **TLS:** `portal-nginx` не стартует без `system_data/certs/portal.crt` + `portal.key`. Dev — self-signed (см. `docs/deploy.md`).

### Конфигурация: bootstrap (env) vs runtime (JSON) — ADR-037
- **Bootstrap** (`app/core/config.py::Settings`): `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `ADMIN_EMAIL/PASSWORD`, `LOCAL_AUTH_ENABLED`, `SCREENSHOT_SERVICE_SECRET`, DB pool tunables. Полный список — `.env.example`.
- **Runtime** (`/data/settings/system.json`, `SystemSettings`): управляется через Admin UI без рестарта — upload limits, `allowed_cidr`, `log_level`, `sentry_dsn`, `nextcloud_url`, `nc_service_app_password`, и др.
- **Keycloak** (`/data/secrets/keycloak-settings.json`): только Admin UI → «Keycloak». Никакого env-fallback.
- При первом старте `migrate_env_to_system_settings()` создаёт `system.json` из легаси env-переменных автоматически.

---

## Правила разработки

### Тесты (обязательно с каждым модулем)
- Unit-тесты пишутся **одновременно** с кодом модуля, не после
- Интеграционные тесты используют Testcontainers (PostgreSQL, Redis)
- E2E тесты: Playwright, покрытие ≥ 90% ключевых путей
- Тест НЕ принимается без покрытия happy path + основных error cases

### Миграции (zero-downtime)
- Порядок: migration → deploy → backfill → constraint. Новое поле — сначала `NULL`, потом `NOT NULL`.
- Rename: добавить новое → писать в оба → читать новое → удалить старое.
- Индексы: `CREATE INDEX CONCURRENTLY`. Запрещено: `ADD COLUMN NOT NULL` без DEFAULT на большой таблице.

### API
- Каждый list endpoint возвращает `{ items, total, limit, offset }`
- Soft-deleted записи не возвращаются без `?include_deleted=true` (только admin)
- Все DELETE — soft (устанавливают `deleted_at`), кроме явного `?hard=true` (admin)
- Версии при коллизии: 409 с `current_version` и `your_version` в теле
- ВСЕ KB endpoints должны вызывать `require_article_permission` или `require_section_permission` с указанием уровня (`viewer`/`editor`/`manager`)
- ВСЕ admin-mutating endpoints должны вызывать `push_audit_event(...)` после успешного commit

### i18n
- Все строки — через `t('key')`. Ключи добавлять сразу в оба файла (`ru.json` мастер + `en.json`). Fallback: русский.
- Ключи: dot-notation (`kb.article.save`). Проверка: `npm run i18n:check`.

### Безопасность
- Не логировать токены, пароли, персональные данные (Sentry `scrub_sensitive` в `app/core/sentry.py`)
- Роли — `Depends(require_role("editor"))`, данные — Pydantic, SQL — bind-параметры
- JWT issuer валидируется в `parse_jwt_claims` (issuer=`{keycloak_url}/realms/{realm}`)
- Rate limit `/auth/local/login`: IP (5/15min) + email-хеш (10/15min) через `fastapi-limiter`
- Email уникальность по `LOWER(email)` (индекс `idx_users_email_ci_active`); lookups — `func.lower()`

---

## Ключевые файлы для контекста

Перед реализацией любого модуля читай:
1. `docs/db-schema.md` — схема БД (не изобретай таблицы заново)
2. `docs/api-contracts.md` — контракты (не меняй без обсуждения)
3. `docs/adr.md` — ADR (архитектурные решения и их обоснование)
4. `docs/roles-matrix.md` — матрица прав (не решай самостоятельно кто что видит)

---

## Чего НЕ делать

- ❌ Не обращаться к Active Directory напрямую (только через Keycloak JWT)
- ❌ Не хранить **пользовательские файлы** локально — всё в Nextcloud (исключения: фото `/data/photos/`, брендинг `/data/branding/`)
- ❌ Не использовать JWT пользователя для WebDAV — только `portal-svc` App Password
- ❌ Не хранить токены в localStorage (только HTTPOnly cookies)
- ❌ Не делать CASCADE на `kb_sections.parent_id`
- ❌ Не хранить полный response body в `idempotency_keys` (только `{"id": "uuid"}`)
- ❌ Не использовать `slowapi` (не async), `WeasyPrint` (400 МБ), `postgres:16` без hunspell Dockerfile
- ❌ Не использовать Docker healthcheck на `/health` (использовать `/ready`)
- ❌ Не буферизовать файл в `bytes` при upload — только streaming (`AsyncIterator[bytes]`)
- ❌ Не создавать таблицу `user_preferences` — использовать `users.preferences JSONB`
- ❌ Не интерполировать user-controlled данные в SQL — bind-параметры
- ❌ Не ротировать session_id при каждом `/auth/refresh` забыть — обновлять
- ❌ Не использовать FQN для ARQ `enqueue_job` — только короткое имя функции
- ❌ Не вызывать FS-операцию до `db.commit()` при rename папок — commit → FS + компенсация
- ❌ Не использовать Content-Type клиента для MIME-валидации — только python-magic
- ❌ Не использовать LMPOP/RPOP для audit-events — только LMOVE в processing-list
- ❌ Не реализовывать BPM, чаты, социальные функции, геймификацию
