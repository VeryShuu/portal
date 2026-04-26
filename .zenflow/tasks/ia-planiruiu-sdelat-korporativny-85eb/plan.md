# Корпоративный портал — план работ

## Configuration
- **Artifacts Path**: `.zenflow/tasks/ia-planiruiu-sdelat-korporativny-85eb`

## Статус

### [x] Step 1: Изучение ТЗ, исследование практик, создание спецификации
- Прочитано ТЗ
- Исследованы лучшие практики 2025-2026 (intranet portals, Keycloak+Nextcloud, FastAPI+Vue3)
- Создан файл `requirements.md` в корне репозитория с:
  - Полным списком функционала (базовый + дополненный)
  - Техническими деталями реализации (схемы БД, API endpoints, WOPI, SSO)
  - Архитектурной схемой
  - Вопросами для обсуждения с заказчиком
  - Оценкой трудоёмкости (~75 чел.-дней)

### [x] Step 2: Обсуждение и уточнение требований
- Зафиксирован стек: Vue 3 + TypeScript, FastAPI, PostgreSQL 16, Redis 7
- Зафиксированы все архитектурные решения (Keycloak-only IdP, Nextcloud impersonation, Naive UI, Markdown storage, Playwright PDF, fastapi-limiter, Sentry)
- Уточнены опциональные модули (календарь и PWA — отложены)
- requirements.md доведён до v0.7 после code-review сессии:
  - Дублирующийся SQL убран из requirements.md (источник правды — docs/db-schema.md)
  - preferences JSONB добавлен в users (персонализация ярлыков)
  - Шаблоны документов перенесены в v2
  - NC_USER_ID_FIELD TBD — файловый модуль заморожен до миграции Nextcloud
  - MAX_UPLOAD_SIZE_MB через .env; hunspell Docker; Playwright Docker; streaming upload — задокументированы
  - Добавлен endpoint PATCH /admin/users/{id}/role

### [x] Step 3: Проектирование архитектуры и БД
- [x] ADR: docs/adr.md
- [x] Финальная схема БД: docs/db-schema.md
- [x] API контракты: docs/api-contracts.md
- [x] AI-агент промт: AGENT.md
- Схема деплоя зафиксирована в requirements.md (секция 8)

### [x] Step 4: Phase 0 — Инфраструктура (фундамент, до всего остального)
- [x] Docker Compose: сервисы postgres, redis, backend, frontend, nginx, worker
- [x] Кастомный `postgres/Dockerfile` с hunspell-ru словарями (обязательно для FTS)
- [x] `backend/migrations/init.sql`: расширения pg_trgm, unaccent, FTS конфигурация russian_hunspell, первые партиции audit_log
- [x] Alembic: базовая конфигурация + первая миграция (таблица users)
- [x] Nginx: TLS, security headers, IP-whitelist, `client_max_body_size` из `MAX_UPLOAD_SIZE_MB`
- [x] `backend/Dockerfile` с Playwright/Chromium (PDF-экспорт + E2E тесты — один образ)
- [x] `.env.example` со всеми переменными
- [x] GitHub Actions: CI (lint + test), build Docker images
- [x] Health endpoints: `GET /health` (always 200) и `GET /ready` (DB + Redis + NC)
- [x] structlog + Sentry SDK подключены (logging с первого модуля)
- [x] Prometheus метрики: базовая инструментация FastAPI

### [x] Step 5: Phase 1 — Новости + Пользователи + i18n
_ТЗ: §3.1 Аутентификация, §3.2 Профили, §3.4 Новости, §2 i18n_

**Аутентификация и профили:**
- [x] Keycloak OIDC: Authorization Code Flow + PKCE (`GET /auth/login`, `GET /auth/callback`)
- [x] Silent authentication (`prompt=none`) при открытии портала
- [x] Хранение токенов в Redis (session_id в HTTPOnly cookie, не сам JWT)
- [x] Refresh token rotation, автообновление сессии (`POST /auth/refresh`)
- [x] Ролевая модель: `reader` / `editor` / `admin` (хранится в `users.role`, см. roles-matrix.md)
- [x] `POST /auth/logout` + SLO через Keycloak front-channel (`GET /auth/logout`)
- [x] Таблица `users`: upsert при каждом логине из JWT claims (ФИО, отдел, должность, телефон)
- [x] `GET /users`, `GET /users/{id}` — справочник сотрудников
- [x] `PATCH /users/me/profile` — статус присутствия, язык, уведомления
- [x] `POST /users/me/avatar` — загрузка аватара (local volume `/data/avatars`)
- [x] `PATCH /users/me/preferences` — preferences JSONB (hidden_link_ids)
- [x] `POST /users/admin/sync` — ручная синхронизация из Keycloak Admin API (ARQ)
- [x] `PATCH /users/admin/{id}/role` — смена роли
- [x] Блокировка доступа вне VPN/внутренней сети (Nginx allow/deny по CIDR)
- [x] Аудит входов/выходов в `audit_log` (`auth.login` / `auth.logout` + metadata.source)

**Новости:**
- [x] Таблица `news` + `news_versions` (Alembic миграция)
- [x] `POST /news`, `PUT /news/{id}`, `DELETE /news/{id}` — CRUD
- [x] WYSIWYG-редактор TipTap v2 + tiptap-markdown (dual-mode)
- [x] Черновики с автосохранением каждые 30 сек (`PUT /news/{id}/draft`)
- [x] Таргетирование по отделам и ролям (`target_departments`, `target_roles`)
- [x] Отложенная публикация (`publish_at`) — ARQ cron каждую минуту
- [x] Автоархивация (`archive_at`) — ARQ cron каждый час
- [x] Закрепление новости (`is_pinned`), категории
- [x] Soft delete + восстановление
- [x] Версионность (история редактирования)
- [x] `GET /news` с пагинацией + фильтрами + таргетингом по профилю из БД
- [x] Счётчик просмотров (дедупликация 1/час/user через Redis)
- [x] Главная страница: последние новости + закреплённые + приветствие
- [x] Структура медиа: `/data/news_media/{news_id}/cover.{ext}` (подпапки по news_id)
- [x] Галерея: таблица `news_gallery_images`, CRUD + reorder (drag-and-drop), lightbox (`n-image-group`)
- [x] Вложения: таблица `news_attachments`, загрузка любых файлов, скачивание с оригинальным именем
- [x] Ограничение размера файлов: `NEWS_ATTACHMENT_MAX_SIZE_MB=50` (env)
- [x] `DELETE /news/{id}` — удаление с подтверждением на фронте (диалог)
- [x] Экспорт новости: `GET /news/{id}/export/html`, `/export/markdown`, `/export/pdf` (Playwright)
- [x] Экспорт включает обложку, галерею и картинки из тела — все встраиваются как base64 data URI (standalone файлы)
- [x] Исправлен `Content-Disposition` для кириллических имён файлов (RFC 5987)
- [x] `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` — зафиксирован в Dockerfile и docker-compose.yml

**i18n:**
- [x] vue-i18n v9: `ru.json` (мастер) + `en.json` — все строки интерфейса с первого компонента
- [x] Переключатель языка в шапке, сохранение в `users.lang`
- [x] CI-проверка: отсутствующие ключи `en.json` vs `ru.json` = ошибка сборки
- [x] Тёмная/светлая тема через Naive UI `n-config-provider`

**Тесты Phase 1:**
- [x] Unit: JWT parsing, token refresh, маппинг claims → модель, таргетинг новостей (29+ тестов)
- [x] Integration: Keycloak OIDC flow (mock), DB upsert, ARQ задачи публикации
- [ ] E2E: логин → главная с новостями → выход (SLO) — запускается с Docker
- [ ] E2E: создание новости с таргетом → отложенная публикация — запускается с Docker

### [x] Step 6: Phase 2 — Ярлыки сервисов + Закладки
_ТЗ: §3.5 Навигация и ярлыки, §3.9 Закладки_


- [x] Таблица `service_links` (Alembic миграция)
- [x] `GET /links` — все активные ярлыки, сгруппированные по категориям
- [x] `POST /links`, `PUT /links/{id}`, `DELETE /links/{id}` — CRUD только admin
- [x] SSO-проброс при клике: если `supports_sso=true` → передаётся `id_token_hint` в URL
- [x] Персонализация: скрытие ненужных ярлыков через `PATCH /users/me/preferences` (`hidden_link_ids`)
- [x] Таблица `bookmarks` (Alembic миграция)
- [x] `GET /bookmarks`, `POST /bookmarks`, `DELETE /bookmarks/{id}` — личные закладки
- [x] `PATCH /bookmarks/reorder` — drag-and-drop сортировка (с pg_advisory_xact_lock)
- [x] Группы закладок (`group_name`)
- [x] Блок «Избранное» на главной странице

**Тесты Phase 2:**
- [x] Unit: валидация URL ярлыков, сортировка закладок (12 тестов)
- [x] Integration: DB CRUD ярлыков и закладок
- [ ] E2E: добавить закладку → drag-and-drop → сохранилось; скрыть ярлык → не показывается — запускается с Docker

### [x] Step: Phase 2.1 — Локальная аутентификация
_ТЗ: §3.1.1 Локальная аутентификация_

> Реализуется сразу после Phase 2 — нужна для bootstrap первого admin и аварийного входа без Keycloak.

**Бэкенд:**
- [x] Alembic миграция: `ADD COLUMN auth_source VARCHAR(20) NOT NULL DEFAULT 'keycloak'`, `ADD COLUMN password_hash VARCHAR(255) NULL`; `ALTER COLUMN keycloak_id DROP NOT NULL`
- [x] `POST /api/v1/auth/local/login` — принимает `{email, password}`, проверяет bcrypt, создаёт Redis-сессию, устанавливает HTTPOnly cookie `session_id`
- [x] Bootstrap при старте: если задан `ADMIN_EMAIL` + `ADMIN_PASSWORD` и нет ни одного `role = "admin"` → создаётся локальный admin (idempotent)
- [x] `POST /api/v1/admin/users/local` — создание локальных пользователей (только admin): `{email, full_name, password, role}`
- [x] `PATCH /api/v1/users/me/password` — смена пароля (только для `auth_source = "local"`)
- [x] `PATCH /api/v1/admin/users/{id}/password` — сброс пароля admin'ом (только локальные)
- [x] Rate limit: 5 попыток / 15 мин / IP для `POST /auth/local/login` (через fastapi-limiter)
- [x] Явная 403 при попытке локального входа с Keycloak-аккаунтом (сообщение «Use Keycloak SSO»)
- [x] Аудит: `event_type = "local_login"` / `"local_logout"` в `audit_log`
- [x] Env: `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `LOCAL_AUTH_ENABLED`

**Фронтенд:**
- [x] Страница `/login`: форма email+password + кнопка «Войти через Keycloak (SSO)»; SSO-кнопка — по умолчанию, форма — fallback или при `LOCAL_AUTH_ENABLED=true`
- [x] Страница смены пароля в профиле (видна только для `auth_source = "local"`)

**Тесты Phase 2.1:**
- [x] Unit: bcrypt hash/verify, bootstrap idempotency, auth_source изоляция (17 тестов, все прошли)
- [x] Integration: stubs — local login flow, смена пароля, auth_source изоляция
- [ ] E2E: локальный admin входит по паролю → главная → выход; попытка Keycloak-аккаунта через форму → 403 (запускается с Docker)

### [x] Step 6.5: UI Redesign (MAGE brandbook) — реализовано без ТЗ
_Добавлено постфактум после ревью коммитов. Исходно в ТЗ не было._

- [x] Документ `UI.md` с планом редизайна (8 этапов) на основе MAGE brandbook
- [x] Stage 1 — design tokens (`src/styles/tokens.css`, `typography.css`), naive-ui theme overrides (`src/styles/naive-theme.ts`), глобальные стили
- [x] Stage 2 — AppLayout с navy header, grouped sider, search pill в шапке
- [x] Stage 3 — HomePage: Hero-блок, сетка виджетов, skeleton loaders (`HeroBlock.vue`, `SkeletonCard.vue`)
- [x] Stage 4 — Ctrl+K global search palette (`GlobalSearch.vue`) — только UI, backend поиск — Phase 3
- [x] Stage 5 — Редизайн страниц новостей (list / detail / form) с MAGE-палитрой
- [x] Stage 6-7 — login split-screen, profile hero, bookmark/link card grids
- [x] Stage 8 — a11y: skip-to-content link, main landmark
- [x] Precompile vue-i18n messages (устранение `new Function` eval — CSP совместимо)
- [x] Fallback логина при недоступности `/auth/config`
- [x] Admin-страница (`AdminPage.vue`): управление ролями пользователей + CRUD ярлыков с UI
- [x] `EmptyState.vue`, `NewsCard.vue`, `NewsAttachmentsViewer.vue`, `NewsGalleryViewer.vue`, `RichEditor.vue` — общие UI-компоненты

**Security follow-ups (ревью):**
- [x] dompurify для санитайзинга HTML на фронте
- [x] P0/P1/P2 замечания code-review закрыты (commits `b84f39e`, `c654a47`, `6344dde`)
- [x] Nginx: динамическая DNS-резолвция апстримов, безопасные заголовки на `/media/`

### [x] Step 6.7: Комплексная система логирования
_Добавлено по результатам ревью системы логирования._

- [x] `LOG_LEVEL`, `LOG_FORCE_JSON`, `LOG_SLOW_REQUEST_MS` в `Settings` и `.env.example`
- [x] Processors: `redact_secrets_processor` (password/token/secret/cookie/csrf/api_key — на любой глубине, включая dict/list)
- [x] Processor `mask_pii_processor` — маскирует email до `a***@domain` во всех строковых значениях
- [x] Processor `truncate_large_values_processor` — обрезает строки > 4 КБ, помечает `_truncated_fields`, ставит `_event_oversize`
- [x] `add_service_name_processor` — `service=portal-backend|portal-worker` в каждом event
- [x] JSON-рендер в production / при non-TTY stdout, цветной ConsoleRenderer в dev
- [x] Перехват и единая обработка логов `uvicorn`, `arq`, `sqlalchemy.engine`
- [x] Helpers `bind_request_context()` (фильтрует None) / `clear_request_context()`
- [x] HTTP-middleware: уровень лога по `status_code` (5xx → error, 4xx → warning, slow → warning), `try/except` с `logger.exception("http.request_failed")`
- [x] `X-Request-Id` принимается из заголовка балансера или генерируется UUID
- [x] `client_ip` извлекается из `X-Real-IP` / `X-Forwarded-For` / `request.client`
- [x] `user_id`/`role`/`auth_source` биндятся в contextvars в `get_current_user`
- [x] ARQ worker: `on_job_start` биндит `job_id`/`job_try`/`function`/`correlation_id`, `on_job_end` очищает
- [x] `logger.error` → `logger.exception` с `error_type` в health/auth/news/audit/users worker
- [x] docker-compose: единый `x-logging` anchor с json-file rotation (50 МБ × 5 файлов, gzip)
- [x] `tests/unit/test_logging.py` — 37 тестов: redaction, PII masking, truncation, contextvars, JSON-output

### [x] Step 6.8: Расширенная система оформления (Branding System)
_Добавлено по запросу пользователя: название портала, accent color, favicon, login-bg, banner, welcome text._

**Backend (`backend/app/api/branding.py`):**
- [x] `BrandingSettings`: `portal_name`, `portal_tagline`, `accent_color`, `welcome_subtitle`, `banner_enabled`, `banner_text`, `banner_type`, `banner_expires_at`
- [x] `GET /branding/settings`, `PUT /admin/branding/settings`
- [x] `GET/POST/DELETE /branding/favicon` и `/admin/branding/favicon`
- [x] `GET/POST/DELETE /branding/login-bg` и `/admin/branding/login-bg`
- [x] Общие хелперы `_find_file`, `_delete_files`, `_upload_image`

**Frontend Store (`src/stores/branding.ts`):**
- [x] Pinia store с `settings`, `isBannerActive`, `lightOverrides`, `darkOverrides`
- [x] HSL color derivation (base → hover → pressed)
- [x] `applyCssVars` — устанавливает CSS vars `--color-brand-red*`
- [x] `applyFavicon` — динамически меняет `<link rel="icon">`
- [x] `load()` + `save()` методы
- [x] Реактивные `themeOverrides` для naive-ui (accent color меняется в реальном времени)

**Frontend интеграция:**
- [x] `App.vue`: `themeOverrides` из `brandingStore.lightOverrides/darkOverrides`
- [x] `LoginPage.vue`: `portalName`, `portalTagline`, `loginBgUrl` (HEAD-запрос)
- [x] `HeroBlock.vue`: `welcome_subtitle` из настроек
- [x] `HomePage.vue`: баннер с типами (info/warning/error/success) + автоскрытие + dismiss

**AdminPage.vue — вкладка «Оформление»:**
- [x] Секция Favicon: загрузка/сброс (PNG, JPEG, SVG, ICO)
- [x] Секция Фон страницы входа: загрузка/сброс с preview
- [x] Секция Общие настройки: название, слоган, accent color (color picker + hex input), welcome text
- [x] Секция Баннер: включение, текст, тип, дата автоскрытия
- [x] CSS классы: `.branding-favicon-preview`, `.branding-loginbg-preview`, `.branding-fields`, `.branding-color-row`, `.branding-color-input`, `.branding-color-swatch`
- [x] i18n: все ключи `admin.branding.*` в `ru.json` и `en.json`

### [x] Step 6.6: Синхронизация документации с реальной реализацией
_Добавлено постфактум после ревью коммитов и документации._

- [x] `docs/db-schema.md` — добавлены секции `news_gallery_images` и `news_attachments` (миграция 006), статусные предупреждения для KB/notifications (плановые), ERD с news relationships
- [x] `docs/api-contracts.md` — добавлены endpoints галереи/вложений/экспорта новостей; `GET /links/{id}/sso-url`; Files-модуль помечен BLOCKED до миграции Nextcloud → Keycloak OIDC
- [x] `docs/roles-matrix.md` — добавлены строки news cover/gallery/attachments/export и `GET /links/{id}/sso-url`; обновлены local-auth endpoints Phase 2.1
- [x] `docs/testing.md` — покрытие по фазам обновлено до фактического (Phase 0/1/2/2.1): `test_security`, `test_session`, `test_news_service`, `test_links_bookmarks`, `test_local_auth`
- [x] `docs/adr.md` — добавлены ADR-016 (EmailStr с `.local`-доменами), ADR-017 (dual-auth, единая Redis-сессия, роль из БД)
- [x] `AGENT.md` — версия `requirements.md` обновлена до v1.0; в дереве репозитория добавлены `testing.md` и `UI.md`; отмечены dual-auth, account-linking, Naive UI provider requirement, Pydantic EmailStr edge-case
- [x] `requirements.md` v1.0 — зафиксированы Phase 2.1 как завершённая, `.env.example` с `ADMIN_EMAIL`/`ADMIN_PASSWORD`/`LOCAL_AUTH_ENABLED`, bcrypt через `bcrypt` lib (SHA256 pre-hash)

### [x] Step 7: Phase 3 — База знаний + Поиск
_ТЗ: §3.3 База знаний, §3.7 Умный поиск_

**База знаний:**
- [x] Таблицы `kb_sections`, `kb_articles`, `kb_article_versions`, `kb_tags`, `kb_article_tags`, `kb_article_comments`, `kb_suggestions`, `kb_article_feedback` (миграция `008_kb`)
- [x] `GET /kb/sections` — дерево разделов (рекурсивный CTE для хлебных крошек)
- [x] `POST /kb/sections`, `PUT /kb/sections/{id}`, `DELETE /kb/sections/{id}` — CRUD разделов
- [x] `GET /kb/articles`, `POST /kb/articles`, `PUT /kb/articles/{id}`, `DELETE /kb/articles/{id}`
- [x] TipTap v2 (RichEditor.vue) — WYSIWYG редактор статей
- [x] Черновики с автосохранением каждые 30 сек (`PUT /kb/articles/{id}/draft`)
- [x] Оптимистичная блокировка: поле `version`, 409 Conflict при коллизии
- [x] Версионность статей: `GET /kb/articles/{id}/versions`, откат к версии N
- [x] Soft delete + восстановление (`POST /kb/articles/{id}/restore`)
- [x] Теги: многие-ко-многим через `kb_article_tags`
- [x] Комментарии: `GET/POST /kb/articles/{id}/comments`, `DELETE .../comments/{id}` (автор или admin)
- [x] «Предложить правку» (`POST /kb/articles/{id}/suggest`) + рассмотрение (`POST /kb/suggestions/{id}/review`)
- [x] Кнопка «Статья полезна?» — `POST /kb/articles/{id}/feedback` (upsert)
- [x] Счётчик просмотров (Redis дедупликация 1/час/user)
- [x] Экспорт PDF: Playwright/Chromium (`GET /kb/articles/{id}/export/pdf`)
- [x] Экспорт DOCX: python-docx (`GET /kb/articles/{id}/export/docx`)

**Поиск:**
- [x] `GET /search?q=...` — единый поиск: KB-статьи + новости + ярлыки + пользователи
- [x] FTS через PostgreSQL `body_tsvector` (russian_hunspell) + pg_trgm fallback
- [x] `GET /search/suggest?q=...` — typeahead через pg_trgm (debounce 400 мс на фронте)
- [x] Нечёткий поиск (опечатки): `pg_trgm similarity ≥ 0.3`
- [x] Фильтр по типу (`?type=article|news|link|user`)
- [x] KB-результаты в GlobalSearch (`Ctrl+K`) — параллельный запрос
- [x] Аудит поисковых запросов в `audit_log`

**Фронтенд:**
- [x] `KbListPage.vue` — список статей с боковым деревом разделов, фильтры, пагинация
- [x] `KbArticlePage.vue` — детальная статья: markdown-it + DOMPurify, feedback, комментарии, версии, правки, экспорт
- [x] `KbArticleFormPage.vue` — форма создания/редактирования, автосохранение черновика
- [x] `KbSectionTree.vue` — рекурсивное дерево разделов
- [x] Маршруты: `/kb`, `/kb/create`, `/kb/articles/:id`, `/kb/articles/:id/edit`
- [x] i18n: `kb.*` ключи в `ru.json` и `en.json`

**Тесты Phase 3:**
- [x] Unit: 37 тестов (slugify, оптимистичная блокировка, права доступа, soft delete, версионирование, view dedup, комментарии, feedback, поиск, дерево разделов, экспорт) — все прошли
- [ ] Integration: DB CRUD с реальным PostgreSQL (FTS запросы), Playwright PDF — запускается с Docker
- [ ] E2E: создать статью → найти с опечаткой → экспорт PDF → откат версии — запускается с Docker
- [ ] E2E: `reader` пытается создать статью → 403 — запускается с Docker

**Документация:**
- [x] `docs/db-schema.md` — добавлены таблицы `kb_suggestions`, `kb_article_feedback`, обновлён список миграций до `008_kb`, снят статус «планируемое»
- [x] `docs/api-contracts.md` — добавлены endpoints: `PUT /kb/sections/{id}`, `GET/POST suggestions`, `DELETE comments`, `POST feedback`

### [x] Step 7.5: Комплексная система тестирования (review + overhaul)
_Добавлено по результатам ревью testing-инфраструктуры (исходно 6/10)._

- [x] `backend/tests/conftest.py` — расширен (env defaults, фабрики User/News/KbArticle, AsyncClient, authed_client_factory, маркеры)
- [x] `backend/pyproject.toml` — pytest-xdist/randomly/mock/fakeredis, strict-markers, branch coverage, fail_under=70
- [x] `backend/tests/integration/conftest.py` — real_db_session с TRUNCATE-cleanup, real_user/real_editor/real_admin
- [x] Integration: `test_news_db.py`, `test_session_redis.py`, `test_kb_search.py`, `test_local_auth_db.py`, `test_rate_limit.py`, `test_audit_partitions_real.py`
- [x] `backend/tests/security/` (новый каталог): `test_security_headers.py`, `test_csrf.py`, `test_auth_required.py`, `test_xss_sanitization.py`, `test_password_security.py` (~40 тестов)
- [x] `frontend/playwright.config.ts` — chromium + mobile проекты, junit + html reporter, traces on first retry
- [x] E2E: `smoke.spec.ts`, `local-login.spec.ts`, `security-headers.spec.ts`
- [x] Frontend unit расширен: `url.spec.ts`, `sanitize.spec.ts`, `router-guards.spec.ts`, `rich-editor.spec.ts`
- [x] `load/` (новый каталог): `smoke.js`, `baseline.js`, `search.js`, `portal-load.js` (300 VU per ТЗ §7)
- [x] CI обновлён: alembic migrate перед integration, `--cov-fail-under=60`, отдельные jobs `frontend-e2e` (smoke) и `load-smoke` (k6 inspect)
- [x] `docs/testing.md` переписан: новая структура, маркеры, фикстуры, покрытие по слоям, CI-таблица

### [x] Step 7.6: Phase 3.5 — KB: Markdown-хранилище, медиа, импорт/экспорт
_Обсуждено с заказчиком: KB должна работать как Obsidian — хранить Markdown, поддерживать вставку фото/файлов, импорт и экспорт совместимый с Obsidian vault._

> **Источник правды — PostgreSQL.** Файловая система используется только для медиа и временных файлов экспорта.
> `tiptap-markdown` уже установлен (v0.8.0), но не активирован — переход минимально инвазивный.

**Бэкенд — система прав KB (ACL):**
- [x] Alembic миграция `009_kb_acl`:
  - Таблица `kb_section_permissions` (`id`, `section_id` FK, `subject_type` CHECK('user','group'), `subject_id` varchar(255), `subject_name` varchar(255), `permission` CHECK('viewer','editor','manager'), `granted_by` FK users, `created_at`)
  - Таблица `kb_article_permissions` (аналогично, `article_id` вместо `section_id`)
  - `ALTER TABLE kb_articles ADD COLUMN inherit_permissions BOOLEAN NOT NULL DEFAULT TRUE`
  - Индексы: `(section_id, subject_id)`, `(article_id, subject_id)`
- [x] `backend/app/services/kb_acl.py` — сервис проверки прав:
  - `async def resolve_permission(user, article, db) → Permission | None` — алгоритм: 1) portal admin → full; 2) создатель → manager; 3) `inherit_permissions=false` → `kb_article_permissions`; 4) `inherit_permissions=true` → рекурсивно вверх по `kb_section_permissions`; 5) None → 403
  - `async def resolve_section_permission(user, section, db) → Permission | None` — аналогично для разделов (рекурсия вверх)
  - Кэш в Redis: ключ `kb_acl:{user_id}:{article_id}` TTL 5 мин; инвалидация при изменении прав
- [x] `GET /kb/sections/{id}/permissions` — список субъектов с правами (только manager раздела или admin)
- [x] `POST /kb/sections/{id}/permissions` — добавить/обновить право (`{subject_type, subject_id, subject_name, permission}`)
- [x] `DELETE /kb/sections/{id}/permissions/{subject_id}` — отозвать право
- [x] `GET /kb/articles/{id}/permissions` — список прав статьи (только если `inherit_permissions=false` или manager)
- [x] `POST /kb/articles/{id}/permissions` — добавить право на статью
- [x] `DELETE /kb/articles/{id}/permissions/{subject_id}` — отозвать право
- [x] `PATCH /kb/articles/{id}/inherit` — `{inherit_permissions: bool}`; при переключении на `false` копировать текущие права раздела как стартовую точку
- [x] `GET /kb/users/search?q=...` — поиск пользователей + групп из Keycloak Admin API для picker в UI (только editor/manager/admin)
- [x] Все существующие KB endpoints (`GET /kb/articles`, `GET /kb/articles/{id}`, `GET /kb/sections`) — пропустить через `resolve_permission`; возвращать только доступное
- [x] Файлы и медиа: проверка прав через `resolve_permission` перед `X-Accel-Redirect`
- [x] Аудит: изменения прав → `audit_log` (`event_type: kb.permission_grant / kb.permission_revoke`)

**Фронтенд — управление правами KB:**
- [x] `KbPermissionsModal.vue` — модальное окно управления правами (для раздела и статьи):
  - Список текущих субъектов с правами (аватар + имя + уровень + кнопка удалить)
  - Picker: поиск пользователей/групп (`GET /kb/users/search`) с debounce 400 мс
  - Выбор уровня: Viewer / Editor / Manager
  - Переключатель «Наследовать права от раздела» (только для статей)
- [x] `KbSectionTree.vue`: контекстное меню раздела — пункт «Управлять доступом» (только manager/admin)
- [x] `KbArticlePage.vue`: кнопка «Доступ» в шапке (только manager/admin); badge «🔒 Ограниченный доступ» если `inherit_permissions=false`
- [x] Фильтрация в `KbListPage.vue` и `KbSectionTree.vue`: показывать только разделы/статьи к которым есть хотя бы viewer-доступ
- [x] i18n ключи: `kb.permissions.*` в `ru.json` и `en.json`

**Бэкенд — переход на Markdown:**
- [x] Alembic миграция `010_kb_markdown`: `body TEXT` остаётся; добавлена таблица `kb_article_files`
- [x] Скрипт `backend/scripts/migrate_kb_html_to_md.py` — конвертация HTML→Markdown; idempotent, dry-run флаг
- [x] `KB_MEDIA_MAX_SIZE_MB`, `KB_ATTACHMENT_MAX_SIZE_MB` в `Settings` (config.py) и `.env.example`
- [x] `POST /kb/articles/{id}/media` — загрузка изображений; сохраняется в `/data/kb/media/{article_id}/`; возвращает `{url}`
- [x] `GET /kb/media/{article_id}/{filename}` — отдача медиа-файлов
- [x] `POST /kb/articles/{id}/files` — загрузка прикреплённых файлов
- [x] `GET /kb/articles/{id}/files` — список прикреплённых файлов
- [x] `DELETE /kb/articles/{id}/files/{file_id}` — удалить файл (автор или admin)
- [x] `GET /kb/files/{article_id}/{filename}` — скачивание с `Content-Disposition` RFC 5987
- [x] Аудит: загрузка медиа, скачивание файлов — в `audit_log`

**Бэкенд — экспорт:**
- [x] `GET /kb/articles/{id}/export/md` — статья как `.md` файл с YAML frontmatter
- [x] `GET /kb/sections/{id}/export/zip` — раздел как ZIP с подпапками по иерархии
- [x] `GET /kb/export/vault.zip` — вся KB как ZIP, совместимый с Obsidian vault
- [x] Временные ZIP-файлы генерируются в память (io.BytesIO)

**Бэкенд — импорт:**
- [x] `POST /kb/articles/import` — принимает `.md` файл; парсит YAML frontmatter; создаёт/обновляет статью
- [x] `POST /kb/import/vault` — принимает ZIP (Obsidian vault); `?strategy=skip|overwrite|create_new`
- [x] Отчёт импорта: `{created, updated, skipped, errors}`

**Бэкенд — diff версий:**
- [x] `GET /kb/articles/{id}/versions/{v1}/diff/{v2}` — diff через `difflib.unified_diff`; `{hunks, stats}`

**Фронтенд — редактор:**
- [x] `RichEditor.vue`: `Markdown` extension из `tiptap-markdown`; `onUpdate` → `getMarkdown()`; `setContent` принимает Markdown
- [x] Тулбар: кнопка «Вставить изображение» → `POST /kb/articles/{id}/media` → вставляет `![alt](url)`
- [x] Drag & drop изображений в редактор
- [x] Вставка изображений из буфера обмена (`paste` event с `image/*`)

**Фронтенд — вложения:**
- [ ] `KbArticleFormPage.vue`: блок «Прикреплённые файлы» под редактором (список + кнопка + удаление) — не реализовано
- [x] `KbArticlePage.vue`: блок «Файлы» на странице просмотра через `KbAttachmentsPanel`
- [x] `KbAttachmentsPanel.vue` — переиспользуемый компонент

**Фронтенд — импорт/экспорт UI:**
- [x] `KbArticlePage.vue`: меню экспорта с пунктом «Скачать Markdown (.md)»
- [ ] `KbListPage.vue`: кнопка «Экспортировать раздел (.zip)» — не реализовано
- [ ] Страница Admin → KB: кнопка «Экспортировать всю KB» и «Импортировать из Obsidian (.zip)» — не реализовано
- [ ] Диалог импорта: drag-and-drop зона + прогресс-бар + отчёт — не реализовано

**Фронтенд — diff версий:**
- [x] `KbVersionDiffModal.vue` — модальное окно сравнения версий (unified view, green/red)
- [x] Вызывается из истории версий в `KbArticlePage.vue`
- [x] i18n ключи: `kb.diff.*`, `kb.import.*`, `kb.export.*`, `kb.files.*`, `kb.media.*` в `ru.json` и `en.json`

**Документация:**
- [x] `docs/api-contracts.md` — добавлены endpoints media, files, import, export, diff (реализовано в рамках Step 7.6)
- [x] `docs/adr.md` — ADR-018: KB хранит Markdown в PostgreSQL, файловая система только для блобов
- [ ] `docs/db-schema.md` — таблица `kb_article_files` (из миграции 010) — нужно добавить

**Тесты Phase 3.5:**

_ACL:_
- [ ] Unit: алгоритм `resolve_permission` — все ветки (admin override, создатель, inherit=true/false, рекурсия по дереву разделов, нет прав → None) (~15 тестов)
- [ ] Unit: инвалидация Redis-кэша при изменении прав
- [ ] Integration: viewer не видит раздел в `GET /kb/sections`; editor видит и может редактировать; manager может менять права; portal admin видит всё
- [ ] Integration: статья с `inherit_permissions=false` → права раздела не применяются
- [ ] Integration: файл статьи недоступен пользователю без прав на статью → 403
- [ ] E2E: ivanov создаёт раздел → приглашает petrov как viewer → petrov видит раздел; sidorov не видит
- [ ] E2E: статья с отключённым наследованием → petrov теряет доступ → видит 403

_Markdown + медиа + импорт/экспорт:_
- [ ] Unit: YAML frontmatter parse/generate, ZIP структура, `difflib` hunks, file size validation (15+ тестов)
- [ ] Integration: media upload → X-Accel-Redirect → файл отдан; без прав → 403
- [ ] Integration: file upload → download с оригинальным именем; vault ZIP import → секции + статьи созданы с правами создателя
- [ ] E2E: создать статью → вставить изображение → сохранить → изображение отображается при просмотре
- [ ] E2E: экспорт статьи в MD → импорт обратно → содержимое и теги совпадают
- [ ] E2E: загрузить Obsidian vault ZIP → статьи появились с правильной структурой разделов

### [x] Step 8: Phase 4 — Email уведомления + In-app уведомления
_ТЗ: §3.12 Уведомления_

> Обе части реализуются вместе — in-app SSE нужна для Phase 1/2/3 (новости, правки статей), отдельно от email не имеет смысла.

- [x] Таблица `notifications` (Alembic миграция `012_notifications`)
- [x] `GET /notifications` — список непрочитанных (пагинация)
- [x] `POST /notifications/{id}/read`, `POST /notifications/read-all`
- [x] `DELETE /notifications/{id}` — удаление уведомления
- [x] `GET /notifications/unread-count` — счётчик непрочитанных
- [x] **In-app SSE:** `GET /notifications/stream` через Redis Streams (`XADD`/`XREAD`)
  - `Last-Event-ID` для event replay при реконнекте
  - Bell-icon в шапке со счётчиком непрочитанных (`NotificationsDropdown.vue`)
  - SSE подключается в `AppLayout.vue` → `onMounted` / отключается в `onBeforeUnmount`
  - Автореконнект через 5 сек при разрыве соединения
- [x] **Email:** aiosmtplib + Postfix; ARQ tasks с retry
  - Шаблоны писем: новость опубликована, правка одобрена/отклонена
- [x] Настройки уведомлений в профиле: `notify_email`, `notify_inapp` (поля в `users`)
- [x] Отправка уведомлений при: публикации новости (ARQ hook), одобрении/отклонении правки KB
- [x] `notify_suggestion_reviewed()` вызывается из `review_suggestion` в `kb.py`
- [x] Pinia store `useNotificationsStore`: `items`, `unreadCount`, `hasUnread`, SSE управление
- [x] i18n ключи `notifications.*` в `ru.json` и `en.json`
- [x] ARQ worker: `notify_news_published`, `notify_suggestion_reviewed_email` зарегистрированы

**Тесты Phase 4:**
- [x] Unit: SSE payload (stream key format), email рендеринг (HTML+text), таргетинг получателей, `get_unread_count`, `notify_suggestion_reviewed`, `notify_users_news_published` (16 тестов в `test_notifications.py`)
- [ ] Integration: Redis Streams pub/sub, aiosmtplib mock — запускается с Docker
- [ ] E2E: опубликовать новость → SSE уведомление появилось в bell icon — запускается с Docker

### [x] Step 8.1: Phase Admin-UI — Runtime-настройки через интерфейс
_Добавлено постфактум: перенос инфраструктурных настроек из `.env` в Admin UI с применением без рестарта._

**Backend:**
- [x] `backend/app/api/system_settings.py` — `GET/PUT /admin/system/settings` с персистом в `/data/settings/system.json` (TTL-кэш 60 сек); автогенерация Nginx `limits.conf`/`allowlist.conf` + триггер `reload-trigger`; валидация `allowed_cidr` через `ipaddress.ip_network()` → 422 без сохранения и без reload'а
- [x] `POST /admin/system/nginx/reload` — принудительная перегенерация конфигов и reload
- [x] `GET /admin/system/tls/status`, `POST/DELETE /admin/system/tls/cert`, `POST/DELETE /admin/system/tls/key` — управление TLS-сертификатом в `/data/certs/`; автотриггер reload после загрузки
- [x] Динамическое переключение `log_level` без рестарта через `app.core.logging.set_log_level()`
- [x] `backend/app/api/keycloak_admin.py` — `GET/PUT /admin/keycloak/settings` с секретами в `/data/secrets/keycloak-settings.json` (`chmod 0600`); автомиграция из legacy `/data/branding/keycloak-settings.json`; маска `*_secret_set: bool` в GET; единая семантика `null`/`"***"`/`""`/value для секретов; `POST /admin/keycloak/test/oidc`, `POST /admin/keycloak/test/sync`, `GET /admin/keycloak/sync/status`, `POST /admin/users/sync`
- [x] `app/services/keycloak.py` — публичный helper `invalidate_settings_cache()`, читает оба пути (новый и legacy)
- [x] `backend/app/api/branding.py` — `GET/PUT /admin/branding/email/settings` + `POST /admin/branding/email/test`; SMTP-конфиг в `/data/branding/email-settings.json`; маска `password_set: bool`, семантика `null/"***"/""/value` для пароля; `_load_email_settings()` возвращает default-объект при отсутствии файла (фикс `AttributeError` после миграции моделей)
- [x] `app/worker/tasks/notifications.py::_get_smtp_config()` — читает email-settings.json на каждый send, изменения применяются к следующему письму без рестарта
- [x] Nginx entrypoint — опрос `/data/nginx/reload-trigger` + `nginx -s reload` без рестарта контейнера
- [x] Nginx healthcheck + `GET /health` на порту 80 (docker-compose healthcheck)
- [x] `/data/secrets/` — отдельный volume `./secrets_data:/data/secrets` с правами 0600 на файлы
- [x] Keycloak sync client — отдельный сервисный аккаунт с ролью `realm-management → view-users`, ARQ cron каждый час
- [x] `.env.example` — выкинуты Nextcloud/TLS/limits/log_level/keycloak-секреты, добавлен комментарий о переносе в Admin UI; оставлены только bootstrap-секреты

**Frontend (`AdminPage.vue`):**
- [x] Вкладка «Система»: форма `SystemSettings` (Nextcloud URL, NC password, CIDR, лимиты, log_level, флаги) + кнопки «Сохранить», «Перезагрузить Nginx», блок TLS (upload cert/key, status, срок действия, delete)
- [x] Вкладка «Keycloak»: форма (URL/realm/oidc_client_id/secret + sync_client_id/secret) + кнопки «Проверить OIDC», «Проверить sync», «Запустить синхронизацию», блок «Статус последней синхронизации»; маскировка `*_secret` при загрузке; clearing `sync_client_id` также очищает secret
- [x] Вкладка «Email»: форма SMTP (host/port/from/username/password/tls/starttls) + кнопка «Отправить тестовое письмо» с модалкой ввода получателя
- [x] Исправлен порядок секций хинтов в Keycloak-форме (actual test-flow)
- [x] i18n ключи: `admin.tabs.*`, `admin.system.*`, `admin.keycloak.*`, `admin.email.*` в `ru.json`/`en.json`

**Документация:**
- [x] `docs/api-contracts.md` — добавлены endpoints email, уточнён путь Keycloak secrets (`/data/secrets/`), добавлено замечание о валидации CIDR
- [x] `docs/adr.md` ADR-020 — Email row, секция о `/data/secrets/` и legacy-миграции, семантика секретов, валидация CIDR, новый volume `secrets_data`
- [x] `docs/roles-matrix.md` — новые матрицы «Системные настройки» и «Настройки Keycloak», строки email в матрице Branding
- [x] `requirements.md` — секция 3.X «Runtime-настройки через Admin UI», статусы Phase 3/4/Admin-UI обновлены до ✅

**P0/P1 фиксы по итогам ревью:**
- [x] Падение при чистом старте без `email-settings.json` (ранее обращение к удалённым `s.smtp_*` полям) → `_load_email_settings()` возвращает default
- [x] Невалидный CIDR приводил к падению Nginx при reload → `field_validator` через `ipaddress.ip_network()` отвергает 422 до записи
- [x] Keycloak secrets лежали в `/data/branding/` рядом с публичными медиа → перенос в `/data/secrets/` с `chmod 0600` и автомиграцией legacy-файла
- [x] Сигнал «отключить sync-клиент» не очищал secret → при `sync_client_id=""` фронт шлёт `sync_client_secret=""`
- [x] Infinite loop в `sync_users_from_keycloak` при багованной Keycloak-пагинации → guard `max_pages=1000`
- [x] Прямой доступ к `_settings_cache` из admin handler'ов → публичный `invalidate_settings_cache()`

### [x] Step 8.5: Phase 4.5 — Фотогалерея (Immich)
_Детальный план: `docs/immich-integration.md`_

> Разворачивается после уведомлений (SSE/email уже есть). Immich — self-hosted Google Photos, AGPL-3.0, нативная поддержка Keycloak OIDC.
> Используется последняя стабильная версия (`IMMICH_VERSION=release`).

**Уточнения по итогам обсуждения:**
- `immich-machine-learning` — optional, через `profiles: [ml]` (можно подключить позже)
- Отдельный `immich-postgres` (pgvecto-rs) — отдельный инстанс, своя БД
- `IMMICH_CORP_ALBUM_ID` — ручная настройка после первого запуска (ок)
- Graceful fallback: виджет скрывается, если Immich не настроен (`{"configured": false}`)
- Disk-кэш для thumbnail'ов: `/data/cache/immich/` + Redis TTL 1 ч
- `immich_widget_limit` (кол-во фото в виджете) — в Admin UI → **Модули** (не Система)
- `SSO autoLaunch` у ярлыка — настраиваемо через поле `url` ярлыка в Admin UI
- Wildcard TLS / DNS-запись `photos.portal.company.local` — уже есть на инфраструктуре

**Инфраструктура:**
- [x] Добавить сервисы `immich-server`, `immich-postgres`, `immich-redis` в `docker-compose.yml`
- [x] `immich-machine-learning` как optional — `profiles: [ml]`
- [x] Volume `immich_upload_data`, `immich_pg_data`, `immich_cache_data`
- [x] Nginx: отдельный server block `photos.portal.company.local` → `immich-server:2283`
- [x] Переменные окружения: `IMMICH_VERSION`, `IMMICH_UPLOAD_LOCATION`, `IMMICH_DB_PASSWORD`, `IMMICH_URL`, `IMMICH_PUBLIC_URL`, `IMMICH_API_KEY`, `IMMICH_CORP_ALBUM_ID`

**SSO (Keycloak ↔ Immich):**
- [ ] Новый клиент `immich` в Keycloak Realm (Confidential, OIDC, Redirect URIs на `/auth/login` и `/user-settings`)
- [ ] Mapper `immich_role` → claim для разграничения admin/user
- [ ] Настройка OAuth в Immich Admin Settings: Issuer URL, Client ID/Secret, Auto Register=true
- [ ] Smoke-test SSO: пользователь кликает ярлык → оказывается в Immich без повторного логина

**Данные / настройка (ручные шаги после деплоя):**
- [ ] Создать корпоративный shared-альбом в Immich UI после первого запуска
- [ ] Получить UUID альбома → ввести в Admin UI → Модули → Фотогалерея (Corp Album UUID)
- [ ] Создать сервисный API-ключ (Administration → API Keys) → ввести в Admin UI → Модули → Фотогалерея (API Key)
- [ ] INSERT ярлыка "Фотогалерея" в `service_links` через Admin UI с `supports_sso=true`

**Backend:**
- [x] `backend/app/api/photos.py`: `GET /api/v1/photos/recent` — возвращает `{"configured": false}` если ключи не заданы; иначе последние N фото из корп. альбома через Immich API
- [x] `GET /api/v1/photos/thumbnail/{asset_id}` — прокси thumbnail: disk-кэш `/data/cache/immich/` + Redis TTL 1 ч; `Cache-Control: public, max-age=3600`
- [x] `backend/app/api/modules.py` — `GET/PUT /admin/modules/immich` с маскированными секретами, хранение в `/data/settings/modules.json`
- [x] `photos.py` переведён на `load_modules().immich` (больше не читает env напрямую)
- [x] Регистрация роутера в `main.py`

**Frontend:**
- [x] `src/components/widgets/PhotosWidget.vue` — сетка 4×2 превью, skeleton loader, ссылка "Все фото →"; виджет скрыт при `configured=false`
- [x] Виджет размещён на HomePage в боковой колонке
- [x] i18n ключи: `photos.title`, `photos.see_all`, `photos.empty`, `photos.notConfigured` в `ru.json` и `en.json`

**Admin UI:**
- [x] Вкладка «Модули» → секция «Фотогалерея (Immich)»: toggle включения, URL, API-ключ, Album UUID, widget_limit

**Тесты:**
- [x] Unit: `test_photos.py` — сортировка фото по дате, прокси thumbnail → Cache-Control header, 401 без авторизации, `configured=false` когда настройки пусты, лимит из system.json (12+ тестов)
- [ ] Integration: httpx mock Immich API (GET album, GET thumbnail) — запускается с Docker
- [ ] E2E: виджет отображается на главной → клик по фото → открывается Immich в новой вкладке — запускается с Docker

### [x] Step 8.6: Phase 4.6 — Видеогалерея (PeerTube)
_Детальный план: `docs/peertube-integration.md`_

> PeerTube уже установлен. Фокус на SSO через OIDC-плагин, виджет видео на главной, iframe embed в статьях/новостях.

**SSO (Keycloak ↔ PeerTube через плагин) — ручные шаги после деплоя:**
- [ ] Установить плагин `peertube-plugin-auth-openid-connect` (Admin → Plugins или CLI)
- [ ] Новый клиент `peertube` в Keycloak (Confidential, OIDC, Redirect URI на `/plugins/auth-openid-connect/*/router/code-cb`)
- [ ] Mapper `peertube_role` → claim (editor/admin → `moderator`, остальные → `user`)
- [ ] Настройка плагина: Discovery URL, Client ID/Secret, username/mail/role claims, Button text
- [ ] Отключить локальную регистрацию в PeerTube (только SSO)
- [ ] Privacy по умолчанию: `Internal` (только залогиненные)
- [ ] Smoke-test SSO: переход из портала → PeerTube без повторного логина

**Данные / настройка — ручные шаги:**
- [ ] Создать сервисный аккаунт `portal-svc` (Role: User) для API-запросов виджета
- [ ] `curl /api/v1/oauth-clients/local` → ввести `client_id`/`client_secret` в Admin UI → Модули → Видеопортал
- [ ] Ввести логин/пароль `portal-svc` в Admin UI → Модули → Видеопортал
- [ ] Создать корпоративные каналы: `corporate`, `training`, `demos`
- [ ] INSERT ярлыка "Видеопортал" в `service_links` через Admin UI с `supports_sso=true`

**Backend:**
- [x] `backend/app/api/videos.py`: `GET /api/v1/videos/recent` (graceful fallback) + `GET /api/v1/videos/config`
- [x] `GET /api/v1/videos/thumbnail/{uuid}` — прокси thumbnail с disk-кэшем `/data/cache/peertube/`
- [x] Кэширование OAuth2 токена в памяти (TTL = `expires_in - 60`)
- [x] `Settings`: `PEERTUBE_URL`, `PEERTUBE_PUBLIC_URL`, `PEERTUBE_CLIENT_ID`, `PEERTUBE_CLIENT_SECRET`, `PEERTUBE_SVC_USERNAME`, `PEERTUBE_SVC_PASSWORD`, `PEERTUBE_CHANNEL_ID`
- [x] `peertube_widget_limit` управляется через Admin UI → Модули → Видеопортал (default 6)
- [x] Регистрация роутера в `main.py`

**Frontend — виджет:**
- [x] `src/components/widgets/VideosWidget.vue` — сетка 3×2, thumbnail 16:9, badge длительности, skeleton loader; скрыт при `configured=false`
- [x] Виджет размещён на `HomePage` после `PhotosWidget`
- [x] i18n ключи: `videos.title`, `videos.see_all`, `videos.empty` в `ru.json`/`en.json`

**Frontend — iframe embed в TipTap:**
- [x] `src/components/editor/extensions/IframeEmbed.ts` — TipTap Node с whitelist доменов (configurable per instance)
- [x] Зарегистрирован в `RichEditor.vue` через `allowedIframeOrigins` prop
- [x] Кнопка "Вставить видео" в тулбаре редактора (диалог с URL)
- [x] `sanitize.ts`: `sanitizeHtmlAllowIframe(html, origins)` — DOMPurify hook разрешает `<iframe>` только с whitelist доменов
- [x] Pinia store `useVideosStore` — кэширует `configured` и `peertubeOrigin`

**Admin UI:**
- [x] Вкладка «Модули» → секция «Видеопортал (PeerTube)»: toggle, URL, OAuth2 credentials, сервисный аккаунт, channel ID, widget_limit

**Nginx / CSP:**
- [x] CSP header: `frame-src 'self' https://video.company.local` и `media-src 'self' https://video.company.local`
- [x] Nginx server block для `video.company.local` → `peertube:9000`

**Тесты:**
- [x] Unit: `_is_configured` (все ветки), `_thumb_cache_path`, `get_videos_config`, `get_recent_videos`, thumbnail proxy cache hit/miss, token cache (17 тестов в `test_videos.py`)
- [ ] Integration: httpx mock PeerTube API (token + videos), thumbnail proxy — запускается с Docker
- [ ] E2E: виджет видео на главной → клик → PeerTube в новой вкладке — запускается с Docker
- [ ] E2E: editor вставляет iframe embed в статью → iframe отображается при просмотре — запускается с Docker

### [x] Step 8.7: Admin UI — вкладка «Модули» (Immich/PeerTube/Nextcloud)
_Добавлено по запросу пользователя: вынести настройки Immich и PeerTube из env в Admin UI._

- [x] `backend/app/api/modules.py` — `GET /admin/modules`, `PUT /admin/modules/immich`, `PUT /admin/modules/peertube`, `PUT /admin/modules/nextcloud`; хранение в `/data/settings/modules.json` (chmod 0600); TTL-кэш 60 сек; env-fallback при первом запуске; маскированные секреты
- [x] `photos.py`, `videos.py` переведены на `load_modules()` — больше не читают env напрямую
- [x] Удалены `immich_widget_limit` и `peertube_widget_limit` из `system_settings.py`
- [x] `AdminPage.vue` — новая вкладка «Модули»: per-module toggle + поля настроек; секреты: null = оставить, "" = очистить
- [x] i18n: `admin.modules.*` в `ru.json` и `en.json`
- [x] `.env` — добавлен `IMMICH_DB_PASSWORD` (единственная env-переменная Immich, остальное в UI)

### [x] Step 8.8: Синхронизация документации — Immich/PeerTube/Modules
_Добавлено по запросу пользователя после завершения блоков интеграции._

- [x] `docs/api-contracts.md` — добавлены разделы «Фотогалерея (Immich)», «Видеопортал (PeerTube)», «Модули (Admin UI)»; endpoints, примеры запросов/ответов, описание disk-кэша, graceful fallback, семантика секретов
- [x] `docs/roles-matrix.md` — добавлены матрицы «Фотогалерея (Immich)», «Видеопортал (PeerTube)», «Модули (Admin UI)»
- [x] `docs/adr.md` — добавлены ADR-026 (Immich), ADR-027 (PeerTube + IframeEmbed + DOMPurify), ADR-028 (Modules Admin UI pattern, env-fallback, расширяемость)
- [x] Удалены устаревшие файлы `docs/phase-0.md` и `docs/review-pre-phase-4.md`

### [ ] Step 9: Phase 5 — Файлы через Nextcloud
_ТЗ: §3.6 Интеграция Nextcloud + Collabora_
_⛔ **ЗАБЛОКИРОВАН** до получения от инженера: значения `NC_USER_ID_FIELD` + успешного smoke-теста Bearer к WebDAV_

**Предварительное условие (выполняет инженер):**
- [ ] Миграция Nextcloud: AD/LDAP → Keycloak OIDC (`user_oidc` app ≥ 1.3)
- [ ] Smoke-test Bearer: `curl -X PROPFIND -H "Authorization: Bearer $TOKEN" .../dav/files/testuser/` → 207
- [ ] Зафиксировать `NC_USER_ID_FIELD=preferred_username|sub` в `.env`
- [ ] Настройка Audience mapper в Keycloak: `aud: [portal, nextcloud]`

**Реализация (после разблокировки):**
- [ ] `NextcloudClient` в `backend/app/services/nextcloud.py` — streaming upload/download, impersonation
- [ ] `GET /files?path=...` — WebDAV PROPFIND → JSON листинг папки
- [ ] `GET /files/{path}/download` — WebDAV streaming → StreamingResponse
- [ ] `GET /files/{path}/open` — PDF inline / Office → URL Nextcloud/Collabora (новая вкладка)
- [ ] `POST /files/upload` — multipart → WebDAV PUT (streaming, MAX_UPLOAD_SIZE_MB)
- [ ] `POST /files/{path}/share` — OCS Sharing API (внутренние ссылки, TTL)
- [ ] Встроенный просмотр PDF: `<iframe>` в модалке
- [ ] Обработка 403/404 от Nextcloud → порталу возвращает соответствующий статус
- [ ] Аудит всех файловых операций в `audit_log`

**Тесты Phase 5:**
- [ ] Unit: парсинг WebDAV XML, формирование WebDAV-путей, таймауты
- [ ] Integration: httpx mock Nextcloud WebDAV + OCS API
- [ ] E2E (ACL): пользователь Marketing → `/Finance/salaries.xlsx` → 403
- [ ] E2E (ACL): пользователь Finance → тот же файл → 200, скачивается
- [ ] E2E: audit trail — скачал файл → в `audit_log` имя пользователя, не `portal-svc`
- [ ] E2E: после 20 мин неактивности → автоматический refresh NC-токена → листинг работает

### [ ] Step 10: Аудит, Аналитика, Observability
_ТЗ: §3.8 Аналитика, §3.11 Аудит, §7 Observability_
> Аудит частично уже пишется в каждой фазе (fire-and-forget). Здесь — дашборд и финальная обвязка.

- [ ] ARQ batch INSERT из Redis `audit_queue` → `audit_log` каждые 1-2 сек
- [ ] ARQ cron: `create_next_audit_partition` (1-е число месяца), `drop_old_audit_partition` (retention 12 мес)
- [ ] `GET /audit` + `GET /audit/export.csv` — интерфейс просмотра для admin
- [ ] `GET /analytics/dashboard`, `/top-articles`, `/top-files`, `/departments`
- [ ] Prometheus: кастомные метрики (SSE connections, audit queue depth, ARQ jobs)
- [ ] Grafana алерты (настраиваются вне портала)

### [x] Step 10.5: Комплексное ревью после Admin-UI/Branding/Notifications/KB Markdown
_Добавлено по запросу пользователя: ревью всех коммитов, выходящих за исходное ТЗ, исправление проблем и синхронизация документации._

**Результаты ревью (3 параллельных субагента):**
- [x] Проверены коммиты Phase 3/3.5/4/Admin-UI/Branding — все выходят за исходное ТЗ, но покрыты пост-хок шагами 6.5/6.7/6.8/7/7.5/8/8.1
- [x] Выявлены P0/P1 проблемы в Admin-UI подсистеме (runtime-настройки, TLS, Keycloak, email, SSE)

**P0/P1 фиксы применены:**
- [x] docker-compose volumes: `secrets_data:/data/secrets`, `kb_data:/data/kb` — добавлены в backend/worker; `.gitignore` покрывает новые каталоги
- [x] CSRF origin strict-match: `urlparse` + сравнение scheme + netloc (защита от `portal.company.local.evil.com` и `http://`↔`https://` подмены)
- [x] Bootstrap admin: новый флаг `admin_password_reset_on_start` — пароль перезаписывается только при явной установке; иначе UI-изменения пароля сохраняются
- [x] TLS private key: строгий whitelist PEM-заголовков (`-----BEGIN PRIVATE KEY-----`, RSA/EC/DSA/OPENSSH/ENCRYPTED) — защита от загрузки сертификата/CSR как ключа
- [x] `system.json` и `email-settings.json`: `chmod 0600` при сохранении (защита секретов)
- [x] Email-шаблоны: HTML-escape (`_html.escape(quote=True)`) всех интерполируемых значений в worker/notifications.py и branding `_send_test_email` (`sender_name`, `host`, `portal_name`, `news_title`, `article_title`, ссылки)
- [x] Keycloak URL SSRF guard: `_validate_keycloak_url()` — отвергает non-http(s), пустой host, loopback/link-local/multicast, AWS metadata `169.254.169.254`; применён в PUT `/admin/keycloak/settings` и обоих test-endpoints
- [x] SSE per-user connection limit: Redis sorted set (`sse:conn:{user_id}`) с `ZREMRANGEBYSCORE`+`ZCARD`+`ZADD`, max 5/user, TTL 60s, 429 при превышении, очистка в `finally` по `connection_id`
- [x] Frontend: `uploadTlsFile` переведён с raw `fetch()` на `apiUpload` (CSRF-токен теперь прикладывается)
- [x] Frontend fail-open forms: `loadSystemSettings`/`loadKcSettings`/`loadEmailSettings` теперь surface ошибку через `message.error()` и устанавливают `sysLoadError`/`kcLoadError`/`emailLoadError`; соответствующие save-функции делают early-return, чтобы не перезаписать живую конфигурацию пустыми значениями
- [x] i18n ключи `loadFailedGuard` добавлены в `admin.system`, `admin.keycloak`, `admin.email` (ru/en)

### [x] Step 10.6: Ревью интеграции Immich + перенос модулей в Admin UI
_Добавлено по запросу пользователя: ревью коммитов 2744048..5948b5b (Immich + вкладка «Модули»), оценка UI/UX, обновление документации._

**Ревью кода — найденные проблемы:**
- **P1 баг**: `videos._token_cache` (глобальный OAuth-токен PeerTube) не инвалидировался при смене настроек через `PUT /admin/modules/peertube` — стейл-токен жил до `expires_in - 60` (≤ 1 ч).
- **P1**: `_save_modules` писал `modules.json` не-атомарно (`write_text` → `chmod`), оставляя race window когда файл уже виден другим процессам, но ещё с дефолтными правами.
- **P2**: Повреждённый `modules.json` молча игнорировался (`except Exception: pass`) — оператор не мог понять почему «настройки сбросились».
- **UX**: Нет кнопки «Проверить соединение» для Immich/PeerTube — асимметрично с Keycloak/SMTP, где такие кнопки есть.
- **UX**: Nextcloud-toggle активен, но функционал заблокирован до Phase 5 — оператор может ошибочно включить модуль без эффекта.

**Применённые исправления:**

_Backend (`backend/app/api/modules.py`):_
- [x] Атомарная запись `modules.json` через `tempfile.mkstemp` + `chmod 0600` на временном файле + `os.replace` (исключает race и оставляет файл только с дефолтными правами)
- [x] Логирование `modules.settings_parse_failed` при corrupted JSON (вместо `except: pass`)
- [x] Публичный helper `invalidate_modules_cache()` + приватный `_invalidate_module_caches()` — чистит `videos._token_cache`
- [x] `_save_modules` автоматически вызывает `_invalidate_module_caches()` после сохранения
- [x] `POST /admin/modules/immich/test` — `GET /api/server/about` + опционально `GET /api/albums/{corp_album_id}`; возвращает структурированный отчёт `{server_ok, version, album_ok, album_name, asset_count}`
- [x] `POST /admin/modules/peertube/test` — OAuth2 токен по сервисному аккаунту + опциональный счётчик видео; сбрасывает токен-кэш в конце

_Frontend (`frontend/src/pages/AdminPage.vue`):_
- [x] Кнопки «Проверить соединение» для Immich и PeerTube (видны только при `enabled=true`)
- [x] Блок `.module-test-result.ok/.err` с цветовой индикацией результата (зелёный/красный)
- [x] Handlers `testImmichModule()`/`testPeertubeModule()` форматируют ответ: `✓ server reachable (v1.119.0) · album «Корп.альбом» (42)`
- [x] Nextcloud toggle → `disabled` + `<n-alert type="info">` со ссылкой на Phase 5
- [x] Импорт `NAlert` из naive-ui

_i18n (`ru.json`, `en.json`):_
- [x] `admin.modules.testConnection`, `admin.modules.test.{serverOk,serverFail,albumOk,albumFail,tokenOk,tokenFail,videosTotal}`, `admin.modules.nextcloud.blockedNotice`

_Документация:_
- [x] `docs/api-contracts.md` — описаны `POST /admin/modules/immich/test` и `POST /admin/modules/peertube/test` с примерами ответов (200 ok/fail, 400 validation)
- [x] `docs/roles-matrix.md` — добавлены строки test-endpoints в матрицу «Модули (Admin UI)»; уточнены примечания PUT (atomic write + chmod 0600, сброс OAuth-кэша)
- [x] `docs/adr.md` — ADR-029: test-connection endpoints + инвалидация OAuth-кэша + atomic write

**Не сделано (вынесено в Step 11 / технический долг):**
- [x] Cleanup dead code: `modulesNextcloudSaving`, `saveNextcloudModule` в `AdminPage.vue` — удалены (подтверждено grep)
- [ ] Unit-тесты для новых test-endpoints с httpx mock
- [ ] E2E: admin сохраняет настройки → жмёт «Проверить» → видит зелёный/красный результат

### [x] Step 10.7: Удаление Immich из проекта
_Обоснование: Immich не поддерживает модель «все читают папку, некоторые грузят» без per-user настроек. Принято решение: заменить собственным модулем фотогалереи (см. Step 10.8)._

**Backend:**
- [x] Immich-прокси `photos.py` удалён/переписан под собственный модуль (Step 10.8)
- [x] `Immich*` модели и поля удалены из `modules.py` — нет следов в коде
- [x] Immich-зависимые функции удалены, cache `/data/cache/immich/` не используется

**Frontend:**
- [x] `PhotosWidget.vue` переписан под собственный модуль
- [x] Immich-секция из вкладки «Модули» в `AdminPage.vue` удалена
- [x] Immich-специфичные i18n-ключи удалены

**Infrastructure:**
- [x] `immich-server`, `immich-postgres`, `immich-redis`, `immich-machine-learning` удалены из `docker-compose.yml`
- [x] Immich volumes и переменные окружения удалены из `.env.example`

**Документация:**
- [x] `docs/immich-integration.md` удалён
- [x] Immich-секции убраны из `docs/api-contracts.md` и `docs/roles-matrix.md`
- [x] ADR-030 добавлен в `docs/adr.md`; ADR-026 помечен SUPERSEDED
- [x] `chore(photos): drop immich integration, replace with self-hosted gallery (see ADR-030)` — выполнено совместно с Step 10.8

### [x] Step 10.8: Собственный модуль фотогалереи (замена Immich)
_Замена Immich. Реализация: KB-style ACL (viewer/uploader/manager) + локальное хранение + Pillow + WebP thumbnails + X-Accel-Redirect._

- [x] Миграция `014_photos`: `photo_folders`, `photo_folder_permissions`, `photos`
- [x] Backend ACL (`services/photos_acl.py`) — резолвер с рекурсией вверх + Redis-кэш TTL 5 мин
- [x] Backend storage (`services/photos_storage.py`) — Pillow + pillow-heif, WebP 200/600/1600, EXIF strip GPS, path-traversal guard
- [x] Backend API (`app/api/photos.py`) — folders CRUD, photos upload/list/delete, permissions, thumbnail/original via X-Accel-Redirect, recent
- [x] Pydantic-схемы (`schemas/photos.py`)
- [x] SQLAlchemy-модели (`models/photos.py`)
- [x] ARQ-задача `process_photo_upload` для thumbnails + EXIF
- [x] Admin UI: `PUT /admin/modules/photos` (`PhotosModuleSettings/Out/In` в `modules.py`)
- [x] Frontend API-клиент `api/photos.ts`, Pinia store `stores/photos.ts`
- [x] Виджет `PhotosWidget.vue` на главной
- [x] Страница `/photos` (`PhotosIndexPage.vue` + `FolderNode.vue`) — дерево + grid + lightbox + upload + permissions
- [x] AdminPage вкладка «Модули» — секция «Фотогалерея»
- [x] i18n: `photos.*` + `admin.modules.photos.*` + `common.loadMore` (ru + en)
- [x] docker-compose volumes: `photos_originals_data` (backend/worker rw, nginx ro), `photos_thumbs_data`
- [x] Nginx internal locations `/internal/photos-thumbs/` (cache 7d) и `/internal/photos-originals/` (no-store)
- [x] `.gitignore`: `photos_originals_data/`, `photos_thumbs_data/`
- [x] Backend Dockerfile: `Pillow>=10.3`, `pillow-heif>=0.16` + системные `libheif1/libde265-0/libjpeg62-turbo/zlib1g/libwebp7`
- [x] ADR-031 — архитектура модуля
- [x] Полная чистка упоминаний Immich: `.env.example`, `docs/adr.md` (header + удалён ADR-026 + правки в ADR-028/030), `docs/api-contracts.md` (header), `docs/roles-matrix.md` (header), `backend/app/api/photos.py` (docstring)
- [x] `docs/api-contracts.md` — секция «Фотогалерея (собственный модуль)» + `PUT /admin/modules/photos` + photos в `GET /admin/modules`
- [x] `docs/roles-matrix.md` — матрица «Фотогалерея (собственный модуль)» + строка `PUT /admin/modules/photos`
- [x] `docs/db-schema.md` — секция «Фотогалерея (миграция 014_photos)» с таблицами `photo_folders`, `photo_folder_permissions`, `photos`; обновлена цепочка миграций до `014_photos`

### [x] Step 10.9: Lightbox UX — скачать, поделиться, повернуть, приблизить
_Добавлено по запросу пользователя: расширение лайтбокса фотогалереи + публичный шаринг по токену._

**Backend:**
- [x] Миграция `015_photo_share_tokens` (`photo_share_tokens`: id, photo_id FK, token unique, created_by, created_at, expires_at, revoked_at)
- [x] Модель `PhotoShareToken` (`backend/app/models/photos.py`) + индексы
- [x] Pydantic схемы `ShareLinkRequest` / `ShareLinkPublic` (`backend/app/schemas/photos.py`)
- [x] `GET /photos/original/{id}?download=0|1` — параметр для `attachment` (RFC 5987 имя из `original_name`)
- [x] `POST /photos/{id}/share` (`uploader+`): `secrets.token_urlsafe(32)`, `expires_in_days` 1..365 или null; audit `photos.share_created`
- [x] `_resolve_token()` helper: 404 при revoked/missing, 410 при expired
- [x] `GET /photos/public/{token}/info` — без auth, `uploaded_by` не отдаётся
- [x] `GET /photos/public/{token}/thumbnail/{200|600|1600}` — синхронный fallback `_ensure_thumb()` + X-Accel-Redirect
- [x] `GET /photos/public/{token}/file?download=0|1` — публичный оригинал
- [x] Helpers `_content_disposition()` (RFC 5987) и `_serve_original_response()` — переиспользуются в auth/public ветках

**Frontend:**
- [x] `api/photos.ts`: `originalUrl(id, download)`, `createShareLink(photoId, expiresInDays)`, `publicPhotoInfoUrl/ThumbUrl/FileUrl`
- [x] Лайтбокс (`PhotosIndexPage.vue`): toolbar с zoom (±, wheel, 25%..800%), rotate (⟲/⟳), reset, download, copy in-portal link, create share link
- [x] Модалка «Создать публичную ссылку» с TTL select (1/7/30/90 дн или бессрочно), копирование с fallback на `execCommand('copy')`
- [x] Авто-открытие лайтбокса при `?folder=...&photo=...` (deep link)
- [x] Сброс zoom/rotation при переходе между фото (prev/next/open/close)
- [x] Публичная страница `/p/:token` (`PublicPhotoPage.vue`) — без auth, портальное название из branding store, тулбар с zoom/rotate/download
- [x] Маршрут `/p/:token` зарегистрирован в `router.ts` (`requiresAuth: false`, `public: true`)
- [x] i18n ключи `photos.lightbox.{download,copyLink,copied,createShareLink,shareLinkCreated,expiresIn,expires{1d,7d,30d,90d,Never},generate,rotate,rotateRight,zoomIn,zoomOut,reset}` + `photos.public.{expired,notFound}` + `common.{copy,prev,next}` (ru + en)

**Документация:**
- [x] `docs/api-contracts.md` — секции `POST /photos/{id}/share`, `GET /photos/public/{token}/info|thumbnail|file`, расширенный `?download` параметр для `/original/{id}`
- [x] `docs/roles-matrix.md` — строки share + 3 public endpoints в матрице фотогалереи
- [x] `docs/db-schema.md` — таблица `photo_share_tokens` (миграция 015) с алгоритмом resolve

### [x] Step 10.10: Зеркалирование структуры портальных папок на диске
_Запрос пользователя: при создании папки на портале каталог на диске должен называться так же (с поддержкой кириллицы), а не сваливаться в `originals/folder` после ASCII-санитайза._

**Backend:**
- [x] Миграция `016_photo_folders_fs_path` — добавлен `photo_folders.fs_path VARCHAR(2000) NOT NULL DEFAULT ''`; data-step заполняет fs_path обходом дерева с `sanitize_folder_name`; миграция файловой системы (rename slug-каталогов в Unicode-имена через shutil.move)
- [x] `models/photos.py` — поле `PhotoFolder.fs_path`
- [x] `services/photos_storage.py` — `sanitize_folder_name()` (NFC + удаление OS-reserved/control-символов, сохраняет кириллицу/пробелы); `folder_fs_path()` теперь интерпретирует аргумент как Unicode fs_path; `rename_folder_dir()` для физического переноса каталога
- [x] `api/photos.py::create_folder` — вычисление fs_path с проверкой коллизий sibling-имён, mkdir каталога после INSERT
- [x] `api/photos.py::update_folder` — при rename: пересчёт fs_path, каскадный UPDATE префикса для всех потомков (LIKE с escape `\_`/`\%`), физический shutil.move каталога
- [x] `api/photos.py::upload_photos` — оригиналы пишутся в `folder.fs_path`
- [x] `api/photos.py::_serve_original_response` — X-Accel-Redirect использует `urllib.parse.quote(fs_path, safe='/')` для корректной отдачи Unicode-путей
- [x] `api/photos.py::_ensure_thumb`, `get_thumbnail` — fallback-генерация читает оригинал из `folder.fs_path`
- [x] `worker/tasks/photos.py::process_photo_upload`, `cleanup_deleted_photos` — используют `folder.fs_path`

### [x] Step 10.11: Улучшения фотогалереи (image_upgrade.md)
_Реализованы 2 коммитами: `2279282` (Phase 1) и `c9e329f` (Phase 2)._

**Phase 1 — реализовано:**
- [x] №1 Перемещение папок drag-and-drop в дереве (HTML5 D&D, PATCH parent_id)
- [x] №2 Bulk-операции: мультивыбор → переместить / удалить
- [x] №3 Скачать папку ZIP — ARQ задача + статус-бар с polling + автостарт загрузки
- [x] №4 Импорт дерева с диска (`/data/photos/import/` → сканировать → ARQ thumbnails)
- [x] №5 Корзина (Trash) — 30 дней, кнопка восстановить (⏸️ FTP watch-mode отложен)
- [x] №6 Восстановление soft-deleted папок
- [x] №9 Фильтры в папке: дата, размер, MIME-тип
- [x] №10 Сортировка по taken_at
- [x] №11 Хлебные крошки в lightbox
- [x] №12 Keyboard navigation: ←/→, Esc, Home/End, Space=zoom
- [x] №16 Background ARQ: detect_missing_thumbnails (cron раз в сутки)
- [x] №22 Cover photo в дереве папок (миниатюра вместо иконки)
- [x] №23 Описания папок (inline edit в шапке)
- [x] №24 Slideshow-режим в lightbox (5/10/30 сек)
- [x] №25 Drag-and-drop загрузка файлов из Проводника на grid
- [x] №26 Прогресс-бар на multi-upload (per-file + общий)
- [x] №31 Storage usage per folder в Admin UI

**Phase 2 — реализовано:**
- [x] №8 Теги для фото (таблицы photo_tags + photo_tag_assignments, миграция 018, облако в боковой панели)
- [x] №13 AVIF thumbnails дополнительно к WebP
- [x] №14 Адаптивные размеры: 400 и 1000 + `<picture srcset>`
- [x] №15 Lazy thumbnail regeneration при запросе
- [x] №19 Публичная ссылка на папку — galleria-page без auth (миграция 019, `PublicFolderPage.vue`)
- [x] №20 QR-код для shared link (Google Charts API)
- [x] №21 Управление active share-токенами: список + revoke (`MySharesPage.vue`)

**Отложено:**
- ⏸️ №5 FTP watch-mode — требует отдельный FTP-сервис
- ⏸️ №15+16 Виртуализация grid + infinite scroll — нужен фиксированный размер карточки

### [ ] Step 11: Финальное тестирование и поставка
_ТЗ: §8 Тестирование, §9 Поставка_

- [ ] Security: OWASP ZAP — XSS, CSRF, доступ без VPN, обход SSO
- [ ] Performance: k6 — 300 одновременных сессий, p95 < 2 сек, поиск < 1 сек
- [ ] E2E coverage ≥ 90% ключевых путей (все 11 сценариев из §8.4)
- [ ] OpenAPI спецификация (`/docs` FastAPI → экспорт)
- [ ] Инструкция: Keycloak ↔ Nextcloud ↔ Портал
- [ ] Гайд администратора + пользователя
- [ ] Отчёт о тестировании с логами прогонов
- [ ] `docker-compose.yml` финальный + `docker-compose.staging.yml`
