# Architecture Decision Records (ADR)

> Корпоративный интранет-портал
> Последнее обновление: апрель 2026 (ADR-026 — Immich; ADR-027 — PeerTube; ADR-028 — Modules Admin UI)

Каждый ADR описывает одно архитектурное решение: контекст, альтернативы, выбор и обоснование.

---

## ADR-001: Keycloak как единственный IdP

**Статус:** Принято

**Контекст:**
Инфраструктура уже включает Keycloak с настроенной LDAP Federation к Active Directory. Nextcloud ранее аутентифицировал пользователей напрямую через LDAP.

**Решение:**
Портал использует только Keycloak (OIDC). Портал не обращается к AD напрямую. Nextcloud переводится с LDAP на Keycloak `user_oidc` app.

**Альтернативы:**
- Прямой LDAP из портала → отклонено: дублирование логики, два источника правды
- Keycloak + прямой LDAP как fallback → отклонено: усложняет сопровождение

**Последствия:**
- Требует миграции Nextcloud (1 рабочий день, описано в prerequisites)
- Все user-атрибуты (отдел, должность, телефон) берутся только из JWT claims
- Обязательная настройка Keycloak Protocol Mappers для `department`, `job_title`, `phone`, `groups`
- Ручная синхронизация: кнопка admin → Keycloak Admin API → обновление `users`

---

## ADR-002: Nextcloud — impersonation через Bearer JWT (Вариант B)

**Статус:** Принято

**Контекст:**
Портал должен показывать пользователям файлы из Nextcloud с соблюдением ACL. Было несколько вариантов интеграции.

**Решение:**
Все файловые операции (листинг, скачивание, загрузка, шаринг) выполняются от имени конкретного пользователя через `Authorization: Bearer {user_access_token}`. Nextcloud резолвит JWT через `user_oidc` app и применяет ACL пользователя. Service account (`portal-svc`) используется **только** для системных операций (Templates, webhooks).

**Альтернативы:**
- Вариант A: служебный аккаунт для всех операций → отклонено: нарушает ACL, некорректный audit trail (все операции от `portal-svc`)
- WOPI-сервер на стороне портала → отклонено: вне скопа, сложная реализация
- OCS временные share-ссылки → отклонено: TTL в OCS работает в днях, не минутах; мусор в БД Nextcloud

**Условие применимости:**
`user_oidc` версии ≥ 1.3 с поддержкой Bearer token authentication. Smoke-test описан в prerequisites. При неудаче — fallback через service account с pre-check прав (stopgap).

**Скачивание:** WebDAV streaming через `httpx.stream() → StreamingResponse` (не временные share-ссылки)

**Upload:** `фронтенд → бэкенд → WebDAV PUT` (не прямой upload с фронта: утечка токена, CORS, нет audit)

**httpx таймауты:**
- Листинг/метаданные: 10 сек
- Скачивание: без таймаута (`None`)
- Загрузка: 600 сек
- Health check (`/status.php`): 3 сек

**Последствия:**
- JWT пользователя должен содержать `aud: nextcloud` (настраивается Audience mapper в Keycloak)
- Audit trail в Nextcloud корректен: реальное имя пользователя
- Требует ротации app-password service account каждые 90 дней

**⚠️ WebDAV path mapping — TBD (определить при миграции Nextcloud):**

Настройка `Use unique user ID` в `user_oidc` определяет имя папки пользователя в WebDAV:
- `OFF` → `preferred_username` → путь `/remote.php/dav/files/ivanov/`
- `ON` → UUID sub из Keycloak → путь `/remote.php/dav/files/{uuid}/`

Инженер фиксирует выбор в `.env` как `NC_USER_ID_FIELD=preferred_username` или `NC_USER_ID_FIELD=sub`. `nextcloud.py` строит путь из этой переменной, а не хардкодит. Это решение должно быть принято **до** старта разработки модуля файлов.

---

## ADR-003: Хранение аватаров в local volume (не PostgreSQL BYTEA, не Nextcloud)

**Статус:** Принято

**Контекст:**
Нужно хранить аватары ~300 пользователей.

**Решение:**
Local Docker volume `avatars_data`, примонтированный в `/data/avatars/` контейнера backend. Nginx отдаёт статику напрямую (`location /static/avatars/`). В PostgreSQL хранится только `avatar_url VARCHAR(512)`.

**Альтернативы:**
- `BYTEA` в PostgreSQL → отклонено: раздувает WAL, тяжёлые бэкапы, IO деградация
- Nextcloud `/avatars/{user_id}/` → отклонено: service account не разграничивает доступ корректно; Nextcloud — для документов, не статики
- MinIO/S3 → отклонено: избыточно для 300 × 200 КБ ≈ 60 МБ

**Последствия:**
- При горизонтальном масштабировании backend потребуется shared volume или смена на MinIO (v2)
- Бэкап: volume включается в ежедневный бэкап `docker volume cp`

---

## ADR-004: UI — Naive UI (вместо PrimeVue)

**Статус:** Принято

**Контекст:**
Выбор UI-библиотеки для Vue 3 + TypeScript.

**Решение:** **Naive UI**

**Сравнение:**
| Критерий | Naive UI | PrimeVue 4 | Vuetify 3 |
|----------|----------|-----------|-----------|
| TypeScript | 100% native | Частично | Хорошо |
| Dark/Light тема | CSS variables нативно | PrimeFlex/конфликт | Material Design |
| Bundle size | ~120 KB | ~300+ KB | ~250 KB |
| Opinionated стиль | Нет | Да (PrimeFlex) | Material Design |

**Последствия:**
- Тема кастомизируется через `n-config-provider` без CSS override
- Нет зависимости от PrimeFlex или Tailwind

---

## ADR-005: WYSIWYG — TipTap v2 с dual-mode (Visual + Markdown)

**Статус:** Принято

**Контекст:**
300 сотрудников включают как технических, так и нетехнических пользователей (HR, бухгалтерия).

**Решение:**
TipTap v2 + `tiptap-markdown` (community package, не несуществующий `@tiptap/extension-markdown`). Два режима в одном редакторе:
- **Визуальный** (по умолчанию) — WYSIWYG, CommonMark + GFM
- **Markdown** — raw-редактирование в CodeMirror

**Хранение:** Markdown (CommonMark + GFM) как source of truth в PostgreSQL `TEXT`.

**Санитизация:** `bleach` (Python) на бэкенде запрещает raw HTML в MD перед сохранением.

**Вставка изображений:**
- Кнопка тулбара → модалка файлового браузера Nextcloud → `![alt](url)`
- Ctrl+V скриншота → автозагрузка в Nextcloud (PUT через бэкенд) → вставка ссылки

**Альтернативы:**
- Только Markdown → отклонено: плохой UX для нетехнических пользователей
- TipTap с HTML-хранением → отклонено: сложная санитизация, тяжёлый diff в версионировании
- ProseMirror напрямую → отклонено: избыточная сложность

**Ограничения:** без resize изображений, без custom embeds — только CommonMark/GFM

---

## ADR-006: PDF-экспорт через Playwright/Chromium (не WeasyPrint)

**Статус:** Принято

**Контекст:**
Нужен экспорт статей KB в PDF.

**Решение:** Playwright/Chromium (`page.pdf()`): рендерит Markdown → HTML → PDF

**Альтернативы:**
- WeasyPrint → отклонено: зависимости Cairo/Pango/GObject (~400 МБ в Docker образе)
- xhtml2pdf → отклонено: слабая поддержка CSS, артефакты рендеринга
- wkhtmltopdf → отклонено: устаревший, плохая поддержка современного CSS

**Преимущество:** Playwright Chromium уже включён в образ для E2E-тестов — нет дополнительных зависимостей.

---

## ADR-007: Rate Limiting — fastapi-limiter (не slowapi)

**Статус:** Принято

**Контекст:**
Нужен per-user rate limiting на уровне FastAPI.

**Решение:** `fastapi-limiter` — async-native, работает на `redis.asyncio`.

**Альтернативы:**
- `slowapi` → отклонено: синхронный Redis client в некоторых версиях блокирует event loop
- Только Nginx `limit_req_zone` → отклонено: только per-IP, нет per-user, грубая защита

**Применение (актуально на момент Phase 3.5):**
- `POST /auth/local/login` — 5/15 мин/IP (по `X-Real-IP`)
- `POST /auth/refresh` — 30/мин/user
- `GET /search` — 60/мин/user
- `GET /search/suggest` — 120/мин/user
- `PATCH /users/me/password` — 10/15 мин/user
- `PATCH /users/admin/{id}/password` — 20/15 мин/admin
- `POST /files/upload` — 10/мин/user (запланировано)
- Экспорт PDF/DOCX — 5/мин/user
- Остальные state-changing endpoints — без явного лимита (полагается на CSRF + Origin check)

---

## ADR-008: Хранение контента в Markdown, не HTML

**Статус:** Принято

**Контекст:**
TipTap может хранить контент в HTML или Markdown.

**Решение:** Markdown (CommonMark + GFM) как source of truth.

**Преимущества:**
- Чистый `diff` в версионировании статей (читаемый git-style diff)
- Читаем без рендера (в базе, в бэкапах)
- Совместим с онлайн-редакторами Markdown
- Проще санитизация (запрет raw HTML через `bleach`)

**Ограничения (принято как компромисс):**
- Roundtrip MD → TipTap → MD при сложном контенте (таблицы с colspan) теряет часть форматирования — поэтому ограничения редактора: только CommonMark/GFM возможности

---

## ADR-009: Оптимистичная блокировка (version field) вместо пессимистичной

**Статус:** Принято

**Контекст:**
Два редактора могут одновременно открыть статью KB.

**Решение:** Поле `version INTEGER` в `kb_articles`. При UPDATE: `WHERE id=:id AND version=:expected_version`. При несовпадении → `409 Conflict`. Клиент показывает diff и предлагает ручное слияние.

**Альтернативы:**
- `locked_by UUID + locked_at TIMESTAMPTZ` (пессимистичная) → отклонено: требует heartbeat для разблокировки зависших сессий, сложнее инфраструктурно

**Последствия:**
- Клиент обязан отправлять `version` при каждом PUT
- При 409 клиент показывает: «Статья была изменена пользователем X. Ваши изменения: ... Текущая версия: ...»

---

## ADR-010: ON DELETE RESTRICT на kb_sections.parent_id (не CASCADE)

**Статус:** Принято

**Контекст:**
Дерево разделов KB реализовано как adjacency list с self-referencing FK.

**Решение:** `ON DELETE RESTRICT` — при попытке удалить раздел с дочерними → ошибка на уровне БД.

**Альтернатива:**
- `ON DELETE CASCADE` → отклонено: рекурсивный CASCADE при удалении корневого раздела сносит всё дерево включая все статьи. Это чаще баг, чем фича.

**API:** явный endpoint `DELETE /api/v1/kb/sections/{id}?force=true` — удаление раздела со всем содержимым (только admin, логируется в audit).

---

## ADR-011: SSE через Redis Streams (не pub/sub)

**Статус:** Принято

**Контекст:**
In-app уведомления требуют realtime-доставки при SSE-реконнекте.

**Решение:** Redis Streams (`XADD`/`XREAD`) с `Last-Event-ID` для event replay.

**Альтернативы:**
- Redis pub/sub → отклонено: нет персистентности, при разрыве соединения события теряются
- WebSocket → отклонено: избыточно для односторонних уведомлений
- Centrifugo → отклонено: дополнительный сервис, усложняет деплой

**Ограничения:** SSE через Uvicorn держит постоянные коннекты → `workers=2-4`, `--limit-concurrency`. TTL на записи в Stream: 24 ч (`XADD MAXLEN 100`).

---

## ADR-012: Audit Log — async batch insert через ARQ (не синхронная запись)

**Статус:** Принято

**Контекст:**
Каждое действие пользователя должно логироваться, но синхронная запись в БД блокировала бы API.

**Решение:**
- API handler: `background_tasks.add_task(audit_service.enqueue, ...)` — кладёт в Redis list
- ARQ worker: batch INSERT из Redis list каждые 1–2 сек
- Таблица `audit_log` партиционирована по месяцам (native PG16, без pg_partman)
- Retention: 12 месяцев онлайн; ARQ-задача ежемесячно `DROP TABLE audit_log_YYYY_MM`
- Индексы: `(user_id, created_at DESC)`, `(event_type, created_at DESC)`, `(resource_type, resource_id)`

**Последствия:**
- Максимальная задержка записи: ~2 сек (приемлемо)
- При падении Redis до flush: потеря событий в этом окне (принято как компромисс)

---

## ADR-013: CSRF — SameSite=Strict + Origin/Referer (не Double Submit Cookie)

**Статус:** Принято

**Контекст:**
Токены хранятся в HTTPOnly cookies, SPA делает запросы через `fetch`.

**Решение:** `SameSite=Strict` на всех cookies + проверка `Origin`/`Referer` заголовков на бэкенде.

**Альтернатива:**
- Double Submit Cookie → отклонено: требует не-HttpOnly CSRF-cookie, которую JS читает и шлёт в заголовке. Усложняет код без значимого прироста безопасности при `SameSite=Strict`.

**Покрытие:** `SameSite=Strict` закрывает 99% CSRF. Origin/Referer check — дополнительный слой.

---

## ADR-014: Idempotency — хранение только `{"id": uuid}`, не полного response body

**Статус:** Принято

**Контекст:**
Idempotency middleware кэширует ответ для повторных запросов.

**Решение:** Хранить только `{"id": resource_uuid}` + `status_code`. Каждый POST-endpoint в whitelist обязан выставлять заголовок `X-Resource-Id: {uuid}`.

**Почему не полный body:**
- StreamingResponse (скачивание файла 500 МБ) нельзя сохранить в JSONB — БД умрёт
- Клиенту достаточно `id` для последующего GET

**Применяется только к whitelist:** `POST /news`, `POST /kb/articles`, `POST /files/upload`, `POST /notifications/send`. TTL: 24 часа.

---

## ADR-015: Docker healthcheck — `/ready`, не `/health`

**Статус:** Принято

**Контекст:**
Docker healthcheck должен перезапускать контейнер при падении зависимостей.

**Решение:**
- `GET /health` — всегда 200 (жив ли процесс)
- `GET /ready` — 200/503 (готов ли к трафику: DB + Redis + Nextcloud)
- Docker healthcheck использует `/ready`

**Проблема `/health`:** процесс жив, но PostgreSQL упал → `/health` = 200, контейнер не перезапустится, API отдаёт 500. `/ready` = 503 → Docker перезапускает контейнер или LB исключает его.

---

## ADR-016: LocalLoginRequest — `str` вместо `EmailStr` для корпоративных доменов

**Статус:** Принято

**Контекст:**
Endpoint `POST /api/v1/auth/local/login` принимает `email` и `password`. Использование `pydantic[email]` (тип `EmailStr`) возвращало 422 Unprocessable Content для адресов вида `admin@company.local`.

**Причина:**
`email-validator` (зависимость `pydantic[email]`) по умолчанию проверяет DNS-доставляемость домена (`check_deliverability=True`). Домены `.local` являются mDNS-доменами (RFC 6762) и не резолвятся через публичный DNS → валидация падает даже для корректно сформированных адресов.

**Решение:**
В `LocalLoginRequest` (и аналогичных login-схемах) использовать:
```python
email: str = Field(min_length=1, max_length=255)
```

**Ограничение:** `EmailStr` с `check_deliverability=False` через `EmailStr` не настраивается на уровне поля в Pydantic v2 — только через глобальный параметр или кастомный тип. Использование `str` проще и прозрачнее.

**Где `EmailStr` остаётся:** `LocalUserCreateRequest` (создание пользователей через admin-API) — там валидация формата email желательна и домены могут быть любыми.

**Последствия:**
- Login принимает любую строку ≥1 символ. Защита от мусора — проверка по БД (email не найден → 401).
- Документация в OpenAPI показывает поле как `string`, не `email format` — принято как компромисс.

---

## ADR-017: Dual-auth, единая Redis-сессия, роль из БД

**Статус:** Принято (Phase 2.1)

**Контекст:**
До Phase 2.1 портал авторизовал только через Keycloak OIDC, и роль читалась из JWT claim `role`. Для bootstrap первого admin и аварийного входа без работающего Keycloak потребовался второй источник аутентификации (email + bcrypt). Возникли вопросы: как изолировать источники, где хранить сессию, где хранить роль, что делать при account-collision по email.

**Решение:**
1. **Поле `users.auth_source`** ∈ `{"keycloak", "local"}` (`CHECK`-constraint). `keycloak_id` стал `NULLABLE`, добавлено `password_hash VARCHAR(255) NULL`.
2. **Единая Redis-сессия** для обоих источников: ключ `session:{uuid}` → `{user_id, auth_source, [access_token, refresh_token, id_token]}`. В HTTPOnly+Secure+SameSite=Lax cookie `portal_session` уходит только opaque session_id. JWT в cookie не кладётся даже для Keycloak-источника.
3. **Cookie SameSite=Lax** (не Strict) — иначе Keycloak-редирект на `/auth/callback` не передаёт cookie. CSRF-защита: SameSite=Lax + Origin/Referer-check. Top-level GET-навигация безопасна по семантике Lax.
4. **Роль хранится в БД** (`users.role`), а не читается из JWT при каждом запросе. Источник назначения:
   - Keycloak: первый upsert берёт `role` из JWT-claim (если есть), затем меняется только через admin-API.
   - Local: задаётся при создании (`POST /users/admin/local`) или из env (`ADMIN_EMAIL`).
   Это даёт админу мгновенное понижение/повышение прав без ожидания refresh-токена и единый код для обоих источников.
5. **Account-linking при email-collision:** если Keycloak-логин происходит для email, у которого `keycloak_id IS NULL` (то есть запись была локальной — например bootstrap-admin), `_upsert_user()` обновляет `keycloak_id`, переводит `auth_source → "keycloak"`, обнуляет `password_hash`, **сохраняет существующую роль** (важно для bootstrap-admin) и пишет `auth.account_linked` в логи как warning. Никакого silent-merge: событие явно аудируется.
6. **Bootstrap-race:** при `--workers ≥ 2` несколько процессов могут одновременно попытаться создать первого admin. `_bootstrap_admin()` оборачивается в `pg_advisory_xact_lock(0x504F5254414C0001)` — только один воркер выполняет вставку, остальные видят commit и выходят по idempotency-проверке.
7. **Login error-unification:** `POST /auth/local/login` отвечает **унифицированным 401** на любой негативный исход (нет user enumeration). Различие фиксируется в server-side log (`reason ∈ {no_user, wrong_source, bad_password}`).
8. **Rate-limit identifier — `X-Real-IP`** (выставляется nginx, см. `app/core/limiter.py::real_ip_identifier`). `X-Forwarded-For` напрямую не используется — клиент может его подделать и обойти лимит 5/15 мин.

**Альтернативы и почему отклонены:**
- Хранить JWT в cookie — невозможно безопасно ротировать, размер cookie + риск CSRF-leak в URL-логах ≥ Redis-сессии.
- Роль в JWT — теряется мгновенность изменения admin-действиями, и для local-аккаунтов нет JWT.
- SameSite=Strict — ломает OIDC redirect, протестировано.
- `with_for_update(User)` для bookmarks reorder — ставил блокировку на не-ту таблицу; заменено на `pg_advisory_xact_lock(BOOK_NS, user_hash)`.

**Последствия:**
- Один источник правды для роли — БД. Документировано в `docs/roles-matrix.md`.
- API endpoints локальной auth: `POST /auth/local/login`, `PATCH /users/me/password`, `POST /users/admin/local`, `PATCH /users/admin/{id}/password`. Namespace для admin-операций единый: `/api/v1/users/admin/*`.
- При откате местами Keycloak ↔ local не возникает дубликатов и потери привилегий — account-linking гарантирует уникальность по email.

---

## ADR-019: Настройки оформления — файловый store без БД

**Статус:** Принято (Step 6.8)

**Контекст:**
Система оформления (branding) включает текстовые настройки (`portal_name`, `accent_color`, `banner_*`, ...) и бинарные файлы (логотип, favicon, фон). Требуется простая персистентность без overhead новой таблицы и миграции.

**Решение:**
- Бинарные файлы хранятся в `/data/branding/` на volume Docker (`./branding_data:/data/branding`)
- Текстовые настройки — `settings.json` в той же папке (Pydantic `model_validate_json` / `model_dump_json`)
- GET-эндпоинты (`/branding/settings`, `/branding/logo`, ...) — **публичные** (без JWT): нужны до авторизации (фон логина, название вкладки)
- PUT/POST/DELETE-эндпоинты (`/admin/branding/...`) — только `admin`
- Nginx всё равно ограничивает доступ по IP/VPN

**Альтернативы:**
- PostgreSQL-таблица `branding_settings` — избыточно для ~10 ключей, требует Alembic-миграции
- Redis — не персистентен без RDB/AOF, усложняет операции с бинарными файлами
- Env-переменные — не изменяются в runtime, требуют restart контейнера

**Последствия:**
- Бэкап: `branding_data/` включается в общую backup-процедуру (rsync/tar)
- Файлы сбрасываются в дефолт при удалении volume — отдельный том задокументирован в `docker-compose.yml`
- Горизонтальное масштабирование бэкенда требует shared volume (NFS/S3-fuse) — приемлемо для self-hosted 300 пользователей

---

## ADR-020: Admin UI как единая точка конфигурации

**Статус:** Принято (апрель 2026)

**Контекст:**
Первоначально конфигурация портала (Keycloak URL/secrets, Nextcloud URL, разрешённые CIDR, лимиты файлов, уровень логирования, TLS-сертификат) задавалась через `.env`-переменные и требовала рестарта контейнеров при изменении. Для self-hosted решения на 300 пользователей это неудобно: системный администратор не всегда имеет доступ к серверу.

**Решение:**
Все runtime-изменяемые настройки вынесены в Admin UI портала (`/admin`) и персистируются в JSON-файлах на volumes. При старте контейнер читает `.env` только для секретов (пароли БД, Redis), а операционные настройки — из JSON. Изменение настроек через UI применяется без рестарта.

Разделение по группам:

| Группа | Файл | Endpoint |
|--------|------|----------|
| Системные (Nextcloud, CIDR, лимиты, логирование) | `/data/settings/system.json` | `PUT /admin/system/settings` |
| Keycloak (OIDC клиент, sync клиент) | `/data/secrets/keycloak-settings.json` (`chmod 0600`) | `PUT /admin/keycloak/settings` |
| TLS-сертификат | `/data/certs/portal.crt` + `portal.key` | `POST /admin/system/tls/cert` |
| Оформление (branding) | `/data/branding/settings.json` | `PUT /admin/branding/settings` |
| Email (SMTP) | `/data/branding/email-settings.json` | `PUT /admin/branding/email/settings` |

**Разделение публичных ресурсов и секретов:**
- `/data/branding/` — публичные файлы оформления (логотип, favicon, фон входа, текстовые настройки, SMTP-конфиг без пароля отдаваемого наружу).
- `/data/secrets/` — только файлы, содержащие секреты клиентов IdP (`keycloak-settings.json` с `chmod 0600`). Отдельный volume — чтобы не раздавать их через Nginx `/media/` и иметь более строгие права.
- При наличии legacy-файла `/data/branding/keycloak-settings.json` он мигрируется в `/data/secrets/` при первом чтении (idempotent).

**Валидация входа на стороне админ-API:**
- `allowed_cidr` парсится через `ipaddress.ip_network()` — невалидная запись возвращает 422 без перегенерации Nginx-конфига (иначе падал бы Nginx reload).
- Секреты (OIDC/sync/SMTP-password/NC service password) следуют единой семантике: `null` / `"***"` — оставить, `""` — очистить, новое значение — записать. Маска `"***"` в GET-ответах защищает от утечек в UI-скриншотах и журналах браузера.

**Nginx и TLS:**
- При изменении `max_upload_size_mb` или `allowed_cidr` бэкенд автоматически перегенерирует `limits.conf` и `allowlist.conf` в `/data/nginx-conf/` и создаёт файл-триггер в `/data/nginx/reload-trigger`.
- Nginx entrypoint (`entrypoint.sh`) постоянно опрашивает триггер и выполняет `nginx -s reload` без рестарта контейнера.
- TLS-сертификат и ключ загружаются через Admin UI; после загрузки автоматически триггерится reload.

**Синхронизация Keycloak:**
- Для синхронизации пользователей используется **отдельный** сервисный клиент Keycloak (`sync_client_id` / `sync_client_secret`), которому назначена роль `realm-management → view-users`. Это изолирует синхронизацию от OIDC-потока авторизации пользователей и не требует административного аккаунта Keycloak.
- Синхронизация запускается вручную через `POST /admin/users/sync` или по расписанию ARQ-cron.
- Последний результат синхронизации кэшируется в Redis (`kc:sync_last_run`) и доступен через `GET /admin/keycloak/sync/status`.
- Проверка подключения OIDC и sync-клиентов: `POST /admin/keycloak/test/oidc` и `POST /admin/keycloak/test/sync`.

**Volumes (локальные директории вместо named volumes):**
Все тома объявлены как локальные директории (`./название_data:/path/in/container`) в корне репозитория. Это даёт предсказуемое расположение данных для бэкапа и git-ignore.

| Директория | Назначение |
|-----------|-----------|
| `./postgres_data` | PostgreSQL WAL и данные |
| `./redis_data` | Redis RDB snapshot |
| `./avatars_data` | Аватары пользователей |
| `./news_media_data` | Медиа новостей |
| `./branding_data` | Файлы оформления + Email settings |
| `./secrets_data` | `/data/secrets/` — keycloak-settings.json (`chmod 0600`) |
| `./link_icons_data` | Иконки ярлыков |
| `./settings_data` | Системные настройки (system.json) |
| `./nginx_conf_data` | Генерируемые конфиги Nginx (limits.conf, allowlist.conf) |
| `./nginx_reload_data` | Триггер reload для Nginx |
| `./certs_data` | TLS-сертификат и ключ |

**Альтернативы:**
- Хранение в PostgreSQL-таблице `system_settings` → избыточно, требует Alembic-миграции при добавлении поля, усложняет bootstrap без БД.
- Оставить только `.env` → требует перезапуска контейнеров при любом изменении настройки, неудобно для оператора.
- Consul/etcd → избыточно для self-hosted 300 пользователей.

**Последствия:**
- Секреты инфраструктуры (POSTGRES_PASSWORD, REDIS_PASSWORD, SECRET_KEY) по-прежнему в `.env` — они неизменны в runtime.
- JSON-файлы настроек должны быть включены в backup-процедуру вместе с volumes.
- При первом запуске без `system.json` используются значения из `.env` / defaults; после первого сохранения через UI — JSON становится источником правды.
- Кэш настроек в памяти (TTL 60 сек) — изменения применяются с задержкой до 1 минуты без явного триггера.

---

## ADR-021: Cookie Secure определяется по X-Forwarded-Proto, а не ENVIRONMENT

**Статус:** Принято (апрель 2026)

**Контекст:**
Cookie сессии `portal_session` ставился с флагом `Secure=True` когда `ENVIRONMENT=production`. По умолчанию портал запускается на HTTP (без TLS), а TLS включается позже через Admin UI. При первом запуске с `ENVIRONMENT=production` и HTTP-nginx браузер молча отбрасывал Secure-куку — логин возвращал 200, но последующий `GET /auth/me` отвечал 401, потому что кука не доходила до сервера.

**Решение:**
Флаг `Secure` теперь выставляется динамически по заголовку `X-Forwarded-Proto`, который nginx проставляет в зависимости от фактического протокола соединения:

```python
_proto = request.headers.get("X-Forwarded-Proto", request.url.scheme)
resp.set_cookie(secure=_proto == "https", ...)
```

Это корректно работает в обоих режимах:
- HTTP-только (по умолчанию) → `Secure=False` → кука устанавливается и работает
- После включения TLS через Admin UI → nginx ставит `X-Forwarded-Proto: https` → `Secure=True` → кука доступна только по HTTPS

Изменение применено к обоим точкам выдачи куки: OIDC callback (`/auth/callback`) и local login (`/auth/local/login`).

**Альтернативы:**
- Оставить `Secure` зависящим от `ENVIRONMENT=production` и требовать TLS при первом запуске → неудобно, противоречит подходу «сначала HTTP» из ADR-020.
- Убрать `Secure` совсем → небезопасно при работе по HTTPS.
- Читать настройку TLS из `system.json` → coupling между auth и system-settings модулями, сложнее тестировать.

**Последствия:**
- При работе по HTTP кука не имеет `Secure` — это допустимо для внутренней сети/VPN (портал недоступен из интернета по ADR-001).
- Нет необходимости перезапускать контейнеры при смене HTTP → HTTPS: nginx начинает проксировать с `X-Forwarded-Proto: https`, и следующий логин автоматически получает `Secure`-куку.
- Существующие HTTP-сессии продолжают работать до истечения TTL (8 часов), затем пользователи перелогиниваются с правильным флагом.

---

## ADR-022: Явная регистрация HEAD на branding file-эндпоинтах

**Статус:** Принято (апрель 2026)

**Контекст:**
Фронтенд (`branding.ts`, `LoginPage.vue`, `AppLayout.vue`, `AdminPage.vue`) проверяет наличие кастомного логотипа, favicon и фона входа через `HEAD`-запросы перед их отображением. Это стандартный паттерн: HEAD дешевле GET (нет тела), и позволяет корректно разделить «файл не загружен» (404) от «файл есть» (200).

FastAPI/Starlette должен автоматически добавлять HEAD-маршрут при регистрации GET. Однако на практике (FastAPI 0.115 + Starlette) три эндпоинта возвращали `405 Method Not Allowed` на HEAD-запросы.

**Решение:**
Три эндпоинта переведены с `@router.get(...)` на `@router.api_route(..., methods=["GET", "HEAD"])` с явной обработкой HEAD:

```python
@router.api_route("/branding/favicon", methods=["GET", "HEAD"])
async def get_favicon(request: Request) -> Response:
    fav = _find_file("favicon", _FAVICON_EXTS)
    if not fav:
        raise HTTPException(status_code=404, ...)
    mime = ...
    if request.method == "HEAD":
        return Response(headers={"Content-Type": mime, "Cache-Control": "public, max-age=3600"})
    return FileResponse(fav, ...)
```

Дополнительно добавлен `"HEAD"` в `allow_methods` CORS-middleware (был `["GET", "POST", "PUT", "PATCH", "DELETE"]`).

**Семантика HEAD для этих эндпоинтов:**
- `200` + заголовки (без тела) — файл загружен, фронт устанавливает URL и рендерит
- `404` — файл не загружен, фронт использует SVG-дефолт / системный favicon

**Альтернативы:**
- Добавить флаги `has_logo`, `has_favicon`, `has_login_bg` в ответ `GET /branding/settings` → требует изменения схемы и логики settings-endpoint; HEAD-подход более REST-идиоматичен.
- Всегда делать GET вместо HEAD → лишняя передача бинарного тела при каждой инициализации страницы.

**Последствия:**
- `GET /branding/logo|favicon|login-bg` сигнатура не изменилась — обратная совместимость сохранена.
- HEAD-запросы не логируются как Warning (405 убран), что снижает шум в логах.

---

## ADR-018: bcrypt SHA256 pre-hash для длинных паролей

**Статус:** Принято (Phase 2.1 / закрытие P1-17)

**Контекст:**
bcrypt молча обрезает входной пароль до 72 байт. Для UTF-8 это 18-72 видимых символа в зависимости от языка. Стандартное поведение: длинный пароль → silent truncation → две разные строки могут совпасть, если их первые 72 байта равны.

**Решение:**
Перед `bcrypt.hashpw()` пароль пропускается через `base64(sha256(password.encode("utf-8")))` — фиксированные 44 байта, всегда умещающиеся в bcrypt input-limit.

```python
# backend/app/core/security.py::_prepare_password
raw = hashlib.sha256(password.encode("utf-8")).digest()
return base64.b64encode(raw)
```

**Альтернативы:**
- Argon2id — лучший выбор для новых проектов, но заявлен `bcrypt` в requirements.md. Потребует доп. зависимости и миграции хешей.
- Жёсткое ограничение длины пароля в схеме (≤ 72 байт ASCII) → плохой UX, нарушение OWASP ASVS V2.1.7 (≥ 64 символа).
- Голый `bcrypt.hashpw(password.encode())` → silent truncation, угроза collision.

**Последствия:**
- Хеши **несовместимы** с другими bcrypt-инструментами/системами (htpasswd, passlib без явного pre-hash). Ничего не обещаем экспортировать — мы единственный потребитель.
- Если в будущем переходим на Argon2id — миграция через двойную проверку (старые хеши = bcrypt(sha256+b64), новые = argon2) + ленивый rehash при логине.
- Документировано в OpenAPI как «password: string, min_length: 8» — без особенностей хранения.

---

## ADR-023: SSE per-user connection limit через Redis sorted set

**Статус:** Принято (апрель 2026, review follow-up)

**Контекст:**
`GET /notifications/stream` открывает долгоживущий SSE-коннект. Без ограничения злоумышленник (или бажный клиент) может открыть сотни коннектов от одного пользователя → exhaustion backend worker-слотов (uvicorn async concurrency, Redis connections) и DoS.

**Решение:**
Используется Redis sorted set `sse:conn:{user_id}` со score = `now + TTL`, где:
- `ZREMRANGEBYSCORE` удаляет истёкшие записи (self-cleaning, не нужен фоновый GC);
- `ZCARD` считает активные соединения;
- Если `ZCARD ≥ MAX (5)` → `429 Too Many Requests`;
- Иначе `ZADD` регистрирует новый `connection_id = uuid4().hex` с TTL 60 сек;
- Keepalive-тик (каждые 20 сек) обновляет score через `ZADD` — продлевает TTL пока соединение живо;
- В `finally` — `ZREM` по `connection_id` снимает запись при любом завершении (клиент отключился, исключение и т.д.).

**Альтернативы:**
- Simple counter (`INCR`/`DECR`) — не самоочищается при краше процесса/сети: счётчик навсегда застревает в завышенном значении.
- Python in-memory dict — не работает при нескольких backend replicas.
- NGINX `limit_conn` — ограничивает по IP, не по user_id; не различает разные вкладки одного пользователя.

**Последствия:**
- Масштабируется горизонтально: все backend replicas видят одно состояние через Redis.
- TTL-подход толерантен к сбоям: если процесс убит до `finally`, запись истечёт через 60 сек.
- MAX=5 покрывает типичные сценарии (мобильный + 2-3 вкладки на десктопе), можно перенастроить через константу.

---

## ADR-024: SSRF-guard на user-supplied Keycloak URL

**Статус:** Принято (апрель 2026, review follow-up)

**Контекст:**
Admin UI позволяет менять `keycloak_url` через `PUT /admin/keycloak/settings`. Test-endpoints (`/admin/keycloak/test/oidc`, `/admin/keycloak/test/sync`) делают HTTP-запросы к этому URL. Хотя эндпоинт доступен только admin-роли, компрометация одного admin-аккаунта превращает бэкенд в SSRF-прокси во внутреннюю сеть: AWS metadata (`169.254.169.254`), внутренние БД, сервисы без аутентификации.

**Решение:**
`_validate_keycloak_url(url)` вызывается **до** сохранения в `PUT` и **перед** каждым исходящим запросом в test-endpoints. Проверки:
1. `scheme ∈ {http, https}` — режем `file://`, `gopher://`, `ftp://`.
2. `hostname` непустой.
3. Hostname не в `{localhost, ip6-localhost, ip6-loopback}` (литералы).
4. Если hostname — IP-литерал: отвергаем `loopback` / `link-local` / `multicast` / `unspecified`.
5. Блокируется `169.254.169.254` (AWS/GCP metadata endpoint).

Private-диапазоны (10/8, 172.16/12, 192.168/16) **разрешены** намеренно — Keycloak в типичной on-prem топологии живёт именно во внутренней сети за VPN.

**Альтернативы:**
- Whitelist доменов — слишком жёстко для self-hosted сценариев с разными окружениями.
- DNS resolution + IP-check перед запросом — усложняет логику, всё равно не защищает от DNS rebinding без pin-resolver.

**Последствия:**
- Ошибка валидации возвращается как `400 Bad Request` с понятным текстом — admin видит причину отказа в UI.
- При изменении стека (переезд Keycloak на managed cloud) список `host == "169.254.169.254"` нужно расширить Azure/Oracle metadata endpoints.

---

## ADR-025: CSRF defense-in-depth — Origin strict-match + Double-Submit Cookie

**Статус:** Принято (апрель 2026, review follow-up, дополняет ADR-013)

**Контекст:**
ADR-013 фиксировал CSRF-защиту через SameSite=Strict + проверку Origin/Referer. Ревью показало: (а) сравнение `origin.startswith(portal_base_url)` ломается на `https://portal.company.local.evil.com` (prefix match); (б) Origin-only уязвим к browser bug'ам и sub-domain takeover.

**Решение:**
1. **Strict origin parsing:** `urlparse(origin)` + сравнение `scheme` и `netloc` (case-insensitive) с `urlparse(portal_base_url)`. Никаких substring/startswith.
2. **Double-Submit Cookie:** safe-response выставляет JS-readable cookie `XSRF-TOKEN`. SPA через `ofetch` interceptor копирует значение в заголовок `X-XSRF-TOKEN` на всех unsafe-запросах. Middleware сравнивает cookie ↔ header (constant-time-ish string compare).
3. **Exempt paths:** только `/api/v1/auth/callback` (OIDC redirect), `/api/v1/auth/local/login` (pre-session), `/api/v1/auth/logout` (front-channel GET) — они выполняются до установки куки.
4. **Frontend uploads:** все multipart загрузки идут через `apiUpload` helper, который наследует interceptor от `api`. Никаких raw `fetch()` в админских формах.

**Последствия:**
- Защита работает даже если SameSite не поддерживается (старый Safari, embedded webviews).
- Double-submit cookie автоматически обновляется при каждом safe-запросе — не истекает для активной сессии.
- Любой новый multipart-эндпоинт в админке ОБЯЗАН использовать `apiUpload`. Проверено для TLS upload (P0-фикс).

---

## ADR-026: Immich как self-hosted фотогалерея

**Статус:** Принято (апрель 2026, Step 8.5)

**Контекст:**
Корпоративный портал должен показывать виджет с актуальными корпоративными фотографиями. Нужен self-hosted фотохостинг с поддержкой OIDC SSO и API доступа.

**Решение:**
- Immich (AGPL-3.0, последняя стабильная версия `release`) разворачивается в отдельных контейнерах (`immich-server`, `immich-postgres` с pgvecto-rs).
- `immich-machine-learning` вынесен в Docker Compose profile `ml` — не запускается по умолчанию, подключается при необходимости.
- Портал обращается к Immich через **сервисный API-ключ** (`IMMICH_API_KEY`). Thumbnail-прокси и листинг альбома — исключительно backend-to-backend.
- **Graceful fallback:** если `enabled=false` или пустые `api_key`/`corp_album_id` — `GET /photos/recent` возвращает `{"configured": false, "items": []}`, виджет на фронте скрывается без ошибки.
- **Disk-кэш thumbnails:** `/data/cache/immich/{sha256(asset_id)}.jpg`. Кэш бессрочный (изображения не меняются). `Cache-Control: public, max-age=3600` для браузера.
- `corp_album_id` вводится вручную в Admin UI после первого запуска Immich.

**Альтернативы:**
- NextCloud Photos — не подходит: нет нативного API для корпоративного album sharing.
- Google Photos / Яндекс Диск — отклонено: данные покидают периметр.
- Прямой iframe на photos.portal — отклонено: CSP сложности, нет thumbnail proxy.

**Последствия:**
- `IMMICH_DB_PASSWORD` остаётся в `.env` (пароль БД Immich-postgres). Все остальные настройки — Admin UI → Модули (ADR-028).
- Nginx: отдельный server block `photos.portal.company.local → immich-server:2283`. Immich не поддерживает sub-path routing.
- При обновлении Immich API (версии часто ломают `/api/albums/{id}/assets`) — обновить `photos.py`.

---

## ADR-027: PeerTube как self-hosted видеохостинг + iframe embed в редакторе

**Статус:** Принято (апрель 2026, Step 8.6)

**Контекст:**
Портал должен показывать корпоративные видео и позволять вставлять видео-embed в статьи KB и новости через TipTap-редактор.

**Решение:**
- PeerTube (AGPL-3.0) уже развёрнут в инфраструктуре. SSO реализуется через плагин `peertube-plugin-auth-openid-connect`.
- **Доступ к API:** сервисный аккаунт `portal-svc` (Role: User) + OAuth2 password grant (`client_id`/`client_secret` + логин/пароль). Токен кэшируется в памяти процесса (`expires_in - 60` сек); при рестарте backend — перезапрашивается автоматически.
- **Видео-embed в TipTap:** кастомный Node `IframeEmbed` с whitelist доменов. Только PeerTube domain (`VITE_PEERTUBE_URL`) разрешён через DOMPurify hook — YouTube и другие сервисы блокируются.
- **Disk-кэш thumbnails:** `/data/cache/peertube/` по аналогии с Immich.
- **CSP:** `frame-src` и `media-src` расширяются на `https://video.company.local` в Nginx.
- `GET /videos/config` возвращает `public_url` фронту для формирования iframe src без хардкода.

**Альтернативы:**
- YouTube/Vimeo embed — отклонено: данные вне периметра, нет контроля доступа.
- MinIO + HLS плеер — отклонено: нет UI загрузки, транскодинга, каталога.
- Jellyfin — отклонено: нет нативного iframe embed, слабый API.

**Последствия:**
- `client_id`/`client_secret` получаются через `curl /api/v1/oauth-clients/local` после первого запуска.
- В-памяти кэш токена теряется при рестарте — первый запрос после рестарта делает OAuth2 roundtrip (≈100 мс, несущественно).
- Iframe embed DOMPurify hook должен обновляться при смене PeerTube domain — константа `VITE_PEERTUBE_URL` в `.env` фронта.

---

## ADR-028: Модули — Admin UI управление внешними интеграциями

**Статус:** Принято (апрель 2026, Step 8.7)

**Контекст:**
Изначально настройки Immich и PeerTube закладывались как env-переменные (Step 8.5/8.6). Но при эксплуатации это создаёт необходимость рестарта контейнеров при изменении API-ключей, album ID и других параметров. Паттерн runtime-настроек через Admin UI уже применён для Keycloak (ADR-020), SMTP, системных настроек.

**Решение:**
- Новый файл `/data/settings/modules.json` (chmod 0600) хранит настройки всех внешних модулей. Структура: `{ "immich": {...}, "peertube": {...}, "nextcloud": {...} }`.
- TTL-кэш в памяти 60 сек — изменения применяются к следующему запросу без рестарта.
- **Env-fallback:** при первом запуске без `modules.json` — читаются env-переменные `IMMICH_*`/`PEERTUBE_*` для начального посева. Это обеспечивает обратную совместимость при миграции с предыдущего деплоя.
- **Маскировка секретов:** `api_key`, `client_secret`, `svc_password` никогда не возвращаются в GET-ответах. Вместо них — `api_key_set: bool`. В PUT-запросах: `null`/`"***"` = сохранить; `""` = очистить; новое значение = обновить.
- **Nextcloud** — placeholder (`enabled` флаг только). Полная настройка через Admin UI → Система. Данный ADR резервирует место для будущей полной интеграции.
- Паттерн расширяется: будущие модули (мессенджер, JIRA, etc.) добавляются в `AllModuleSettings` и отображаются в той же вкладке Admin UI.

**Альтернативы:**
- Оставить в env — отклонено: рестарт контейнера при смене API-ключа; нет UI для оператора.
- PostgreSQL таблица — избыточно: нет реляционных зависимостей; файл проще и не требует миграции.
- Redis — отклонено: volatile; данные теряются при рестарте Redis.
- Один общий `system.json` — отклонено: иная семантика (Nextcloud, CIDR, TLS); смешивание усложняет эволюцию схемы.

**Последствия:**
- `IMMICH_DB_PASSWORD` остаётся в `.env` (пароль БД Immich-postgres — не runtime-настройка, нужен при старте контейнера).
- `backend` и `worker` монтируют volume `settings_data:/data/settings`.
- При компрометации `modules.json` — все API-ключи к Immich и PeerTube скомпрометированы. Рекомендация: volume доступен только внутри Docker network.

---

## ADR-029: Test-connection endpoints для модулей + инвалидация OAuth-кэша

**Статус:** Принято (апрель 2026, после ревью Step 8.7)

**Контекст:**
После перевода Immich/PeerTube на runtime-настройки (ADR-028) обнаружены две эксплуатационные проблемы:
1. **Нет обратной связи в UI**: admin заполняет URL/API-ключ/Album UUID, сохраняет — и узнаёт о неправильной конфигурации только через отсутствие данных в виджете главной страницы (без диагностики).
2. **Stale OAuth-токен PeerTube**: `app.api.videos._token_cache` — глобальный кэш access-токена (TTL = `expires_in - 60`). При смене `client_id`/`client_secret`/`svc_password` через Admin UI старый токен продолжал использоваться до истечения TTL (до часа). Симптом: «сохранил новые креды, но виджет всё ещё возвращает 401/пустой список».

**Решение:**
- Добавлены `POST /admin/modules/immich/test` и `POST /admin/modules/peertube/test` (только admin) — проверяют сохранённые настройки и возвращают структурированный отчёт (`server_ok`/`version`/`album_ok`/`album_name`/`asset_count` для Immich; `token_ok`/`videos_total` для PeerTube).
- В `_save_modules()` вызывается `_invalidate_module_caches()` — чистит `videos._token_cache` после каждого PUT. Публичный helper `invalidate_modules_cache()` экспортирован для тестов.
- Атомарная запись `modules.json` через `tempfile.mkstemp` + `chmod 0600` на временном файле + `os.replace` — исключает race между создателем файла и `chmod`.
- Повреждённый `modules.json` логируется (`modules.settings_parse_failed`), а не молча игнорируется.

**Альтернативы:**
- Валидировать в PUT и отдавать ошибку сразу — отклонено: PUT сохраняет конфигурацию (в т.ч. «disabled, но с заполненными полями»), валидация смешивает ответственность. Отдельный test-endpoint симметричен Keycloak/SMTP.
- TTL=0 для OAuth-кэша — отклонено: при каждой загрузке виджета 2 запроса к PeerTube (token + videos).
- Event-bus для инвалидации — избыточно: один процесс backend, простой `dict.clear()` достаточно.

**Последствия:**
- Admin видит диагностику сразу («✓ server reachable (v1.119.0) · album «Корп.альбом» (42)»).
- Смена OAuth-кредов PeerTube применяется к следующему запросу — без ожидания TTL.
- UI: кнопки «Проверить соединение» видны только при `enabled=true` (иначе тестить нечего).
- Nextcloud — toggle заблокирован (disabled) с `n-alert` о Phase 5. Оператор не может ошибочно включить модуль без эффекта.
