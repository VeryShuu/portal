# Architecture Decision Records (ADR)

> Корпоративный интранет-портал
> Последнее обновление: апрель 2026

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

**Применение:** login brute force (5/мин/IP), search (30/мин/user), file upload (10/мин/user), export PDF/DOCX (5/мин/user), остальное (120/мин/user)

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
