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
| Auth | **PyJWT[crypto]**, httpx (OIDC/Keycloak) |
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

### Аутентификация
- Основной IdP — **Keycloak** (OIDC). AD напрямую не используется
- Все user-атрибуты Keycloak-пользователей берутся из **JWT claims** (`department`, `job_title`, `phone`, `groups`) и сохраняются в `users` при upsert
- **Серверная сессия в Redis** (ключ — `session_id`, opaque UUID). В HTTPOnly + Secure + **SameSite=Lax** cookie `portal_session` хранится только идентификатор сессии. JWT в cookie **не кладётся**
  - SameSite=Lax (а не Strict) — иначе после редиректа Keycloak → `/auth/callback` cookie не отдаётся и сессия теряется. CSRF-защита обеспечивается Origin/Referer-check + SameSite=Lax (top-level GET-навигация безопасна)
- Роль читается из **БД** (`users.role`) при каждом запросе, не из JWT (см. `docs/roles-matrix.md`). Изменение роли через admin-API применяется немедленно
- **Dual-auth:** `users.auth_source ∈ {"keycloak", "local"}`, `users.password_hash` (bcrypt, nullable), `users.keycloak_id` nullable для локальных. Bootstrap первого admin — из env `ADMIN_EMAIL` + `ADMIN_PASSWORD` (защищён `pg_advisory_xact_lock` от race при `--workers ≥ 2`). Account-linking: при первом Keycloak-логине пользователя с тем же email и `keycloak_id IS NULL` запись переводится в `auth_source = "keycloak"`, роль сохраняется; событие пишется в логи как `auth.account_linked` (warning)
- **Аудит**: события `auth.login` / `auth.logout` с `metadata.source ∈ {"keycloak","local"}`. Отдельных типов `local_login` нет — только метаданные. Дополнительно: `auth.sso_failed` с `metadata.reason ∈ {oidc_error, invalid_state, token_exchange_failed, jwt_invalid, nonce_mismatch}` пишется при сбоях OIDC-callback
- **Auto-SSO:** гость без сессии автоматически перенаправляется на `/api/v1/auth/login` (доменный ПК → прозрачный Kerberos через Keycloak; не-доменный → форма Keycloak). Loop-protection — `sso_attempts` в `sessionStorage` (≥2 попытки за 30s → `/auth/error?reason=loop_detected`). `/login` смонтирован на AuthRedirectStub.vue (стаб-редирект на /api/v1/auth/login). LoginPage.vue — устаревший орфан-файл, не подключён в роутере (к удалению)
- **Локальный admin-вход** доступен только по прямой ссылке `/auth/local` (в публичном UI ссылок нет; backdoor для bootstrap-admin / DevOps). При `LOCAL_AUTH_ENABLED=false` форма скрыта; POST `/auth/local/login` → 403
- **Logout НЕ убивает Keycloak SSO-сессию** (`kc_service.get_logout_url` не вызывается из `logout()`). Удаляется только серверная сессия в Redis + cookie. Keycloak-юзеров редиректит на `/auth/error?reason=logged_out`, локальных — на `/auth/local?logged_out=1`. Для интранета это приемлемо — следующий заход доменного юзера прозрачно перелогинит его (см. ADR)
- **Страница ошибок SSO:** `/auth/error?reason=...` (`sso_failed`/`logged_out`/`loop_detected`/`keycloak_unavailable`/`nonce_mismatch`) — заменяет белый экран FastAPI 401. Кнопка «Войти снова» сбрасывает `sso_attempts`/`sso_failed` и идёт на `/api/v1/auth/login`. В футере мелкая ссылка на `/auth/local`

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
- **httpx таймауты:** листинг=15s, download=None, upload=600s, health=3s
- **Collabora (редактирование документов):**
  - Backend запрашивает у NC Collabora-URL для файла через OCS API (от portal-svc)
  - NC генерирует WOPI-сессию, возвращает URL + токен
  - Frontend открывает Collabora в `<iframe>` с этим URL
  - Параметр `display_name` передаётся в WOPI → в документе видно реальное имя пользователя портала
  - Collabora сохраняет изменения напрямую в NC через WOPI — портал не стоит в цепочке при редактировании
- **Collabora federation callback:** при открытии файла портал сохраняет `display_name` пользователя в Redis под случайным токеном. Nextcloud/Collabora вызывает `POST /ocs/v2.php/apps/richdocuments/api/v1/federation` — реализован в `api/nc_federation.py`, проксируется через nginx. Endpoint публичный (без auth/CSRF), защита — неугадываемый токен.
- **Audit:** каждая файловая операция пишется в `audit_log` с реальным `user_id` из сессии портала
- **Метаданные файлов**: таблица `file_items` (миграция 038) — per-file: `folder_id`, `nc_path`, `name`, `size_bytes`, `mime_type`, `uploaded_by`, `uploaded_at`. Используется в `api/files/_common.py`.

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
- **Системные настройки** (`/data/settings/system.json`): SMTP, Nextcloud, whitelist CIDR, nginx параметры. Запись → atomically через `os.replace()` + temp file
- **Keycloak-настройки** (`/data/secrets/keycloak-settings.json`): keycloak_url, keycloak_realm, keycloak_client_id/secret — только через Admin UI → вкладка «Keycloak»
- **Nginx reload**: `trigger_nginx_reload()` пишет в `/data/nginx/reload-trigger` → inotify-скрипт в контейнере `portal-nginx` перечитывает конфиг без рестарта. Генерацией include-конфигов занимается sidecar `nginx-config` — он inotifies `/data/settings/system.json` и `/data/certs/`, рендерит `allowlist.conf`/`ssl_server.conf`/`limits.conf` в `/data/nginx_conf/` из шаблонов `nginx/templates/`
- **Управление модулями** (`/data/settings/modules.json`): enable/disable `photos`, `nextcloud`; кэш в памяти (TTL 60s), инвалидация через `invalidate_modules_cache()`

### Персональные настройки пользователя
- Хранятся в `users.preferences JSONB` (не отдельная таблица)
- Структура: `{"hidden_link_ids": ["uuid1", "uuid2"]}`
- Endpoint: `PATCH /api/v1/users/me/preferences`
- При добавлении новых типов настроек — расширять тот же JSONB

### База данных
- **Soft delete** везде (кроме пользователей): `deleted_at TIMESTAMPTZ` (NULL = активна). Пользователи (`users`) удаляются **hard-delete** через `DELETE`; FK-поля (`author_id`, `created_by` и т.п.) используют `ON DELETE SET NULL`.
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
- Rate limiting: `fastapi-limiter` (per-user, Redis). Identifier — `X-Real-IP` от nginx (`backend/app/core/limiter.py::real_ip_identifier`); прямой `X-Forwarded-For` не используется — обходится клиентом. **Важно:** `X-Real-IP` нельзя подделать только при условии, что nginx является единственной точкой входа (нет вышестоящего reverse-proxy). Если перед nginx стоит другой балансер — настроить `ngx_http_realip_module` (`set_real_ip_from` + `real_ip_header`) для корректного определения IP.
- File upload: валидация MIME через python-magic
- CSP: без `unsafe-eval` (Naive UI работает без него)

---

## Структура репозитория

```
portal/
├── AGENTS.md                  ← этот файл
├── docs/
│   ├── adr.md                 ← Architecture Decision Records (ADR-001...ADR-037)
│   ├── db-schema.md           ← схема БД (все таблицы + индексы, миграции 001..038)
│   ├── api-contracts.md       ← контракты API (request/response)
│   ├── roles-matrix.md        ← матрица прав: роль × ресурс × действие
│   ├── testing.md             ← стратегия тестирования + покрытие по фазам
│   ├── deploy.md              ← production-чеклист, TLS, бэкапы, ротация секретов
│   └── integration-keycloak-nextcloud.md ← настройка Keycloak realm, NC service account
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── files/         ← FilesBreadcrumbs, FilesBulkBar, FilesCreateFolderModal, FilesDropZone, FilesImagePreview, FilesMoveModal, FilesPermissionsModal, FilesSidebar, FilesTable, FilesToolbar
│   │   │   ├── layout/        ← AppHeader, AppMobileDrawer, AppSider, HeaderLangSwitcher, HeaderThemeToggle, HeaderUserMenu
│   │   │   ├── links/         ← BookmarkFormModal, BookmarksTab, LinkCard, LinkFormModal, ServiceLinksTab
│   │   │   ├── photos/        ← LightboxModal, PhotoTrashView, PhotoPermissionsModal, FolderNode
│   │   │   ├── profile/       ← DepartmentColleagues, extensions/
│   │   │   ├── editor/        ← TipTap-расширения (IframeEmbed.ts, AlignedNodes.ts)
│   │   │   ├── widgets/       ← виджеты HomePage (PhotosWidget)
│   │   │   └── ...            ← AppLayout, EmptyState, FileFolderNode, GlobalSearch, HeroBlock, KbAttachmentsPanel, KbImportModal, KbPermissionsModal, KbSectionTree, KbVersionDiffModal, NewsAttachmentsViewer, NewsCard, NewsCoverUpload, NewsGalleryViewer, NotificationsDropdown, OnboardingTour, RichEditor, SkeletonCard
│   │   ├── pages/
│   │   │   ├── admin/
│   │   │   │   ├── tabs/      ← 14 lazy-loaded tab-компонентов: UsersTab, UserAttributesTab, LinksTab, EmailTab, SystemTab, KeycloakTab, BrandingTab, ModulesTab, KbTab, AnalyticsTab, AuditTab, MonitoringTab, PhotosTab, NewsCategoriesTab
│   │   │   │   └── admin-tabs.css
│   │   │   ├── photos/        ← PhotosIndexPage.vue, PublicPhotoPage.vue, PublicFolderPage.vue, MySharesPage.vue
│   │   │   └── ...            ← HomePage, NewsListPage, NewsDetailPage, NewsFormPage, KbListPage, KbArticlePage, KbPlaceholderPage, FilesPage, LinksAndBookmarksPage, BookmarksPage, AdminPage, UserProfileView, AuthErrorPage, AuthLocalPage, AuthRedirectStub, ...
│   │   ├── queries/           ← TanStack Query composables: admin.ts, files.ts, kb.ts, keys.ts, links.ts, modules.ts, news.ts, notifications.ts, photos.ts, users.ts
│   │   ├── stores/            ← Pinia stores: auth, branding, files, layout, links, modules, notifications, photos, theme
│   │   ├── composables/       ← useAppMenu, useBreakpoints, useCollabora, useConfirmDialog, useFavicon, useFilesBulkOps, useFilesSelection, useFilesTree, useFilesUpload, useGlobalHotkeys, useGlobalSearch, useLayoutHeader, useLinkIconUpload, usePhotoUpload, useRecentArticles, useSortableGroups
│   │   ├── api/               ← типизированные API-клиенты: analytics, audit, auth, bootstrap, files, kb, links, news, notifications, photos, userAttributeMappings, users
│   │   ├── i18n/              ← ru.json (мастер), en.json
│   │   ├── utils/             ← extractDroppedFiles.ts, formatDate.ts, markdown.ts, parseApiError.ts, sanitize.ts (DOMPurify), url.ts
│   │   └── types/             ← TypeScript типы, types.gen.d.ts (openapi-typescript, в .gitignore)
│   ├── tests/
│   │   ├── unit/              ← Vitest unit tests
│   │   └── e2e/               ← Playwright E2E tests (smoke, local-login, security-headers, photos)
│   ├── vite.config.ts
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── files/         ← подпакет: _common, folders, upload, download, files_ops, permissions, sync
│   │   │   ├── kb/            ← подпакет: _common, _frontmatter, sections, tags, articles, versions, comments, suggestions, feedback, permissions, media, attachments, export_import
│   │   │   ├── photos/        ← подпакет: _common, folders, photos, permissions, sharing, zip_jobs, import_scan, thumbnails, tags
│   │   │   └── ...            ← auth, users, user_attribute_mappings, news, news_categories, kb_extra (shim), links, bookmarks, search, branding, system_settings, modules, analytics, audit, notifications, nc_federation, keycloak_admin, health, deps, bootstrap
│   │   ├── core/              ← bootstrap, cache_version, config, constants, database, lifespan, limiter, logging, metrics, pdf, redirects, sanitize, security, sentry, system_config, text, uploads
│   │   ├── middleware/        ← csrf, idempotency, logging, metrics, security_headers, session
│   │   ├── models/            ← SQLAlchemy models: files, kb, links, news, notification, photos, user, user_attribute_mapping
│   │   ├── schemas/           ← Pydantic schemas: branding, files, kb, kb_extra, links, news, notification, photos, user, user_attribute_mapping
│   │   ├── services/
│   │   │   ├── nextcloud/     ← пакет: __init__.py, service.py, webdav.py, collabora.py
│   │   │   ├── acl_base.py           ← общий код ACL: get_cached/set_cached/scan_and_delete/subject_ids_for_user
│   │   │   ├── files_acl.py          ← ACL для файлового модуля (CTE, Redis-кэш TTL 5 мин); batch_resolve_folder_permissions() — N+1 устранён
│   │   │   ├── files_acl_persistence.py  ← персистентный кэш ACL (atomic write, asyncio.Lock)
│   │   │   ├── kb_acl.py             ← ACL для KB: batch_resolve_section/article_permissions — N+1 устранён
│   │   │   ├── kb.py                 ← бизнес-логика KB: record_article_view, set_article_tags
│   │   │   ├── news.py               ← бизнес-логика новостей: upload/delete cover, gallery, attachment
│   │   │   ├── nginx_config.py       ← trigger_nginx_reload(), _build_nginx_csp(), _CERTS_DIR
│   │   │   ├── photos_acl.py         ← ACL для фотогалереи (viewer/uploader/manager)
│   │   │   ├── photos_storage.py     ← Pillow + pillow-heif, WebP/AVIF thumbnails, EXIF strip GPS
│   │   │   ├── tls_status.py         ← проверка наличия TLS-сертификатов
│   │   │   ├── audit_partitions.py   ← ensure_partitions / drop_old_partitions (retention 12 мес)
│   │   │   └── ...                   ← keycloak, nc_federation, audit, notifications, session
│   │   ├── worker/            ← ARQ tasks: audit, notifications, news, photos, files, metrics
│   │   └── main.py            ← FastAPI app + middleware + routers; создаёт /data/{avatars,news_media,link_icons}
│   ├── migrations/
│   │   ├── init.sql           ← расширения + FTS (russian_hunspell) + первые партиции audit_log
│   │   └── versions/          ← Alembic migrations 001_users .. 038_file_items
│   ├── tests/
│   │   ├── unit/              ← Pytest unit (без внешних зависимостей)
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
│   ├── Dockerfile             ← образ portal-nginx (alpine + inotify-tools)
│   ├── Dockerfile.config      ← образ portal-nginx-config (sidecar: jq + envsubst + inotify-tools)
│   ├── entrypoint-config.sh   ← entrypoint sidecar: первый рендер + inotify-watch + reload
│   ├── render-config.sh       ← рендерит шаблоны → /data/nginx-conf/*.conf + тачит reload-trigger
│   ├── templates/             ← http_redirect, https_server, http_only_server, proxy_locations
│   └── certs/
├── postgres/                  ← кастомный Dockerfile с hunspell-ru словарями
├── system_data/               ← runtime-данные (volume, не в git)
│   ├── nginx/                 ← активный nginx.conf + entrypoint.sh + reload-trigger (inotify)
│   ├── nginx_conf/            ← динамически генерируемые nginx include-файлы (allowlist.conf, limits.conf, ssl_server.conf)
│   ├── certs/                 ← TLS-сертификаты
│   ├── secrets/               ← keycloak-settings.json и другие секреты
│   └── settings/              ← modules.json, system.json, email-settings.json
├── docker-compose.yml         ← services: postgres, redis, screenshot-service, migrations, backend, worker, nginx-config (sidecar), frontend, nginx (container_name: portal-nginx)
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
Стандартный образ `postgres:16` требует кастомного `Dockerfile` для установки hunspell-словарей:
```dockerfile
# postgres/Dockerfile
FROM postgres:16
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        hunspell-ru \
    && rm -rf /var/lib/apt/lists/*
RUN PGSHARE=$(pg_config --sharedir) \
    && mkdir -p "${PGSHARE}/tsearch_data" \
    && cp /usr/share/hunspell/ru_RU.dic "${PGSHARE}/tsearch_data/russian.dict" \
    && cp /usr/share/hunspell/ru_RU.aff "${PGSHARE}/tsearch_data/russian.affix"
COPY hunspell/russian.stop /tmp/russian.stop
RUN PGSHARE=$(pg_config --sharedir) \
    && cp /tmp/russian.stop "${PGSHARE}/tsearch_data/russian.stop"
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

Бэкенд обращается к сервису по фиксированному URL `http://screenshot-service:9000` (зашито в `docker-compose.yml` и default-значение в `app/core/config.py`). Менять имеет смысл только при запуске бэкенда вне Compose — переменная `SCREENSHOT_SERVICE_URL` тогда задаётся в окружении процесса.
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

### Конфигурация: bootstrap (env) vs runtime (JSON) — ADR-037
С мая 2026 параметры разделены по назначению:

- **Bootstrap (env, `app/core/config.py::Settings`)** — то, что нужно ДО старта (БД, Redis, секреты, Keycloak OIDC, bootstrap-admin, screenshot-service URL, размеры пула DB). Меняется только редеплоем.
- **Runtime (JSON, `/data/settings/system.json` через `app/core/system_config.py::SystemSettings`)** — управляется через Admin UI без рестарта: `portal_base_url`, лимиты загрузки (`max_upload_size_mb`, `news_attachment_max_size_mb`, `kb_*_max_size_mb`), `allowed_cidr`, `log_level`/`log_force_json`/`log_slow_request_ms`, `sentry_dsn`, `prometheus_metrics_enabled`/`metrics_token`, `arq_max_jobs`, `nc_files_root`, `nc_service_username`, `nextcloud_url`, `nc_service_app_password`.

**Миграция со старых установок** — однократная: при старте бэкенда `migrate_env_to_system_settings()` создаёт `system.json` из легаси env-переменных, если файла ещё нет. После миграции переменные из `.env` игнорируются (логируется warning `config.deprecated_env_vars_ignored` — операторe нужно их удалить).

### Переменные окружения (`.env`)
Полный список — `.env.example`. Ключевые (только bootstrap):

| Переменная | Назначение | Пример / default |
|-----------|-----------|--------|
| `POSTGRES_PASSWORD` | пароль PostgreSQL | (нет default — обязательно) |
| `REDIS_PASSWORD` | пароль Redis | (нет default — обязательно) |
| `SECRET_KEY` | ≥32 символа, CSRF/sessions | (нет default — обязательно) |
| `DATABASE_URL` | asyncpg URL (авто-подставляется в Compose; вручную — только вне Compose) | `postgresql+asyncpg://portal:pwd@postgres:5432/portal` |
| `REDIS_URL` | Redis URL (авто-подставляется в Compose; вручную — только вне Compose) | `redis://:pwd@redis:6379/0` |
| `ENVIRONMENT` | `production`/`development` | `production` |
| `ADMIN_EMAIL` | Email bootstrap-admin | `admin@company.local` |
| `ADMIN_PASSWORD` | Пароль bootstrap-admin | (обязательно, ≥12 символов) |
| `LOCAL_AUTH_ENABLED` | Включить локальную аутентификацию | `true` |
| `SCREENSHOT_SERVICE_SECRET` | shared-secret для screenshot-service (генерится `setup.sh`) | (нет default) |
| `SCREENSHOT_ALLOWED_ORIGINS` | (опц.) allowlist origin'ов для `/screenshot` (SSRF-защита) | (пусто — endpoint выключен) |
| `DB_ECHO` / `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_RECYCLE` | DB pool tuning | `false` / `20` / `30` / `3600` |

> Параметры **runtime** (`PORTAL_BASE_URL`, `MAX_UPLOAD_SIZE_MB`, `ALLOWED_CIDR`, `SENTRY_DSN`, `PROMETHEUS_METRICS_ENABLED`, `LOG_LEVEL`, `ARQ_MAX_JOBS`, `NC_FILES_ROOT`, `NC_SERVICE_APP_PASSWORD`, `NEXTCLOUD_URL` и др.) **больше не читаются из env**. При первом старте легаси-значения мигрируются в `system.json` автоматически; дальше — только Admin UI.
>
> **Keycloak** (`KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`) — также **только** через Admin UI → «Keycloak» (`/data/secrets/keycloak-settings.json`). Никакого env-fallback нет: до первой настройки через UI OIDC-флоу будет недоступен (используйте локальный bootstrap-admin для входа).

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
- Email в БД хранится в исходном виде, но уникальность обеспечена по `LOWER(email)` (partial unique индекс `idx_users_email_ci_active WHERE deleted_at IS NULL`, миграция 037 — позволяет переиспользовать email после soft-delete пользователя); все lookups в auth/users используют `func.lower()`
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
| **Auth (Keycloak OIDC + локальный)** | ✅ | `api/auth.py`, `core/security.py`, `services/session.py` |
| **Пользователи + профили** | ✅ | `api/users.py`, `models/users`, `stores/auth.ts` |
| **Новости** | ✅ | `api/news.py`, `api/news_categories.py`, `pages/NewsListPage.vue` |
| **Ярлыки и закладки** | ✅ | `api/links.py`, `api/bookmarks.py`, `pages/LinksPage.vue` |
| **База знаний (KB)** | ✅ | `api/kb/` (пакет), `api/kb_extra.py` (shim), `services/kb_acl.py`, `services/kb.py`, `pages/KbListPage.vue` |
| **Глобальный поиск** | ✅ | `api/search.py`, `components/GlobalSearch.vue` |
| **Файлы (Nextcloud)** | ✅ | `api/files/` (пакет), `services/nextcloud/`, `services/files_acl.py`, `pages/FilesPage.vue` |
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
- ❌ Не использовать стандартный `postgres:16` без кастомного Dockerfile с hunspell (пакет `hunspell-ru`)
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
