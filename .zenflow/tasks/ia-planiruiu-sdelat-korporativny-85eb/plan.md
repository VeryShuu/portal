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
- [ ] Alembic миграция `009_kb_acl`:
  - Таблица `kb_section_permissions` (`id`, `section_id` FK, `subject_type` CHECK('user','group'), `subject_id` varchar(255), `subject_name` varchar(255), `permission` CHECK('viewer','editor','manager'), `granted_by` FK users, `created_at`)
  - Таблица `kb_article_permissions` (аналогично, `article_id` вместо `section_id`)
  - `ALTER TABLE kb_articles ADD COLUMN inherit_permissions BOOLEAN NOT NULL DEFAULT TRUE`
  - Индексы: `(section_id, subject_id)`, `(article_id, subject_id)`
- [ ] `backend/app/services/kb_acl.py` — сервис проверки прав:
  - `async def resolve_permission(user, article, db) → Permission | None` — алгоритм: 1) portal admin → full; 2) создатель → manager; 3) `inherit_permissions=false` → `kb_article_permissions`; 4) `inherit_permissions=true` → рекурсивно вверх по `kb_section_permissions`; 5) None → 403
  - `async def resolve_section_permission(user, section, db) → Permission | None` — аналогично для разделов (рекурсия вверх)
  - Кэш в Redis: ключ `kb_acl:{user_id}:{article_id}` TTL 5 мин; инвалидация при изменении прав
- [ ] `GET /kb/sections/{id}/permissions` — список субъектов с правами (только manager раздела или admin)
- [ ] `POST /kb/sections/{id}/permissions` — добавить/обновить право (`{subject_type, subject_id, subject_name, permission}`)
- [ ] `DELETE /kb/sections/{id}/permissions/{subject_id}` — отозвать право
- [ ] `GET /kb/articles/{id}/permissions` — список прав статьи (только если `inherit_permissions=false` или manager)
- [ ] `POST /kb/articles/{id}/permissions` — добавить право на статью
- [ ] `DELETE /kb/articles/{id}/permissions/{subject_id}` — отозвать право
- [ ] `PATCH /kb/articles/{id}/inherit` — `{inherit_permissions: bool}`; при переключении на `false` копировать текущие права раздела как стартовую точку
- [ ] `GET /kb/users/search?q=...` — поиск пользователей + групп из Keycloak Admin API для picker в UI (только editor/manager/admin)
- [ ] Все существующие KB endpoints (`GET /kb/articles`, `GET /kb/articles/{id}`, `GET /kb/sections`) — пропустить через `resolve_permission`; возвращать только доступное
- [ ] Файлы и медиа: проверка прав через `resolve_permission` перед `X-Accel-Redirect`
- [ ] Аудит: изменения прав → `audit_log` (`event_type: kb.permission_grant / kb.permission_revoke`)

**Фронтенд — управление правами KB:**
- [ ] `KbPermissionsModal.vue` — модальное окно управления правами (для раздела и статьи):
  - Список текущих субъектов с правами (аватар + имя + уровень + кнопка удалить)
  - Picker: поиск пользователей/групп (`GET /kb/users/search`) с debounce 400 мс
  - Выбор уровня: Viewer / Editor / Manager
  - Переключатель «Наследовать права от раздела» (только для статей)
- [ ] `KbSectionTree.vue`: контекстное меню раздела — пункт «Управлять доступом» (только manager/admin)
- [ ] `KbArticlePage.vue`: кнопка «Доступ» в шапке (только manager/admin); badge «🔒 Ограниченный доступ» если `inherit_permissions=false`
- [ ] Фильтрация в `KbListPage.vue` и `KbSectionTree.vue`: показывать только разделы/статьи к которым есть хотя бы viewer-доступ
- [ ] i18n ключи: `kb.permissions.*` в `ru.json` и `en.json`

**Бэкенд — переход на Markdown:**
- [ ] Alembic миграция `010_kb_markdown`: убедиться что `body TEXT` остаётся; добавить таблицу `kb_article_files` (`id`, `article_id`, `filename`, `original_name`, `size_bytes`, `mime_type`, `uploaded_by`, `created_at`)
- [ ] Скрипт `backend/scripts/migrate_kb_html_to_md.py` — конвертация существующего HTML-контента в Markdown (через `markdownify`); idempotent, с dry-run флагом
- [ ] `KB_MEDIA_MAX_SIZE_MB`, `KB_ATTACHMENT_MAX_SIZE_MB` добавить в `Settings` и `.env.example`
- [ ] `POST /kb/articles/{id}/media` — загрузка изображений в тело статьи; сохраняется в `/data/kb/media/{article_id}/`; возвращает `{url}`
- [ ] `GET /kb/media/{article_id}/{filename}` — отдача медиа-файлов (через Nginx `/kb/media/` location)
- [ ] `POST /kb/articles/{id}/files` — загрузка прикреплённых файлов; сохраняется в `/data/kb/files/{article_id}/`
- [ ] `GET /kb/articles/{id}/files` — список прикреплённых файлов
- [ ] `DELETE /kb/articles/{id}/files/{file_id}` — удалить прикреплённый файл (автор или admin)
- [ ] `GET /kb/files/{article_id}/{filename}` — скачивание с `Content-Disposition: attachment; filename*=UTF-8''...` (RFC 5987)
- [ ] Аудит: загрузка медиа, скачивание файлов — в `audit_log`

**Бэкенд — экспорт:**
- [ ] `GET /kb/articles/{id}/export/md` — статья как `.md` файл с YAML frontmatter (`title`, `tags`, `section`, `author`, `created`, `updated`)
- [ ] `GET /kb/sections/{id}/export/zip` — раздел как ZIP: подпапки по иерархии + `_attachments/{article_slug}/`
- [ ] `GET /kb/export/vault.zip` — вся KB как ZIP, совместимый с Obsidian vault; изображения встроены как data URI или лежат в `_attachments/`
- [ ] Временные ZIP-файлы экспорта: генерируются в память (io.BytesIO), не сохраняются на диск

**Бэкенд — импорт:**
- [ ] `POST /kb/articles/import` — принимает `.md` файл; парсит YAML frontmatter; создаёт или обновляет статью; секцию создаёт если не существует
- [ ] `POST /kb/import/vault` — принимает ZIP (Obsidian vault); рекурсивно обходит папки → создаёт разделы по структуре; `?strategy=skip|overwrite|create_new` (default: `skip`)
- [ ] Отчёт импорта в ответе: `{created: N, updated: N, skipped: N, errors: [...]}`

**Бэкенд — diff версий:**
- [ ] `GET /kb/articles/{id}/versions/{v1}/diff/{v2}` — построчный diff Markdown между версиями (через Python `difflib.unified_diff`); возвращает `{hunks: [...], stats: {added, removed}}`

**Фронтенд — редактор:**
- [ ] `RichEditor.vue`: подключить `Markdown` extension из `tiptap-markdown`; переключить `onUpdate` с `getHTML()` на `editor.storage.markdown.getMarkdown()`; `setContent` принимать Markdown
- [ ] Тулбар: добавить кнопку «Вставить изображение» — открывает диалог выбора файла → `POST /kb/articles/{id}/media` → вставляет `![alt](url)` через `insertContent`
- [ ] Drag & drop изображений в редактор — перехватить `drop` event, загрузить через media endpoint
- [ ] Вставка изображений из буфера обмена (`paste` event с `image/*`)

**Фронтенд — вложения:**
- [ ] `KbArticleFormPage.vue`: блок «Прикреплённые файлы» под редактором — список + кнопка «Прикрепить файл» + удаление
- [ ] `KbArticlePage.vue`: блок «Файлы» на странице просмотра статьи — список с иконкой типа, размером, кнопкой скачивания
- [ ] `KbAttachmentsPanel.vue` — переиспользуемый компонент (форма и просмотр)

**Фронтенд — импорт/экспорт UI:**
- [ ] `KbArticlePage.vue`: в меню экспорта добавить пункт «Скачать Markdown (.md)»
- [ ] `KbListPage.vue`: кнопка «Экспортировать раздел (.zip)» в заголовке раздела (только editor/admin)
- [ ] Страница Admin → KB: кнопка «Экспортировать всю KB» и «Импортировать из Obsidian (.zip)»
- [ ] Диалог импорта: drag-and-drop зона для `.md` / `.zip`; прогресс-бар; отчёт по результатам

**Фронтенд — diff версий:**
- [ ] `KbVersionDiffModal.vue` — модальное окно сравнения версий: side-by-side или unified view; добавленные строки зелёным, удалённые красным
- [ ] Вызывается из истории версий в `KbArticlePage.vue` кнопкой «Сравнить с текущей» или «Сравнить версии»
- [ ] i18n ключи: `kb.diff.*`, `kb.import.*`, `kb.export.*`, `kb.files.*`, `kb.media.*` в `ru.json` и `en.json`

**Документация:**
- [ ] `docs/db-schema.md` — добавить таблицу `kb_article_files` (миграция 009)
- [ ] `docs/api-contracts.md` — добавить все новые endpoints (media, files, import, export, diff)
- [ ] `docs/adr.md` — ADR-018: KB хранит Markdown в PostgreSQL, файловая система только для блобов

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

### [ ] Step 8.5: Phase 4.5 — Фотогалерея (Immich)
_Детальный план: `docs/immich-integration.md`_

> Разворачивается после уведомлений (SSE/email уже есть). Immich — self-hosted Google Photos, AGPL-3.0, нативная поддержка Keycloak OIDC.
> Используется последняя стабильная версия (`IMMICH_VERSION=release`).

**Уточнения по итогам обсуждения:**
- `immich-machine-learning` — optional, через `profiles: [ml]` (можно подключить позже)
- Отдельный `immich-postgres` (pgvecto-rs) — отдельный инстанс, своя БД
- `IMMICH_CORP_ALBUM_ID` — ручная настройка после первого запуска (ок)
- Graceful fallback: виджет скрывается, если Immich не настроен (`{"configured": false}`)
- Disk-кэш для thumbnail'ов: `/data/cache/immich/` + Redis TTL 1 ч
- `immich_widget_limit` (кол-во фото в виджете) — в Admin UI → Система
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
- [ ] Получить UUID альбома → записать в `IMMICH_CORP_ALBUM_ID` в `.env`
- [ ] Создать сервисный API-ключ (Administration → API Keys) → `IMMICH_API_KEY` в `.env`
- [ ] INSERT ярлыка "Фотогалерея" в `service_links` через Admin UI с `supports_sso=true`

**Backend:**
- [x] `backend/app/api/photos.py`: `GET /api/v1/photos/recent` — возвращает `{"configured": false}` если ключи не заданы; иначе последние N фото из корп. альбома через Immich API
- [x] `GET /api/v1/photos/thumbnail/{asset_id}` — прокси thumbnail: disk-кэш `/data/cache/immich/` + Redis TTL 1 ч; `Cache-Control: public, max-age=3600`
- [x] `Settings`: `IMMICH_URL`, `IMMICH_PUBLIC_URL`, `IMMICH_API_KEY`, `IMMICH_CORP_ALBUM_ID`
- [x] `immich_widget_limit` добавлен в `SystemSettings` (Admin UI → Система, default 8)
- [x] Регистрация роутера в `main.py`

**Frontend:**
- [x] `src/components/widgets/PhotosWidget.vue` — сетка 4×2 превью, skeleton loader, ссылка "Все фото →"; виджет скрыт при `configured=false`
- [x] Виджет размещён на HomePage в боковой колонке
- [x] i18n ключи: `photos.title`, `photos.see_all`, `photos.empty`, `photos.notConfigured` в `ru.json` и `en.json`

**Admin UI:**
- [x] Вкладка «Система» → новая секция «Фотогалерея»: поле `immich_widget_limit` (число, 1–50)

**Тесты:**
- [x] Unit: `test_photos.py` — сортировка фото по дате, прокси thumbnail → Cache-Control header, 401 без авторизации, `configured=false` когда настройки пусты, лимит из system.json (12+ тестов)
- [ ] Integration: httpx mock Immich API (GET album, GET thumbnail) — запускается с Docker
- [ ] E2E: виджет отображается на главной → клик по фото → открывается Immich в новой вкладке — запускается с Docker

### [ ] Step 8.6: Phase 4.6 — Видеогалерея (PeerTube)
_Детальный план: `docs/peertube-integration.md`_

> PeerTube уже установлен. Фокус на SSO через OIDC-плагин, виджет видео на главной, iframe embed в статьях/новостях.

**SSO (Keycloak ↔ PeerTube через плагин):**
- [ ] Установить плагин `peertube-plugin-auth-openid-connect` (Admin → Plugins или CLI)
- [ ] Новый клиент `peertube` в Keycloak (Confidential, OIDC, Redirect URI на `/plugins/auth-openid-connect/*/router/code-cb`)
- [ ] Mapper `peertube_role` → claim (editor/admin → `moderator`, остальные → `user`)
- [ ] Настройка плагина: Discovery URL, Client ID/Secret, username/mail/role claims, Button text
- [ ] Отключить локальную регистрацию в PeerTube (только SSO)
- [ ] Privacy по умолчанию: `Internal` (только залогиненные)
- [ ] Smoke-test SSO: переход из портала → PeerTube без повторного логина

**Данные / настройка:**
- [ ] Создать сервисный аккаунт `portal-svc` (Role: User) для API-запросов виджета
- [ ] `curl /api/v1/oauth-clients/local` → записать `PEERTUBE_CLIENT_ID`/`PEERTUBE_CLIENT_SECRET`
- [ ] Создать корпоративные каналы: `corporate`, `training`, `demos`
- [ ] INSERT ярлыка "Видеопортал" в `service_links` с `supports_sso=true`

**Backend:**
- [ ] `backend/app/api/videos.py`: `GET /api/v1/videos/recent` — последние N видео через PeerTube API + OAuth2 token
- [ ] `GET /api/v1/videos/thumbnail/{uuid}` — прокси thumbnail (кэш 1 час в Redis)
- [ ] Кэширование OAuth2 токена сервисного аккаунта в Redis (TTL = `expires_in - 60`)
- [ ] `Settings`: `PEERTUBE_URL`, `PEERTUBE_PUBLIC_URL`, `PEERTUBE_CLIENT_ID`, `PEERTUBE_CLIENT_SECRET`, `PEERTUBE_SVC_USERNAME`, `PEERTUBE_SVC_PASSWORD`, `PEERTUBE_CHANNEL_ID`
- [ ] Регистрация роутера в `main.py`

**Frontend — виджет:**
- [ ] `src/components/widgets/VideosWidget.vue` — сетка 3×2, thumbnail 16:9, badge длительности, skeleton loader
- [ ] Разместить виджет на HomePage
- [ ] i18n ключи: `videos.title`, `videos.see_all`, `videos.empty` в `ru.json`/`en.json`

**Frontend — iframe embed в TipTap:**
- [ ] `src/components/editor/extensions/IframeEmbed.ts` — кастомный Node с whitelist доменов
- [ ] Зарегистрировать в `RichEditor.vue` с `allowedDomains: [VITE_PEERTUBE_URL]`
- [ ] Кнопка "Вставить видео" в тулбаре редактора
- [ ] `sanitize.ts`: DOMPurify hook — разрешить `<iframe>` только с PeerTube домена
- [ ] `VITE_PEERTUBE_URL` в `.env.example` фронтенда

**Nginx / CSP:**
- [ ] Добавить `https://video.company.local` в `frame-src` и `media-src` заголовка CSP
- [ ] Убедиться что Nginx проксирует PeerTube (уже установлен, настроить server block если нужно)

**Тесты:**
- [ ] Unit: форматирование длительности/просмотров, whitelist iframe доменов, 401 без авторизации
- [ ] Unit frontend: IframeEmbed extension — разрешает PeerTube, блокирует YouTube
- [ ] Integration: httpx mock PeerTube API (token + videos), thumbnail proxy
- [ ] E2E: виджет видео на главной → клик → PeerTube в новой вкладке
- [ ] E2E: editor вставляет iframe embed в статью → iframe отображается при просмотре

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
