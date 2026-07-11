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

> ⚠️ Миграции применяются **автоматически** при старте контейнера backend через `backend/scripts/migrate.sh` (в контейнере — `/app/scripts/migrate.sh`). Вручную запускать `alembic upgrade head` не нужно.

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

## Работа между сессиями (handoff)

> У агента **нет памяти между сессиями**. Единственный носитель состояния — файлы:
> git-история, документация в `docs/` и план фичи. Всё, что не записано в файлы, теряется.

### Коммиты — только пользователь

- В конце задачи агент оставляет **чистое, проверенное состояние** (DoD пройден) и выдаёт пользователю **готовый текст коммит-сообщения**. Коммитит и пушит — только пользователь.
- Рекомендуемый формат сообщения (не жёсткое правило, но сильно повышает ценность git как памяти):
  `<type>(<module>): <что сделано>`, где `type ∈ {feat, fix, refactor, docs, test, chore}`.
  Плохо: `fix`, `ашч`. Хорошо: `feat(meetings): добавить лимит max_invitees в валидацию`.

### План фичи (для задач длиннее одной сессии)

- Хранится **в репозитории (под git)**: `docs/wip/<feature>.md`. Виден следующей сессии и переносится через GitHub.
- Удаляется при завершении фичи (после мёржа задачи), чтобы `docs/wip/` отражал только активную работу.
- Создаётся, как только ясно, что задача не закроется за одну сессию. Минимальная структура:
  ```markdown
  # Фича: <название>
  ## Цель
  <1–2 предложения: что и зачем>
  ## Решения по ходу
  - <дата>: выбрали X вместо Y, потому что Z
  ## Чеклист (DoD)
  - [ ] миграция / модель / схема
  - [ ] сервис (бизнес-логика)
  - [ ] API endpoint + регистрация
  - [ ] unit-тесты
  - [ ] frontend (api-клиент / query / компонент)
  - [ ] i18n (ru + en)
  - [ ] lint + typecheck + tests pass
  - [ ] обновлены docs/ (если менялись БД/API/права/архитектура)
  ## Грабли / контекст
  - <на что уже наступили, что важно помнить>
  ```
- В начале сессии агент **первым делом** читает план (если он есть) и `git log --oneline -15` + `git status`, чтобы восстановить контекст.

### Хэндофф — в конце каждой сессии (обязательно, без напоминания)

Агент завершает работу структурированным итогом и синхронизирует его с планом фичи:

```
СДЕЛАНО: <что готово и закоммичено пользователем / готово к коммиту, ссылки на файлы>
В РАБОТЕ: <что начато, но не закончено — конкретный файл:строка>
ДАЛЕЕ: <первый шаг следующей сессии>
ОТКРЫТЫЕ ВОПРОСЫ: <что требует решения пользователя>
КОММИТ: <готовый текст коммит-сообщения для пользователя>
```

---

## Проект

Корпоративный интранет-портал для ~300 сотрудников.
- Единая точка входа: новости, база знаний, файлы, ярлыки сервисов
- Только внутренняя сеть / VPN. Публичный доступ запрещён. Режим работы — через обратный прокси.
- Репозиторий: `/home/snow/portal/` (или `/workspace/portal/` в контейнере)

---

## Стек (зафиксирован, не менять без обсуждения)

**Frontend:** Vue 3 + TypeScript + Vite · **Naive UI** (не PrimeVue/Vuetify) · Pinia · Vue Router 4 · **TanStack Query + ofetch** · vue-i18n v9 · **TipTap v2** · контент — Markdown · DOMPurify · Vitest + Playwright

**Backend:** Python 3.12 · **FastAPI** · SQLAlchemy 2.x async + Alembic · **ARQ** (workers) · **fastapi-limiter** (не slowapi) · httpx · structlog · Sentry · python-magic · **nh3** · Pytest + Testcontainers

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
- **«Толстые» страницы/компоненты**: повторяющуюся логику и оркестрацию из крупных `.vue` (script setup > ~250 LOC) выноси в `pages/composables/use<Name>.ts` / `composables/use<Name>.ts`, представление — в dumb-под-компоненты; двусторонние поля — через `defineModel` (без `vue/no-mutating-props`). Страница остаётся тонким wiring-слоем.
- **Характеризующие тесты перед декомпозицией**: line-coverage обманчив (набирается mount/smoke при func-cov 0–11%). Перед любой разбивкой `.vue`-страницы сначала добавь тесты на функции/ветки/хендлеры (submit-пути, валидация, навигация, передача props в дочерние панели), затем рефактори при 1:1-контракте.

### Общее
- **Definition of Done**: код + тест (unit обязательно, integration если есть API/БД) + lint pass + typecheck pass + i18n проверен (frontend).
- **Перед коммитом**: `ruff check . && mypy app && pytest tests/unit` (backend); `npm run lint:check && npm run typecheck && npm run test:unit && npm run i18n:check` (frontend).
- **Миграции zero-downtime**: добавление колонок — `nullable=True` сначала, бэкфилл данных, затем `NOT NULL` отдельной миграцией.

---

## Архитектура (ключевые решения)

> Подробные обоснования — в `./docs/adr.md` (активные ADR) и `./docs/adr-archive.md`.

### Аутентификация
> Полный разбор: ADR-017 (dual-auth / Redis-сессия), ADR-035 (silent refresh), ADR-036 (auto-SSO).

- **Gotcha:** роль читается из **БД** (`users.role`) при каждом запросе — не из JWT.
- **Gotcha:** logout удаляет только Redis-сессию + cookie; SSO-сессию Keycloak не убивает.
- Dual-auth (`auth_source ∈ {keycloak, local}`), bootstrap-admin через `ADMIN_EMAIL`/`ADMIN_PASSWORD`, локальный вход — backdoor (`LOCAL_AUTH_ENABLED=false` → 403). Детали флоу — в ADR.

### Nextcloud / Файлы
> Полный разбор: ADR-032 (service account), `./docs/files.md`, `./docs/sharing.md`.

- WebDAV через service account **`portal-svc`** (App Password, не JWT). Права — в БД (`file_folder_permissions`), NC — тупое хранилище. Upload — streaming (см. «Чего НЕ делать»).
- Пофайловый шеринг: уровни только `viewer`/`editor` (`manager` не выдаётся), отзыв мягкий через `revoked_at`.

### Фотогалерея
> Полный разбор: ADR-030, ADR-031, `./docs/photos.md`.

- Локальное хранилище `/data/photos/` (не NC), миниатюры WebP/AVIF через Pillow, ACL `{viewer, uploader, manager}`, share-токены per-photo/per-folder.

### Email (outbox-pattern)
> Полный разбор: `./docs/email.md`.

- **Gotcha (поведенческое):** все исходящие письма пишутся в `email_outbox` **в той же транзакции**, что и бизнес-операция (`enqueue_outbox_email(...)`), — не вызывать SMTP напрямую. Отправляет cron `process_email_outbox` (claim `FOR UPDATE SKIP LOCKED`, backoff+DLQ). Producer’ы — meetings/news/kb/helpdesk.

### Справочники объектов
> Полный разбор: `./docs/directories.md`.

- Универсальный движок (Флот/Склады/…), встраивается вкладками в `/staff` (`?tab=<slug>`). Двухуровневый гейтинг: мастер `modules.json` (`directories.enabled`) → per-type `enabled`. Мутации — `editor`/`admin`.

### Техподдержка (Helpdesk)
> Полный разбор: `./docs/helpdesk.md`. Миграция `075`.

- Замена OTRS: заявки из веб-формы **или** email (IMAP-polling), статус-машина `new→open→pending→resolved→closed` (запрещённый переход → 409), двусторонний email-thread (`[#TKT-{number}]`, outbox `kind=helpdesk`).
- **Gotcha:** агенты — отдельная сущность `helpdesk_agents` (не роль `users.role`); права через `require_helpdesk_agent` (admin — суперсет).
- **Gotcha:** вложения локально `/data/helpdesk/TKT-{number}/` (не NC), download — `StreamingResponse` (не `FileResponse`/`X-Accel-Redirect`).
- Mailbox-settings singleton, пароль write-only (Fernet из `SECRET_KEY`). Гостевые заявители линкуются к аккаунту в OIDC-callback.

### Брендинг и системные настройки
- Runtime config: `/data/settings/system.json` (SMTP, Nextcloud, CIDR, nginx), `/data/secrets/keycloak-settings.json` (только Admin UI). Запись atomically через `os.replace()`.
- Модули (`/data/settings/modules.json`): `photos`, `nextcloud`, `meetings`, `directories`, `signature`, `helpdesk`; TTL 60s, `invalidate_modules_cache()`.
- Брендинг: `/data/branding/` (логотип, фавиконка, фон логина). Nginx reload: `trigger_nginx_reload()` → `/data/nginx/reload-trigger` → inotify.

### Admin UX (фронтенд)
> Детали — `./docs/README.md` (роутер «задача → что читать»).

- `AdminPage.vue`: 4 группы (`access`/`email`/`system`/`logs`), навигация через `?tab=<name>`. Контекстные настройки — drawer `?manage=<key>` (шестерёнка на странице модуля, admin-only), композабла `composables/useManageDrawer.ts`. `ModulesTab.vue` — только мастер-переключатели. Cmd+K palette знает про `manage=*`.

### База данных
> Полная схема: `./docs/db-schema.md` (куратируемая) + `./docs/db-schema.generated.md` (auto-gen).

- **Gotcha:** soft delete везде (кроме `users`) через `deleted_at`; FK → `ON DELETE SET NULL`.
- **Gotcha:** FTS — `hunspell_ru` (не Snowball); `pg_trgm` — только typeahead; `kb_sections.parent_id` — `ON DELETE RESTRICT`; KB-статьи — optimistic version → 409.

### API
> Полные контракты: `./docs/api-contracts.md` (куратируемая) + `./docs/api-contracts.generated.md` (auto-gen).

- **Gotcha:** Idempotency-Key для `POST /news`, `/kb/articles`, `/files/folders`, `/notifications/send` — хранить только `{"id": "uuid"}`, выставлять `X-Resource-Id`.

---

## Структура репозитория

```
portal/
├── AGENTS.md                  ← этот файл (операционный playbook)
├── docs/                      ← архитектурная документация (источник истины)
│   ├── README.md              ← полный индекс всех доков (включая модульные) + роутер «задача → что читать»
│   ├── adr.md / adr-archive.md          ← ADR (активные / архивные)
│   ├── db-schema.md / db-schema.generated.md    ← схема БД (curated / auto-gen)
│   ├── api-contracts.md / api-contracts.generated.md  ← API (curated / auto-gen)
│   ├── roles-matrix.md        ← матрица прав
│   ├── testing.md / deploy.md ← стратегия тестирования / production-чеклист
│   ├── wip/                   ← планы активных многосессионных фич (handoff)
│   └── integration-keycloak-nextcloud.md
├── frontend/src/
│   ├── components/            ← Vue-компоненты (admin/, files/, layout/, links/, photos/, editor/, widgets/, ...)
│   ├── pages/                 ← страницы (admin/tabs/ — tab-компоненты в 4 семантических группах; photos/, meetings/, ...)
│   ├── queries/               ← TanStack Query composables (keys.ts, admin/files/kb/news/...)
│   ├── stores/                ← Pinia stores (auth, branding, files, layout, modules, notifications, photos, theme)
│   ├── composables/           ← useFilesData, useFilesUpload, useFilesBulkOps, useFilesTree, useGlobalSearch, useManageDrawer, ...
│   ├── api/                   ← типизированные API-клиенты
│   ├── i18n/                  ← ru.json (мастер), en.json
│   └── api/types.gen.d.ts     ← auto-gen из openapi.json (в .gitignore)
├── backend/app/
│   ├── api/                   ← роутеры (files/, kb/, photos/ — подпакеты; auth, news, users, ...)
│   ├── core/                  ← config, database, security, limiter, logging, metrics, sentry, system_config, ...
│   ├── middleware/            ← csrf, idempotency, session, security_headers, ...
│   ├── models/                ← SQLAlchemy models (files, kb, links, news, notification, photos, user, ...)
│   ├── schemas/               ← Pydantic schemas
│   ├── services/              ← бизнес-логика (nextcloud/, files_acl, kb_acl, photos_acl, photos_storage, ...)
│   └── worker/                ← ARQ tasks (audit, notifications, news, photos, files, metrics)
├── backend/scripts/           ← export_openapi.py, generate_db_schema_doc.py, generate_api_contracts_doc.py, create_audit_partitions.py
├── backend/migrations/        ← init.sql (hunspell + FTS) + versions/ (001..063)
├── screenshot-service/        ← aiohttp + Playwright/Chromium (PDF/screenshot; отдельный контейнер)
├── nginx/                     ← Dockerfile, Dockerfile.config (sidecar), templates/, render-config.sh
├── postgres/                  ← Dockerfile с hunspell-ru словарями
├── system_data/               ← runtime-данные (volume): nginx/, nginx_conf/, certs/, secrets/, settings/
├── docker-compose.yml         ← все сервисы; docker-compose.dev.yml / docker-compose.staging.yml — overlay-конфиги
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
- **fastapi-limiter + starlette 1.x:** `app/core/limiter.py` содержит monkey-patch совместимости (ADR-043). **НЕ добавлять** `from __future__ import annotations` в этот файл — ломает FastAPI-интроспекцию `Request`/`Response` после патча → 422 на rate-limited endpoints.
- **Образ backend вкомпилирован** (target `production`): volume-mount только для `/data/*`. После правок backend-кода — `docker compose build backend`, иначе `restart` не подхватит изменения.
- **`portal_base_url`** в `system.json` обязан включать scheme (`https://...`) — иначе CSRF Origin-проверка ломается → 403 на local login. Валидатор `_schemas.py` добавляет scheme автоматически, но при ручном редактировании — указывать явно.

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
- ❌ Не хранить **пользовательские файлы** локально — всё в Nextcloud (исключения: фото `/data/photos/`, брендинг `/data/branding/`, вложения helpdesk `/data/helpdesk/`, обратная связь `/data/feedback/files/`)
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
