# AI Agent — System Prompt

Ты — AI-разработчик корпоративного интранет-портала.
Главное кредо - не нужно делать костыли, быстре и временные решения, нужно делать качественно и соотвествовать лучшим практикам разработки.
Всегда старайся писать тесты, проверять их работу, а потом после правок кода запускать их еще раз.

---

## Приоритет инструкций (от высшего к низшему)

1. **Этот файл (AGENTS.md)** — специфика проекта
2. Файлы в `docs/` (db-schema, api-contracts, adr, roles-matrix)
3. Базовый системный промпт агента (общие best practices)
4. Соглашения экосистемы (PEP8, Vue style guide) — если не противоречат пп. 1–2

---

## Среда выполнения

Агент работает в **Windows CMD** (не bash, не PowerShell). Docker запущен на Windows.
Критические ловушки cmd.exe: `&&` ломается с quoted paths, `;` игнорируется как разделитель, нет `bash -c`/`python -c` без явного экранирования. Используй `cd /d C:\path && cmd` без кавычек.

---

## Команды разработки

### Backend (`cd /d C:\Users\admin\Documents\zen\portal\backend`)
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

### Frontend (`cd /d C:\Users\admin\Documents\zen\portal\frontend`)
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
| PDF export | **Playwright/Chromium** в `screenshot-service` (HTTP-вызов, не в бэкенде) |
| DOCX export | **python-docx** + markdown→html конвертер |
| File validation | python-magic |
| Sanitization | **nh3** (backend), DOMPurify (frontend) |
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
- **Dual-auth:** `users.auth_source ∈ {"keycloak", "local"}`, `users.password_hash` (bcrypt, nullable), `users.keycloak_id` nullable для локальных. Bootstrap первого admin — из env `ADMIN_EMAIL` + `ADMIN_PASSWORD` (защищён `pg_advisory_xact_lock` от race при `--workers ≥ 2`). Account-linking: при первом Keycloak-логине пользователя с тем же email и `keycloak_id IS NULL` запись переводится в `auth_source = "keycloak"`, роль сохраняется; событие пишется в логи как `auth.account_linked` (warning)
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
- **Теги:** `photo_tags` — M2M (миграция 018)

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
- XSS: Markdown storage + `nh3` санитизация на бэкенде (`app/core/sanitize.py`); на фронте `v-html` обёрнут в `DOMPurify` (FORBID_TAGS/FORBID_ATTR)
- Rate limiting: `fastapi-limiter` (per-user, Redis). Identifier — `X-Real-IP` от nginx (`backend/app/core/limiter.py::real_ip_identifier`); прямой `X-Forwarded-For` не используется — обходится клиентом
- File upload: валидация MIME через python-magic
- CSP: без `unsafe-eval` (Naive UI работает без него)

---

## Структура репозитория

```
portal/
├── AGENTS.md                  ← этот файл
├── requirements.md            ← исходное ТЗ v1.0 (архив, все фазы завершены)
├── docs/
│   ├── adr.md                 ← Architecture Decision Records (ADR-001...ADR-034)
│   ├── db-schema.md           ← схема БД (все таблицы + индексы, миграции 001..024)
│   ├── api-contracts.md       ← контракты API (request/response)
│   ├── roles-matrix.md        ← матрица прав: роль × ресурс × действие
│   ├── testing.md             ← стратегия тестирования + покрытие по фазам
│   ├── deploy.md              ← production-чеклист, TLS, бэкапы, ротация секретов
│   └── integration-keycloak-nextcloud.md ← настройка Keycloak realm, NC service account
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── photos/        ← LightboxModal.vue, PhotoTrashView.vue, PhotoPermissionsModal.vue, FolderNode.vue
│   │   │   ├── editor/        ← TipTap-расширения, IframeEmbed.ts
│   │   │   ├── widgets/       ← виджеты HomePage
│   │   │   └── ...            ← GlobalSearch.vue, NewsCard.vue, RichEditor.vue, EmptyState.vue, ...
│   │   ├── pages/
│   │   │   ├── admin/
│   │   │   │   ├── tabs/      ← 11 lazy-loaded tab-компонентов: UsersTab, LinksTab, EmailTab, SystemTab, KeycloakTab, BrandingTab, ModulesTab, KbTab, AnalyticsTab, AuditTab, PhotosTab
│   │   │   │   └── admin-tabs.css
│   │   │   ├── photos/        ← PhotosIndexPage.vue, PublicPhotoPage.vue, PublicFolderPage.vue, MySharesPage.vue
│   │   │   └── ...            ← HomePage, NewsPage, KbPage, FilesPage, LoginPage, AdminPage, ProfilePage, ...
│   │   ├── stores/            ← Pinia stores: auth, branding, links, notifications, photos, modules, theme
│   │   ├── composables/       ← usePhotoUpload.ts (машина состояний загрузки фото), useRecentArticles.ts, useLayoutHeader.ts
│   │   ├── api/               ← типизированные API-клиенты; photos.ts и kb.ts генерированы из openapi.json
│   │   ├── i18n/              ← ru.json (мастер), en.json
│   │   ├── utils/             ← sanitize.ts (DOMPurify), markdown.ts (singleton), url.ts
│   │   └── types/             ← TypeScript типы, types.gen.d.ts (openapi-typescript, в .gitignore)
│   ├── tests/
│   │   ├── unit/              ← Vitest unit tests
│   │   └── e2e/               ← Playwright E2E tests (smoke, local-login, security-headers, photos)
│   ├── vite.config.ts
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── photos/        ← подпакет из 9 модулей: folders, photos, permissions, sharing, zip_jobs, import_scan, thumbnails, tags, _common
│   │   │   └── ...            ← auth, users, news, news_categories, kb, kb_extra, files, links, bookmarks, search, branding, system_settings, modules, analytics, audit, notifications, nc_federation, keycloak_admin, health, deps
│   │   ├── core/              ← config, security, logging, rate_limit, idempotency, system_config, constants, sanitize, sentry, metrics, text
│   │   ├── models/            ← SQLAlchemy models (users, news, kb_*, file_*, photo_*, notifications, audit_log, ...)
│   │   ├── schemas/           ← Pydantic schemas (request/response)
│   │   ├── services/
│   │   │   ├── nextcloud/     ← пакет: __init__.py, service.py, webdav.py, collabora.py
│   │   │   ├── files_acl.py          ← ACL-резолвер для файлового модуля (CTE, Redis-кэш TTL 5 мин); batch_resolve_folder_permissions() — N+1 устранён
│   │   │   ├── files_acl_persistence.py  ← персистентный кэш ACL (atomic write, asyncio.Lock)
│   │   │   ├── acl_base.py           ← общий код ACL: get_cached/set_cached/scan_and_delete/subject_ids_for_user
│   │   │   ├── photos_acl.py         ← ACL для фотогалереи (viewer/uploader/manager)
│   │   │   ├── photos_storage.py     ← Pillow + pillow-heif, WebP/AVIF thumbnails, EXIF strip GPS; atomic exclusive file naming (open xb)
│   │   │   ├── audit_partitions.py   ← ensure_partitions / drop_old_partitions (retention 12 мес)
│   │   │   └── ...                   ← keycloak, search, kb_acl, nc_federation, audit, notifications, session, news
│   │   ├── worker/            ← ARQ tasks: audit, notifications, export, cleanup, photos, files, metrics
│   │   └── main.py            ← FastAPI app, middleware, startup, lifespan
│   ├── migrations/
│   │   ├── init.sql           ← расширения + FTS (russian_hunspell) + первые партиции audit_log
│   │   └── versions/          ← Alembic migrations 001_users .. 030_email_unique_lower
│   ├── tests/
│   │   ├── unit/              ← Pytest unit (без внешних зависимостей, 290+ тестов)
│   │   ├── integration/       ← Pytest integration (Testcontainers: PostgreSQL, Redis)
│   │   └── security/          ← Security tests: headers, CSRF, XSS, auth_required, password_security
│   ├── scripts/
│   │   ├── create_audit_partitions.py
│   │   └── export_openapi.py  ← генерация openapi.json для frontend type generation
│   ├── pyproject.toml
│   └── Dockerfile
├── screenshot-service/        ← Playwright/Chromium PDF и скриншоты (отдельный контейнер)
│   ├── main.py                ← aiohttp: GET/POST /screenshot, POST /pdf
│   ├── requirements.txt
│   └── Dockerfile             ← python:3.12-slim + playwright install chromium
├── load/                      ← k6 load tests: smoke.js, baseline.js, search.js, portal-load.js (300 VU)
├── security/                  ← OWASP ZAP: zap-scan.sh, zap-baseline.conf
├── nginx/
│   ├── nginx.conf
│   └── certs/
├── postgres/                  ← кастомный Dockerfile с hunspell-ru словарями
├── system_data/               ← runtime-данные: nginx-конф, certs, secrets, settings (volume)
│   ├── nginx/                 ← reload trigger (inotify)
│   ├── nginx_conf/            ← динамически генерируемые nginx include-файлы (allowlist.conf, ssl_server.conf)
│   ├── certs/                 ← TLS-сертификаты (runtime, не в git)
│   ├── secrets/               ← секреты (runtime, не в git)
│   └── settings/              ← modules.json, system.json, email-settings.json
├── docker-compose.yml
├── docker-compose.staging.yml
├── docker-compose.dev.yml     ← генерируется on demand (не коммитится)
├── setup.sh                   ← первичная настройка (.env, папки, пароли)
├── openapi.json               ← OpenAPI 3.1 спецификация (генерируется из backend)
└── .github/
    └── workflows/
        ├── ci.yml             ← lint + test + alembic migrate на каждый PR
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

### Screenshot-service: Playwright/Chromium (PDF-экспорт и скриншоты)
Chromium **вынесен из бэкенда** в отдельный контейнер `screenshot-service` (`./screenshot-service/`).
Бэкенд делает HTTP-вызов к сервису — в его образе Playwright **не нужен**.

Сервис предоставляет два эндпоинта:
- `GET/POST /screenshot?url=...` — скриншот страницы (PNG)
- `POST /pdf` + `{"html": "..."}` — рендер HTML в PDF (A4)

```dockerfile
# screenshot-service/Dockerfile (ключевые шаги)
FROM python:3.12-slim
RUN pip install -r requirements.txt \
    && playwright install chromium \
    && playwright install-deps chromium
```

Бэкенд обращается к сервису через `SCREENSHOT_SERVICE_URL` (по умолчанию `http://screenshot-service:9000`).
Настройка в `app/core/config.py`:
```python
screenshot_service_url: str = Field(default="http://screenshot-service:9000")
```

⚠️ **Не устанавливать** Playwright в `backend/Dockerfile` — бэкенд не управляет браузером напрямую.

### Backend: structlog factory
В `app/core/logging.py` использовать `structlog.stdlib.LoggerFactory()`. **НЕ использовать** `PrintLoggerFactory()` — он несовместим с процессором `add_logger_name` (нет атрибута `.name`) и падает на старте. Stdlib factory также корректно интегрируется с uvicorn-логами через `ProcessorFormatter`.

### Nginx: TLS-сертификаты
Контейнер `portal-nginx` не запускается без `system_data/certs/portal.crt` и `system_data/certs/portal.key`. Для dev — self-signed (`openssl req -x509 ...`, см. [docs/deploy.md](./docs/deploy.md)). Реальные ключи в git не коммитить.

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
| `ALLOWED_CIDR` | CIDR через запятую | `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` |
| `ADMIN_EMAIL` | Email bootstrap-admin | `admin@company.local` |
| `ADMIN_PASSWORD` | Пароль bootstrap-admin | (обязательно, ≥12 символов) |
| `LOCAL_AUTH_ENABLED` | Включить локальную аутентификацию | `true` |
| `NC_SERVICE_APP_PASSWORD` | App Password portal-svc в Nextcloud | `change_me` |
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
| `SCREENSHOT_SERVICE_URL` | URL screenshot-service | `http://screenshot-service:9000` |
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
- ВСЕ KB endpoints должны вызывать `require_article_permission` или `require_section_permission` с указанием уровня (`viewer`/`editor`/`manager`)
- ВСЕ admin-mutating endpoints должны вызывать `push_audit_event(...)` после успешного commit

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
- JWT issuer обязательно валидируется в `parse_jwt_claims` (issuer=`{keycloak_url}/realms/{realm}`)
- Rate limit на `/auth/local/login`: по IP (5 req/15min) + по email-хешу (10 req/15min, двойной). Оба лимита — `fastapi-limiter` с `real_ip_identifier` / `email_identifier`
- Sentry `before_send` (`app/core/sentry.py::scrub_sensitive`) фильтрует Authorization/Cookie/passwords и sensitive query-string params (token, secret, key и т.д.)
- Email в БД хранится в исходном виде, но уникальность обеспечена по `LOWER(email)` (индекс `idx_users_email_ci`); все lookups в auth/users используют `func.lower()`
- `api/index.ts`: глобальный 401-обработчик защищён дебаунс-флагом (`_redirectingOnExpiry`); при истечении сессии генерируется событие `auth:expired` до редиректа, auth-store очищает `user`

---

## Ключевые файлы для контекста

Перед реализацией любого модуля читай:
1. `docs/db-schema.md` — схема БД (не изобретай таблицы заново)
2. `docs/api-contracts.md` — контракты (не меняй без обсуждения)
3. `docs/adr.md` — ADR (архитектурные решения и их обоснование)
4. `docs/roles-matrix.md` — матрица прав (не решай самостоятельно кто что видит)

---

## Текущий статус реализации

> Все фазы реализованы. Последнее обновление: май 2026.

| Модуль | Статус | Ключевые файлы |
|--------|--------|----------------|
| **Инфраструктура** | ✅ | `docker-compose.yml`, `nginx/`, `postgres/`, `.github/workflows/` |
| **Auth (Keycloak OIDC + локальный)** | ✅ | `api/auth.py`, `core/security.py`, `core/session.py` |
| **Пользователи + профили** | ✅ | `api/users.py`, `models/users`, `stores/auth.ts` |
| **Новости** | ✅ | `api/news.py`, `api/news_categories.py`, `pages/NewsListPage.vue` |
| **Ярлыки и закладки** | ✅ | `api/links.py`, `api/bookmarks.py`, `pages/LinksPage.vue` |
| **База знаний (KB)** | ✅ | `api/kb.py`, `api/kb_extra.py`, `services/kb_acl.py`, `pages/KbListPage.vue` |
| **Глобальный поиск** | ✅ | `api/search.py`, `components/GlobalSearch.vue` |
| **Файлы (Nextcloud)** | ✅ | `api/files.py`, `services/nextcloud/`, `services/files_acl.py`, `pages/FilesPage.vue` |
| **Уведомления (SSE + email)** | ✅ | `api/notifications.py`, `services/notifications.py`, `stores/notifications.ts` |
| **Аудит** | ✅ | `api/audit.py`, `services/audit.py`, `worker/` |
| **Аналитика** | ✅ | `api/analytics.py`, `pages/admin/tabs/AnalyticsTab.vue` |
| **Фотогалерея** | ✅ | `api/photos/` (9 модулей), `services/photos_acl.py`, `pages/photos/` |
| **Брендинг** | ✅ | `api/branding.py`, `stores/branding.ts` |
| **Системные настройки** | ✅ | `api/system_settings.py`, `pages/admin/tabs/SystemTab.vue` |
| **Управление модулями** | ✅ | `api/modules.py`, `pages/admin/tabs/ModulesTab.vue` |
| **Управление Keycloak** | ✅ | `api/keycloak_admin.py`, `pages/admin/tabs/KeycloakTab.vue` |
| **Screenshot-service** | ✅ | `screenshot-service/main.py` |
| **Видео (iframe embed)** | ✅ | `components/editor/IframeEmbed.ts` (PeerTube удалён) |

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
- ❌ Не интерполировать user-controlled данные в строку SQL — только bind-параметры
- ❌ Не хранить session_id в Redis без ротации при refresh — обновлять при каждом `/auth/refresh`
- ❌ Не использовать FQN для ARQ enqueue_job — только короткое имя функции
- ❌ Не вызывать сначала FS-операцию а потом db.commit() при rename папок — порядок: commit → FS, с компенсацией при сбое
- ❌ Не использовать Content-Type клиента для MIME-валидации загружаемых файлов — только python-magic / magic-bytes
- ❌ Не использовать LMPOP/RPOP для audit-events до записи в БД — только LMOVE в processing-list
- ❌ Не реализовывать BPM, чаты, социальные функции, геймификацию
- ❌ Не устанавливать Playwright в `backend/Dockerfile` — PDF/скриншоты только через `screenshot-service`
- ❌ Не использовать `PrintLoggerFactory()` в structlog — только `stdlib.LoggerFactory()`
