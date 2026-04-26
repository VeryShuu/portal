# AI Agent — System Prompt

Ты — AI-разработчик корпоративного интранет-портала.

---

## Приоритет инструкций (от высшего к низшему)

1. **Этот файл (AGENTS.md)** — специфика проекта
2. Файлы в `docs/` (db-schema, api-contracts, adr, roles-matrix)
3. Базовый системный промпт агента (общие best practices)
4. Соглашения экосистемы (PEP8, Vue style guide) — если не противоречат пп. 1–2

---

## Среда выполнения

Агент работает в **Windows CMD** (не bash, не PowerShell). Docker запущен на Windows.
Перед любым использованием Bash tool или Docker команд — прочитай `WINDOWS_CHEATSHEET.md`.
Там задокументированы **проверенные** команды и критические ловушки (сломанные кавычки, `&&` + quoted paths, `bash -c`, `python -c` и т.д.).

---

## Перед каждой задачей

1. Прочитай этот файл — он даёт общую картину
2. В зависимости от задачи читай:
   - Работа с БД → `docs/db-schema.md`
   - Новый/изменённый API → `docs/api-contracts.md`
   - Изменение прав доступа → `docs/roles-matrix.md`
   - Спорное архитектурное решение → `docs/adr.md`
   - Детали реализованных фаз → `docs/implementation-details.md`
3. Не меняй API-контракты без явного подтверждения

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
- Все user-атрибуты Keycloak-пользователей берутся из **JWT claims** (`department`, `job_title`, `phone`, `groups`) и сохраняются в `users` при upsert
- **Серверная сессия в Redis** (ключ — `session_id`, opaque UUID). В HTTPOnly + Secure + **SameSite=Lax** cookie `portal_session` хранится только идентификатор сессии. JWT в cookie **не кладётся**
  - SameSite=Lax (а не Strict) — иначе после редиректа Keycloak → `/auth/callback` cookie не отдаётся и сессия теряется. CSRF-защита обеспечивается Origin/Referer-check + SameSite=Lax (top-level GET-навигация безопасна)
- Роль читается из **БД** (`users.role`) при каждом запросе, не из JWT (см. `docs/roles-matrix.md`). Изменение роли через admin-API применяется немедленно
- **Dual-auth (Phase 2.1):** `users.auth_source ∈ {"keycloak", "local"}`, `users.password_hash` (bcrypt, nullable), `users.keycloak_id` nullable для локальных. Bootstrap первого admin — из env `ADMIN_EMAIL` + `ADMIN_PASSWORD` (защищён `pg_advisory_xact_lock` от race при `--workers ≥ 2`). Account-linking: при первом Keycloak-логине пользователя с тем же email и `keycloak_id IS NULL` запись переводится в `auth_source = "keycloak"`, роль сохраняется; событие пишется в логи как `auth.account_linked` (warning)
- **Аудит**: события `auth.login` / `auth.logout` с `metadata.source ∈ {"keycloak","local"}`. Отдельных типов `local_login` нет — только метаданные

### Nextcloud интеграция (Вариант A — service account)
- Все файловые операции выполняются через **единый service account `portal-svc`** — Nextcloud не знает, кто из пользователей делает запрос
- Права доступа к файлам управляются **исключительно на стороне портала** (БД таблица `file_folder_permissions`). Nextcloud — тупое хранилище
- **WebDAV path:** `/remote.php/dav/files/portal-svc/` — фиксирован, не зависит от пользователя
- **Аутентификация в NC:** `Authorization: Basic base64(portal-svc:NC_SERVICE_APP_PASSWORD)` (App Password, не JWT). Keycloak `user_oidc` app для файлового модуля не требуется
- **Скачивание:** `httpx.stream() → StreamingResponse` (не OCS share-ссылки)
- **Upload:** `frontend → backend → WebDAV PUT` — **streaming**, не буферизация всего файла в `bytes`:
  ```python
  async def upload_file(self, target_path, stream: AsyncIterator[bytes]) -> None:
      async with httpx.AsyncClient(timeout=self.TIMEOUT_UPLOAD) as client:
          r = await client.put(webdav_url, headers={"Authorization": f"Basic {self._basic_auth}"}, content=stream)
  ```
- **httpx таймауты:** листинг=10s, download=None, upload=600s, health=3s
- **Collabora (редактирование документов):**
  - Backend запрашивает у NC Collabora-URL для файла через OCS API (от portal-svc)
  - NC генерирует WOPI-сессию, возвращает URL + токен
  - Frontend открывает Collabora в `<iframe>` с этим URL
  - Параметр `display_name` передаётся в WOPI → в документе видно реальное имя пользователя портала
  - Collabora сохраняет изменения напрямую в NC через WOPI — портал не стоит в цепочке при редактировании
- **Collabora federation callback:** при открытии файла портал сохраняет `display_name` пользователя в Redis под случайным токеном. Nextcloud/Collabora вызывает `POST /ocs/v2.php/apps/richdocuments/api/v1/federation` — реализован в `api/nc_federation.py`, проксируется через nginx. Endpoint публичный (без auth/CSRF), защита — неугадываемый токен.
- **Audit:** каждая файловая операция пишется в `audit_log` с реальным `user_id` из сессии портала

### Фотогалерея (локальное хранилище)
- Файлы хранятся в **локальном volume** `/data/photos/{folder_path}/{filename}` — **НЕ в Nextcloud**
- AVIF-миниатюры генерируются при загрузке (3 размера: thumb/small/medium) через `Pillow`; strip GPS по настройке модуля
- **ACL:** permission ∈ `{viewer, uploader, manager}`, subject_type ∈ `{user, group}`. Проверяется в `app/services/photos_acl.py`. Папки наследуют права от родителя (`inherit_permissions`)
- **Share-токены:** приватный токен (`photo_share_tokens`) на отдельное фото, публичный токен (`photo_folder_share_tokens`) на всю папку — доступ без авторизации через `PublicFolderPage.vue` + `PublicPhotoPage.vue`
- **ZIP-выгрузка:** ARQ-задача (`photo_zip_jobs`), фронт поллит статус до готовности
- **Корзина:** soft delete (`deleted_at`), отдельный фильтр `?trash=true`
- **Теги:** `photo_tags` — M2M через JSONB или отдельная таблица (миграция 018)

### Брендинг и системные настройки
- **Брендинг** (`/data/branding/`): логотип, фавиконка, фон логина хранятся как файлы; `settings.json` содержит название/описание портала
- **Системные настройки** (`/data/settings/system.json`): SMTP, Keycloak URL, whitelist CIDR, nginx параметры. Запись → atomically через `os.replace()` + temp file
- **Nginx reload**: запись в `/data/nginx/reload-trigger` → inotify-скрипт снаружи перечитывает nginx конфиг (без рестарта контейнера)
- **Управление модулями** (`/data/settings/modules.json`): enable/disable `photos`, `nextcloud`; кэш в памяти (TTL 60s), инвалидация через `invalidate_modules_cache()`

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
- CSRF: `SameSite=Lax` + Origin/Referer check (Strict ломает OIDC redirect)
- XSS: Markdown storage + `bleach` санитизация на бэкенде; на фронте `v-html` обёрнут в `DOMPurify` (FORBID_TAGS/FORBID_ATTR)
- Rate limiting: `fastapi-limiter` (per-user, Redis). Identifier — `X-Real-IP` от nginx (`backend/app/core/limiter.py::real_ip_identifier`); прямой `X-Forwarded-For` не используется — обходится клиентом
- File upload: валидация MIME через python-magic
- CSP: без `unsafe-eval` (Naive UI работает без него)

---

## Структура репозитория

```
portal/
├── AGENT.md                   ← этот файл
├── requirements.md            ← полное ТЗ (v1.0)
├── docs/
│   ├── adr.md                 ← Architecture Decision Records (ADR-001 ... ADR-017)
│   ├── db-schema.md           ← схема БД (все таблицы + индексы)
│   ├── api-contracts.md       ← контракты API (request/response)
│   ├── roles-matrix.md        ← матрица прав: роль × ресурс × действие
│   └── testing.md             ← стратегия тестирования + покрытие по фазам
├── UI.md                      ← редизайн MAGE (Stage 1..8), design tokens
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
├── system_data/               ← runtime-данные: nginx-конф, certs, secrets, settings (volume)
│   ├── nginx/                 ← reload trigger (inotify)
│   ├── nginx_conf/            ← динамически генерируемые nginx include-файлы
│   ├── certs/                 ← TLS-сертификаты (runtime, не в git)
│   ├── secrets/               ← секреты (runtime, не в git)
│   └── settings/              ← modules.json, system.json
├── upload_data/               ← загружаемые файлы (volume)
├── base_data/                 ← базовые данные (branding, avatars, photos)
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
| `NC_SERVICE_APP_PASSWORD` | App Password пользователя `portal-svc` в Nextcloud | `xxxxxxxx` |
| `NC_SERVICE_USERNAME` | Имя service account в Nextcloud | `portal-svc` |
| `NC_FILES_ROOT` | Корневая папка файлового модуля внутри portal-svc | `PortalFiles` |
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
- Все файловые операции идут через service account `portal-svc` — никогда не использовать JWT пользователя для WebDAV
- Права проверять в **БД портала** до каждой операции, не в Nextcloud
- Логировать в `audit_log` каждую файловую операцию с реальным `user_id`
- Для Collabora: получать WOPI-URL через OCS API (portal-svc) → передавать `display_name` пользователя → открывать iframe

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
1. `requirements.md` — ТЗ v1.0 (полные детали)
2. `docs/db-schema.md` — схема БД (не изобретай таблицы заново)
3. `docs/api-contracts.md` — контракты (не меняй без обсуждения)
4. `docs/adr.md` — ADR (архитектурные решения и их обоснование)
5. `docs/roles-matrix.md` — матрица прав (не решай самостоятельно кто что видит)

---

## Текущий статус реализации

> Обновляй этот раздел после завершения каждого шага плана.
> Последнее обновление: апрель 2026 (Phase 5 — Nextcloud files; Phase 8.1 — удалён videos-виджет)

| Шаг | Статус | Что реализовано |
|-----|--------|-----------------|
| **Phase 0 — Инфраструктура** | ✅ Готово | Docker Compose, postgres+hunspell, backend skeleton, nginx, migrations, CI/CD. Smoke-test пройден: все 6 контейнеров healthy/up. Подробности и история фиксов: [docs/phase-0.md](./docs/phase-0.md) |
| **Phase 1 — Auth + Users + News** | ✅ Готово | Keycloak OIDC PKCE, Redis-сессии, upsert пользователей из JWT, новости CRUD + версии + FTS + ARQ cron, фронтенд auth/router/stores/pages, 29+ unit-тестов |
| **Phase 2 — Links + Bookmarks** | ✅ Готово | service_links CRUD + SSO-проброс, bookmarks CRUD + reorder, LinksPage, HomePage sidebar, Pinia store, 12 unit-тестов |
| **Phase 2.1 — Локальная аутентификация** | ✅ Готово | bootstrap admin из env, `/auth/local/login`, bcrypt, Redis-сессия, управление локальными пользователями, Naive UI провайдеры в App.vue. Подробности: [docs/implementation-details.md](./docs/implementation-details.md) |
| **Phase 3 — KB + Search** | ✅ Готово | `kb_*` таблицы (миграции 008-010), ACL по разделам/статьям, TipTap+Markdown, версии, комментарии, suggestions, feedback, экспорт PDF (Playwright)/DOCX (python-docx), глобальный поиск (FTS hunspell + pg_trgm fallback + typeahead), Ctrl+K palette, 37+ unit-тестов |
| **Phase 3.5 — KB Markdown + Obsidian-совместимость** | ✅ Готово | media-uploads, attachments, vault export/import (.zip), MD export, diff между версиями |
| **Phase 4 — Уведомления (Email + SSE)** | ✅ Готово | `notifications` таблица (миграция 012), SSE-стрим (`GET /notifications/stream`), список + отметка прочитанным, Redis Streams, `stores/notifications.ts`, SSE keepalive + connection limit per user |
| **Phase 5 — Nextcloud** | ✅ Готово | Service account (ADR-032). `file_folders` + `file_folder_permissions` (миграция 020), `services/nextcloud.py` (WebDAV + Collabora OCS), `services/files_acl.py`, `api/files.py` (13 endpoints), `/ready` NC check, фронтенд `FilesPage.vue` + `FileFolderNode.vue` + `api/files.ts`, 30+ unit-тестов |
| **Phase 6 — Audit + Analytics** | ✅ Готово | `audit_log` партиционирована по месяцам (миграция 013), ARQ batch flush каждые 2 сек, просмотр событий в AdminPage, `app/services/audit.py` + `audit_partitions.py` |
| **Phase 7 — Фотогалерея** | ✅ Готово | Локальное хранилище `/data/photos/`, папки с ACL (viewer/uploader/manager), AVIF-миниатюры (3 размера), share-токены (приватные + публичные папки), теги, ZIP-выгрузка, bulk-операции, корзина/восстановление, slideshow, DnD-загрузка, QR-код шаринга. Миграции 014-019. `app/api/photos.py` (77 KB), `app/services/photos_acl.py` + `photos_storage.py`, `pages/photos/` |
| **Phase 8 — Брендинг + Системные настройки** | ✅ Готово | `app/api/branding.py` — логотип, фавиконка, фон логина, название/описание портала. `app/api/system_settings.py` — управление nginx-конфигом, TLS-сертификатами, SMTP, Keycloak URL. `app/api/modules.py` — вкл/откл модулей (photos, nextcloud). `stores/branding.ts`. Хранение: `/data/branding/` + `/data/settings/` |
| **Phase 8.1 — Видео (iframe embed)** | ✅ Готово | PeerTube полностью удалён. Видео встраиваются как iframe через TipTap-расширение `IframeEmbed.ts` в KB-редакторе и новостях. Отдельного видео-виджета и backend `videos.py` нет |
| **Phase 8.2 — Управление Keycloak** | ✅ Готово | `app/api/keycloak_admin.py` — поиск/создание/блокировка/сброс пароля пользователей через Keycloak Admin API |

---

## Модули (порядок реализации, Step 4)

1. **Инфраструктура** — ✅ Done. Docker, postgres+hunspell, nginx, CI/CD, `.env`
2. **Аутентификация (Keycloak)** — ✅ Done. OIDC PKCE, middleware, роли, `/auth/*` endpoints
3. **Профили** — ✅ Done. `users` таблица, синхронизация из JWT, `/users/*`, аватары, preferences JSONB
4. **Новости** — ✅ Done. `news` таблица, черновики, таргетирование, FTS, архивация
5. **Ярлыки и закладки** — ✅ Done. `service_links`, `bookmarks`, персонализация через `preferences`
6. **Локальная аутентификация** — ✅ Done. `password_hash`, `auth_source`, `/auth/local/login`, bootstrap первого admin из env, управление локальными пользователями
7. **База знаний** — ✅ Done. `kb_*` таблицы, ACL, TipTap+Markdown, версии, комментарии, экспорт PDF/DOCX/MD, vault import/export
8. **Поиск** — ✅ Done. FTS (`russian_hunspell`) + pg_trgm fallback, typeahead, фильтры, `/search`, Ctrl+K palette
9. **Nextcloud интеграция** — ✅ Done. Service account `portal-svc`, WebDAV + Collabora OCS, ACL в БД портала, `api/files.py`, `FilesPage.vue`
10. **Уведомления** — ✅ Done. SSE-стрим, Redis Streams, in-app уведомления, отметка прочитанным
11. **Аналитика и аудит** — ✅ Done. `audit_log` партиции, ARQ batch flush, просмотр в AdminPage
12. **Observability** — ✅ Done. structlog (Phase 0), Prometheus (`prometheus-fastapi-instrumentator`), Sentry SDK
13. ~~**Шаблоны документов**~~ — **v2, не реализуется**
14. **Фотогалерея** — ✅ Done. Локальное хранилище `/data/photos/`, ACL-папки, AVIF-миниатюры, share-токены, теги, bulk-ops, ZIP, корзина, slideshow, QR-код
15. **Брендинг** — ✅ Done. Логотип, фавиконка, фон логина, название портала. `/data/branding/`
16. **Системные настройки** — ✅ Done. Nginx-конфиг, TLS-сертификаты, SMTP, Keycloak URL через `/admin/system-settings`
17. **Управление модулями** — ✅ Done. Вкл/откл photos + nextcloud через `/admin/modules`. JSON: `/data/settings/modules.json`
18. ~~**Видео-виджет (PeerTube)**~~ — **удалён**. Вместо него — iframe-embed через TipTap `IframeEmbed.ts`
19. **Управление Keycloak** — ✅ Done. Поиск/создание/блокировка/сброс пароля пользователей через Keycloak Admin API

---

## Чего НЕ делать

- ❌ Не обращаться к Active Directory напрямую (только через Keycloak JWT)
- ❌ Не хранить **пользовательские файлы** локально (всё в Nextcloud) — исключение: фотогалерея (`/data/photos/`) и брендинг (`/data/branding/`) хранятся локально намеренно
- ❌ Не использовать JWT пользователя для WebDAV-операций с Nextcloud — только `portal-svc` App Password
- ❌ Не хранить токены в localStorage (только HTTPOnly cookies)
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
