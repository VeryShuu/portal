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
- [ ] Keycloak OIDC: Authorization Code Flow + PKCE (`GET /auth/login`, `GET /auth/callback`)
- [ ] Silent authentication (`prompt=none`) при открытии портала
- [ ] Хранение токенов в Redis (session_id в HTTPOnly cookie, не сам JWT)
- [ ] Refresh token rotation, автообновление сессии
- [ ] Ролевая модель: `reader` / `editor` / `admin` из JWT claims
- [ ] `POST /auth/logout` + SLO через Keycloak front-channel
- [ ] Таблица `users`: upsert при каждом логине из JWT claims (ФИО, отдел, должность, телефон)
- [ ] `GET /users`, `GET /users/{id}` — справочник сотрудников
- [ ] `PATCH /users/me/profile` — статус присутствия, аватар (local volume)
- [ ] `PATCH /users/me/preferences` — preferences JSONB (hidden_link_ids)
- [ ] `POST /admin/users/sync` — ручная синхронизация из Keycloak Admin API (ARQ)
- [ ] `PATCH /admin/users/{id}/role` — смена роли
- [ ] Блокировка доступа вне VPN/внутренней сети (Nginx allow/deny)
- [ ] Аудит входов/выходов в `audit_log`

**Новости:**
- [ ] Таблица `news` + `news_versions` (Alembic миграция)
- [ ] `POST /news`, `PUT /news/{id}`, `DELETE /news/{id}` — CRUD
- [ ] WYSIWYG-редактор TipTap v2 + tiptap-markdown (dual-mode)
- [ ] Черновики с автосохранением каждые 30 сек (`PUT /news/{id}/draft`)
- [ ] Таргетирование по отделам и ролям (`target_departments`, `target_roles`)
- [ ] Отложенная публикация (`publish_at`) — ARQ cron каждую минуту
- [ ] Автоархивация (`archive_at`) — ARQ cron каждый час
- [ ] Закрепление новости (`is_pinned`), категории
- [ ] Soft delete + восстановление
- [ ] Версионность (история редактирования)
- [ ] `GET /news` с пагинацией + фильтрами + таргетингом по профилю из JWT
- [ ] Счётчик просмотров (дедупликация 1/час/user через Redis)
- [ ] Главная страница: последние новости + закреплённые + приветствие

**i18n:**
- [ ] vue-i18n v9: `ru.json` (мастер) + `en.json` — все строки интерфейса с первого компонента
- [ ] Переключатель языка в шапке, сохранение в `users.lang`
- [ ] CI-проверка: отсутствующие ключи `en.json` vs `ru.json` = ошибка сборки
- [ ] Тёмная/светлая тема через Naive UI `n-config-provider`

**Тесты Phase 1:**
- [ ] Unit: JWT parsing, token refresh, маппинг claims → модель, таргетинг новостей
- [ ] Integration: Keycloak OIDC flow (mock), DB upsert, ARQ задачи публикации
- [ ] E2E: логин → главная с новостями → выход (SLO)
- [ ] E2E: создание новости с таргетом → отложенная публикация

### [ ] Step 6: Phase 2 — Ярлыки сервисов + Закладки
_ТЗ: §3.5 Навигация и ярлыки, §3.9 Закладки_

- [ ] Таблица `service_links` (Alembic миграция)
- [ ] `GET /links` — все активные ярлыки, сгруппированные по категориям
- [ ] `POST /links`, `PUT /links/{id}`, `DELETE /links/{id}` — CRUD только admin
- [ ] SSO-проброс при клике: если `supports_sso=true` → передаётся `id_token_hint` в URL
- [ ] Персонализация: скрытие ненужных ярлыков через `PATCH /users/me/preferences` (`hidden_link_ids`)
- [ ] Таблица `bookmarks` (Alembic миграция)
- [ ] `GET /bookmarks`, `POST /bookmarks`, `DELETE /bookmarks/{id}` — личные закладки
- [ ] `PATCH /bookmarks/reorder` — drag-and-drop сортировка
- [ ] Группы закладок (`group_name`)
- [ ] Блок «Избранное» на главной странице

**Тесты Phase 2:**
- [ ] Unit: валидация URL ярлыков, сортировка закладок
- [ ] Integration: DB CRUD ярлыков и закладок
- [ ] E2E: добавить закладку → drag-and-drop → сохранилось; скрыть ярлык → не показывается

### [ ] Step 7: Phase 3 — База знаний + Поиск
_ТЗ: §3.3 База знаний, §3.7 Умный поиск_

**База знаний:**
- [ ] Таблицы `kb_sections`, `kb_articles`, `kb_article_versions`, `kb_tags`, `kb_article_tags`, `kb_article_comments` (Alembic миграция)
- [ ] `GET /kb/sections` — дерево разделов (рекурсивный CTE для хлебных крошек)
- [ ] `POST /kb/sections`, `PUT /kb/sections/{id}`, `DELETE /kb/sections/{id}` — CRUD разделов
- [ ] `GET /kb/articles`, `POST /kb/articles`, `PUT /kb/articles/{id}`, `DELETE /kb/articles/{id}`
- [ ] TipTap v2 dual-mode: WYSIWYG ↔ raw Markdown; вставка изображений из Nextcloud / Ctrl+V
- [ ] Черновики с автосохранением (`PUT /kb/articles/{id}/draft`)
- [ ] Оптимистичная блокировка: поле `version`, 409 Conflict при коллизии с diff
- [ ] Версионность статей: `GET /kb/articles/{id}/versions`, откат к версии N
- [ ] Soft delete + восстановление (`POST /kb/articles/{id}/restore`)
- [ ] Теги: многие-ко-многим через `kb_article_tags`
- [ ] Комментарии: `GET/POST /kb/articles/{id}/comments`
- [ ] «Предложить правку» (`POST /kb/articles/{id}/suggest`) → уведомление редактора
- [ ] Кнопка «Статья полезна?» (helpful/not helpful)
- [ ] Счётчик просмотров (Redis дедупликация)
- [ ] Экспорт PDF: Playwright/Chromium (`POST /kb/articles/{id}/export/pdf`)
- [ ] Экспорт DOCX: python-docx (`POST /kb/articles/{id}/export/docx`)

**Поиск:**
- [ ] `GET /search?q=...` — единый поиск: KB-статьи + новости + ярлыки + пользователи
- [ ] FTS через PostgreSQL `body_tsvector` + `ts_headline()` для сниппетов
- [ ] `GET /search/suggest?q=...` — typeahead через pg_trgm (debounce 300 мс на фронте)
- [ ] Нечёткий поиск (опечатки): `pg_trgm similarity ≥ 0.3`
- [ ] Фильтры: тип, дата, автор
- [ ] История поиска: последние 10 запросов (localStorage)
- [ ] Аудит поисковых запросов в `audit_log`

**Тесты Phase 3:**
- [ ] Unit: версионность, права доступа на статьи, генерация PDF, FTS + pg_trgm ranking
- [ ] Integration: DB CRUD с реальным PostgreSQL (FTS запросы), Playwright PDF
- [ ] E2E: создать статью → найти с опечаткой → экспорт PDF → откат версии
- [ ] E2E: `reader` пытается создать статью → 403

### [ ] Step 8: Phase 4 — Email уведомления + In-app уведомления
_ТЗ: §3.12 Уведомления_

> Обе части реализуются вместе — in-app SSE нужна для Phase 1/2/3 (новости, правки статей), отдельно от email не имеет смысла.

- [ ] Таблица `notifications` (Alembic миграция)
- [ ] `GET /notifications` — список непрочитанных (пагинация)
- [ ] `POST /notifications/{id}/read`, `POST /notifications/read-all`
- [ ] **In-app SSE:** `GET /notifications/stream` через Redis Streams (`XADD`/`XREAD`)
  - `Last-Event-ID` для event replay при реконнекте
  - Bell-icon в шапке со счётчиком непрочитанных
- [ ] **Email:** aiosmtplib + Postfix; ARQ tasks с retry + exponential backoff
  - Шаблоны писем: новость опубликована, статья обновлена, правка одобрена
- [ ] Настройки уведомлений в профиле: `notify_email`, `notify_inapp`
- [ ] Отправка уведомлений при: публикации новости, обновлении закладленной статьи, одобрении правки
- [ ] ARQ worker: SSE connections limit — uvicorn `--limit-concurrency`, `workers=2-4`

**Тесты Phase 4:**
- [ ] Unit: SSE payload, email рендеринг, таргетинг получателей
- [ ] Integration: Redis Streams pub/sub, aiosmtplib mock
- [ ] E2E: опубликовать новость → SSE уведомление появилось в bell icon

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
