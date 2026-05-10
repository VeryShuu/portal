# Architecture Decision Records (ADR)

> Корпоративный интранет-портал
> Последнее обновление: май 2026 (ADR-035 — silent refresh; ADR-036 — auto-SSO; ADR-037 — bootstrap env / runtime system.json)

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

**Статус:** ~~Принято~~ → **Заменено ADR-032** (апрель 2026)

Исходный Вариант B (impersonation per-user JWT) отклонён после анализа требований: файловый модуль портала хранит **общие корпоративные файлы**, а не личные файлы пользователей. Impersonation не применим — нет смысла проксировать файлы от имени конкретного пользователя, если все работают с единым деревом. См. ADR-032.

---

## ADR-032: Nextcloud — service account (Вариант A)

**Статус:** Принято (апрель 2026, заменяет ADR-002)

**Контекст:**
Файловый модуль портала предоставляет **единое корпоративное файловое хранилище** для ~300 сотрудников. Пользователи заходят в раздел «Файлы» и видят общие файлы организации — не личные папки в Nextcloud. Права доступа (кто что видит и редактирует) определяются ролями на портале, а не ACL Nextcloud. Вариант B (impersonation через JWT пользователя) не применим: нет индивидуальных пользовательских папок, нет смысла проксировать WebDAV от имени каждого.

**Решение:**
Все файловые операции (листинг, скачивание, загрузка) выполняются через единый service account `portal-svc` с **App Password** (`NC_SERVICE_APP_PASSWORD`). Nextcloud используется как тупое хранилище. Права доступа — исключительно в БД портала (таблица `file_permissions`). Keycloak `user_oidc` app для файлового модуля **не требуется**.

**Аутентификация в NC:** `Authorization: Basic base64(portal-svc:APP_PASSWORD)` — не JWT, не Keycloak.

**WebDAV path:** `/remote.php/dav/files/portal-svc/` — фиксирован.

**Скачивание:** `httpx.stream() → StreamingResponse` (не OCS share-ссылки)

**Upload:** `frontend → backend → WebDAV PUT` streaming, не буферизация:
```python
async def upload_file(self, target_path: str, stream: AsyncIterator[bytes]) -> None:
    async with httpx.AsyncClient(timeout=self.TIMEOUT_UPLOAD) as client:
        await client.put(webdav_url, headers={"Authorization": f"Basic {self._basic_auth}"}, content=stream)
```

**httpx таймауты:**
- Листинг/метаданные: 10 сек
- Скачивание: без таймаута (`None`)
- Загрузка: 600 сек
- Health check (`/status.php`): 3 сек

**Collabora (совместное редактирование):**
1. Backend запрашивает Collabora-URL у NC через OCS API (от portal-svc)
2. NC генерирует WOPI-токен → возвращает `{ url, token }`
3. Frontend открывает `window.open(url, '_blank')` — Collabora работает напрямую с NC через WOPI
4. `display_name` пользователя портала передаётся через WOPI — в документе видно реальное имя
5. Сохранение происходит в NC через WOPI — бэкенд портала не стоит в цепочке

**Audit trail:** каждая операция логируется в `audit_log` с `user_id` из Redis-сессии портала.

**Альтернативы:**
- Вариант B (impersonation JWT) → отклонено: портал работает с общими файлами, не персональными; `user_oidc` — лишняя зависимость; сложность с `NC_USER_ID_FIELD` (TBD от инженера) блокировала разработку
- OCS временные share-ссылки → отклонено: TTL работает в днях; мусор в БД Nextcloud
- MinIO/S3 → отклонено: теряется встроенная интеграция Nextcloud + Collabora Online

**Последствия:**
- `NC_USER_ID_FIELD` env-переменная **не нужна** — WebDAV путь фиксирован
- Keycloak `user_oidc` app в Nextcloud не требуется для файлового модуля (может быть нужен для других задач)
- Audit trail в NC некорректен (все операции от `portal-svc`) — это принято как компромисс; правильный audit — в таблице `audit_log` портала
- Ротация App Password: при смене `NC_SERVICE_APP_PASSWORD` — только рестарт backend-контейнера (или hot-reload если вынесено в Admin UI)
- Требует создания пользователя `portal-svc` в Nextcloud вручную до деплоя

---

## ADR-003: Хранение аватаров в local volume (не PostgreSQL BYTEA, не Nextcloud)

**Статус:** Принято

**Контекст:**
Нужно хранить аватары ~300 пользователей.

**Решение:**
Local Docker volume `./upload_data/avatars`, примонтированный в `/data/avatars/` контейнера backend. Nginx отдаёт статику напрямую (`location /static/avatars/`). В PostgreSQL хранится только `avatar_url VARCHAR(512)`.

**Альтернативы:**
- `BYTEA` в PostgreSQL → отклонено: раздувает WAL, тяжёлые бэкапы, IO деградация
- Nextcloud `/avatars/{user_id}/` → отклонено: service account не разграничивает доступ корректно; Nextcloud — для документов, не статики
- MinIO/S3 → отклонено: избыточно для 300 × 200 КБ ≈ 60 МБ

**Последствия:**
- При горизонтальном масштабировании backend потребуется shared volume или смена на MinIO (v2)
- Бэкап: volume включается в инфраструктурный backup-сценарий (см. `docs/deploy.md` §7)

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

**Санитизация:** `nh3` (Rust-based, быстрее bleach, bleach признан устаревшим) на бэкенде запрещает raw HTML в MD перед сохранением.

**Вставка изображений:**
- Кнопка тулбара → модалка файлового браузера Nextcloud → `![alt](url)`
- Ctrl+V скриншота → автозагрузка в Nextcloud (PUT через бэкенд) → вставка ссылки

**Альтернативы:**
- Только Markdown → отклонено: плохой UX для нетехнических пользователей
- TipTap с HTML-хранением → отклонено: сложная санитизация, тяжёлый diff в версионировании
- ProseMirror напрямую → отклонено: избыточная сложность

**Ограничения:** без resize изображений, без custom embeds — только CommonMark/GFM

---

## ADR-006: PDF-экспорт через выделенный screenshot-service (Playwright/Chromium)

**Статус:** Принято (обновлено — Chromium вынесен из бэкенда)

**Контекст:**
Нужен экспорт статей KB в PDF с поддержкой CSS и корректным рендером.
Изначально Playwright запускался внутри бэкенд-контейнера, что добавляло ~300 МБ к его образу
и создавало операционные риски (Chromium в production-процессе FastAPI).

**Решение:** Playwright/Chromium (`page.pdf()`) вынесен в отдельный `screenshot-service`.
Бэкенд делает `POST /pdf` с HTML-телом и получает PDF-байты в ответ (`httpx.AsyncClient`).
Сервис также отдаёт скриншоты страниц через `GET /screenshot?url=...`.

**Альтернативы:**
- WeasyPrint → отклонено: зависимости Cairo/Pango/GObject (~400 МБ в Docker образе)
- xhtml2pdf → отклонено: слабая поддержка CSS, артефакты рендеринга
- wkhtmltopdf → отклонено: устаревший, плохая поддержка современного CSS
- Playwright внутри бэкенда → отклонено: +300 МБ к образу, Chromium в WSGI-процессе нежелательно

**Преимущества выделенного сервиса:**
- Бэкенд-образ легче (~300 МБ экономии)
- Chromium изолирован — краши/OOM не роняют API
- Сервис масштабируется независимо от бэкенда
- Возможна повторная инициализация без перезапуска бэкенда

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
- Проще санитизация (запрет raw HTML через `nh3`)

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

**Статус:** Superseded by ADR-025

> Дополнен ADR-025 (Double Submit Cookie добавлен)

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

---

## ADR-019: Настройки оформления — файловый store без БД

**Статус:** Принято (Step 6.8)

**Контекст:**
Система оформления (branding) включает текстовые настройки (`portal_name`, `accent_color`, `banner_*`, ...) и бинарные файлы (логотип, favicon, фон). Требуется простая персистентность без overhead новой таблицы и миграции.

**Решение:**
- Бинарные файлы хранятся в `/data/branding/` на volume Docker (`./upload_data/branding:/data/branding`)
- Текстовые настройки — `settings.json` в той же папке (Pydantic `model_validate_json` / `model_dump_json`)
- GET-эндпоинты (`/branding/settings`, `/branding/logo`, ...) — **публичные** (без JWT): нужны до авторизации (фон логина, название вкладки)
- PUT/POST/DELETE-эндпоинты визуального оформления (`/admin/branding/settings`, `/admin/branding/logo`, `/admin/branding/favicon`, `/admin/branding/login-bg`) — `editor+`
- Email-эндпоинты (`/admin/branding/email/...`) — только `admin`
- Nginx всё равно ограничивает доступ по IP/VPN

**Альтернативы:**
- PostgreSQL-таблица `branding_settings` — избыточно для ~10 ключей, требует Alembic-миграции
- Redis — не персистентен без RDB/AOF, усложняет операции с бинарными файлами
- Env-переменные — не изменяются в runtime, требуют restart контейнера

**Последствия:**
- Бэкап: `upload_data/branding/` включается в инфраструктурную backup-процедуру (см. `docs/deploy.md` §7)
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
- При изменении `max_upload_size_mb` или `allowed_cidr` бэкенд создаёт файл-триггер в `/data/nginx/reload-trigger`. Генерацией `limits.conf` и `allowlist.conf` в `/data/nginx_conf/` занимается sidecar-контейнер `nginx-config` (alpine + jq + envsubst + inotify-tools) — он inotifies `/data/settings/system.json` и `/data/certs/`, рендерит конфиги из шаблонов в `nginx/templates/`.
- Nginx entrypoint (`entrypoint.sh`) использует `inotifywait` для наблюдения за триггером и выполняет `nginx -s reload` без рестарта контейнера.
- TLS-сертификат и ключ загружаются через Admin UI; после загрузки автоматически триггерится reload.

**Синхронизация Keycloak:**
- Для синхронизации пользователей используется **отдельный** сервисный клиент Keycloak (`sync_client_id` / `sync_client_secret`), которому назначена роль `realm-management → view-users`. Это изолирует синхронизацию от OIDC-потока авторизации пользователей и не требует административного аккаунта Keycloak.
- Синхронизация запускается вручную через `POST /admin/users/sync` или по расписанию ARQ-cron.
- Последний результат синхронизации кэшируется в Redis (`kc:sync_last_run`) и доступен через `GET /admin/keycloak/sync/status`.
- Проверка подключения OIDC и sync-клиентов: `POST /admin/keycloak/test/oidc` и `POST /admin/keycloak/test/sync`.

**Volumes (локальные директории вместо named volumes):**
Все тома сгруппированы в три корневые директории для удобства бэкапа и эксплуатации.

| Директория | Назначение |
|-----------|-----------|
| `./base_data/postgres` | PostgreSQL WAL и данные |
| `./base_data/redis` | Redis RDB snapshot |
| `./upload_data/avatars` | Аватары пользователей |
| `./upload_data/news_media` | Медиа новостей |
| `./upload_data/branding` | Файлы оформления + Email settings |
| `./upload_data/link_icons` | Иконки ярлыков |
| `./upload_data/kb` | Медиа и файлы статей базы знаний |
| `./upload_data/photos/originals` | Оригиналы фотогалереи |
| `./upload_data/photos/thumbs` | Thumbnails фотогалереи (WebP) |
| `./system_data/nginx` | nginx.conf + entrypoint.sh (source-controlled) |
| `./system_data/settings` | Системные настройки (system.json, modules.json) |
| `./system_data/secrets` | Секреты Keycloak (`chmod 0600`) |
| `./system_data/nginx_conf` | Генерируемые конфиги Nginx (limits.conf, allowlist.conf) |
| `./system_data/nginx_reload` | Триггер reload для Nginx |
| `./system_data/certs` | TLS-сертификат и ключ |

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
Фронтенд (`branding.ts`, `components/layout/AppHeader.vue`, `AdminPage.vue`) проверяет наличие кастомного логотипа, favicon и фона входа через `HEAD`-запросы перед их отображением. Это стандартный паттерн: HEAD дешевле GET (нет тела), и позволяет корректно разделить «файл не загружен» (404) от «файл есть» (200).

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
- При изменении стека (переезд Keycloak на managed cloud) список `host == "169.254.169.254"` нужно расширить:
  - **Azure**: `169.254.169.254` (IMDS) — уже блокирован; `fd00::/8` (IPv6 IMDS) — при включении IPv6 добавить в проверку.
  - **Oracle Cloud**: `169.254.169.254` (Instance Metadata) — уже блокирован.
  - **Alibaba Cloud**: `100.100.100.200` — добавить явную блокировку.
  - Для полной защиты в облачных средах рекомендуется DNS-pin + IP-check после резолвинга.

---

## ADR-025: CSRF defense-in-depth — Origin strict-match + Double-Submit Cookie

**Статус:** Принято (апрель 2026, review follow-up, дополняет ADR-013)

**Контекст:**
ADR-013 фиксировал CSRF-защиту через SameSite=Strict + проверку Origin/Referer. Ревью показало: (а) сравнение `origin.startswith(portal_base_url)` ломается на `https://portal.company.local.evil.com` (prefix match); (б) Origin-only уязвим к browser bug'ам и sub-domain takeover.

**Решение:**
1. **Strict origin parsing:** `urlparse(origin)` + сравнение `scheme` и `netloc` (case-insensitive) с `urlparse(portal_base_url)`. Никаких substring/startswith.
2. **Double-Submit Cookie:** safe-response выставляет JS-readable cookie `XSRF-TOKEN`. SPA через `ofetch` interceptor копирует значение в заголовок `X-XSRF-TOKEN` на всех unsafe-запросах. Middleware сравнивает cookie ↔ header (constant-time-ish string compare).
3. **Exempt paths:** только `/api/v1/auth/callback` (OIDC redirect), `/api/v1/auth/local/login` (pre-session), `/api/v1/auth/logout` (front-channel GET) — они выполняются до установки куки.
   - `/auth/local/login` — POST, но `XSRF-TOKEN` cookie ещё не существует на момент запроса (сессия не создана). Остаточная защита: (а) `SameSite=Lax` на session cookie блокирует кросс-сайтовые top-level POST (браузер не отправит cookie при POST от другого origin); (б) Origin/Referer строго проверяется в CSRF middleware даже для exempt-путей — запрос с посторонним Origin отклоняется с 403. (в) Endpoint не возвращает XSRF-TOKEN до успешной аутентификации — CSRF-токен присваивается только после установки сессии.
   - `/auth/callback` — инициируется редиректом от Keycloak (GET → POST), SameSite=Lax разрешает top-level навигацию. CSRF неактуален, т.к. `state` параметр OIDC выполняет аналогичную роль nonce.
   - `/auth/logout` — front-channel GET, не изменяет состояние данных, только уничтожает сессию. Идемпотентен к повторным запросам.
4. **Frontend uploads:** все multipart загрузки идут через `apiUpload` helper, который наследует interceptor от `api`. Никаких raw `fetch()` в админских формах.

**Последствия:**
- Защита работает даже если SameSite не поддерживается (старый Safari, embedded webviews).
- Double-submit cookie автоматически обновляется при каждом safe-запросе — не истекает для активной сессии.
- Любой новый multipart-эндпоинт в админке ОБЯЗАН использовать `apiUpload`. Проверено для TLS upload (P0-фикс).

---

## ADR-026: (зарезервирован/удалён)

> Этот номер ADR не используется. Зарезервирован или удалён в ходе истории документа.

---

## ADR-027: Iframe embed в редакторе (TipTap)

**Статус:** Принято (апрель 2026, Step 8.6)

**Контекст:**
Портал должен позволять вставлять видео-embed в статьи KB и новости через TipTap-редактор. Редакторы являются доверенными внутренними пользователями.

**Решение:**
- **Видео-embed в TipTap:** кастомный Node `IframeEmbed` без ограничений по домену — редакторы вставляют полный embed-код или прямую ссылку через диалог «Вставить видео». Функция `extractEmbedSrc()` парсит `src` из HTML embed-кода.
- **DOMPurify:** `sanitizeHtmlWithIframe()` разрешает `<iframe>` со всех HTTPS-источников, блокирует только `<script>`, `<style>`, event-атрибуты.
- **CSP `frame-src`:** динамически строится в `_build_nginx_csp(nextcloud_url)` (`app/services/nginx_config.py`). Значение: `'self' {scheme}://{nextcloud_netloc}` — только Nextcloud-origin для Collabora. Без configured NC URL — `'self'` только. Открытый `https:` wildcard **не используется**.
- Nginx является единственным источником CSP-заголовков; FastAPI middleware удалён — устранено через `proxy_hide_header Content-Security-Policy` (и других security-заголовков) в nginx server-блоках. `_build_csp_policy()` в `app/main.py` не используется.

**Альтернативы:**
- Whitelist конкретных видеодоменов — отклонено: избыточно для доверенных внутренних редакторов; усложняет поддержку при смене видеохостинга.
- Открытый `frame-src https:` — отклонено: clickjacking relay через произвольный HTTPS-домен; недопустимо даже для интранета.

**Последствия:**
- Collabora iframe работает при корректно прописанном `nextcloud_url` в системных настройках (Admin UI → Настройки).
- Любой HTTPS iframe может быть вставлен редактором в контент (ответственность на редакторе), но браузер заблокирует его если домен не совпадает с NC origin — это ожидаемое поведение.
- При смене `nextcloud_url` sidecar `nginx-config` автоматически перегенерирует конфиги при следующем inotify-событии на `system.json`; ручного вызова не требуется.
- Markdown-режим не поддерживает iframe — `html: true` в tiptap-markdown обязателен.

---

## ADR-028: Модули — Admin UI управление внешними интеграциями

**Статус:** Принято (апрель 2026, Step 8.7)

**Контекст:**
Настройки внешних модулей (Nextcloud, Photos) требуют runtime-изменений без рестарта контейнеров. Паттерн runtime-настроек через Admin UI уже применён для Keycloak (ADR-020), SMTP, системных настроек.

**Решение:**
- Новый файл `/data/settings/modules.json` (chmod 0600) хранит настройки всех внешних модулей. Структура: `{ "nextcloud": {...}, "photos": {...} }`.
- TTL-кэш в памяти 60 сек — изменения применяются к следующему запросу без рестарта.
- **Nextcloud** — полная интеграция реализована. Admin UI → Модули позволяет настраивать: `enabled`, `url`, `service_username`, `service_app_password`, `files_root`, `user_id_field`. Изменения применяются немедленно через invalidate кэша NC-сервиса.
- **Photos** — управляется через ту же вкладку: `enabled`, `widget_limit`, `max_size_mb`, `allowed_mime`, `strip_gps`.
- Паттерн расширяется: будущие модули (мессенджер, JIRA, etc.) добавляются в `AllModuleSettings` и отображаются в той же вкладке Admin UI.

> **Примечание (обновление май 2026):** Исходный ADR описывал Nextcloud как «placeholder». С момента принятия полная интеграция реализована — URL, App Password, Files Root и прочие параметры управляются через Admin UI.

**Альтернативы:**
- Оставить в env — отклонено: рестарт контейнера при смене API-ключа; нет UI для оператора.
- PostgreSQL таблица — избыточно: нет реляционных зависимостей; файл проще и не требует миграции.
- Redis — отклонено: volatile; данные теряются при рестарте Redis.
- Один общий `system.json` — отклонено: иная семантика (Nextcloud, CIDR, TLS); смешивание усложняет эволюцию схемы.

**Последствия:**
- `backend` и `worker` монтируют volume `./system_data/settings:/data/settings`.
- При компрометации `modules.json` — сохранённые настройки модулей скомпрометированы. Рекомендация: volume доступен только внутри Docker network.

---

## ADR-029: (зарезервирован/удалён)

> Этот номер ADR не используется. Зарезервирован или удалён в ходе истории документа.

---

## ADR-030: Собственный модуль фотогалереи

**Статус:** Принято (апрель 2026, Step 10.7–10.8).

**Контекст:**
Корпоративный портал должен показывать виджет с актуальными фотографиями и предоставлять единую иерархию папок (архив ~1 ТБ с подпапками) со следующими требованиями:
- **все сотрудники читают по умолчанию** (per-folder viewer);
- **загружать могут только выбранные пользователи/группы** (per-folder uploader);
- наследование прав вниз по дереву папок;
- виджет «свежие фото» агрегирует контент из всех доступных папок единообразно.

Готовые self-hosted решения (см. альтернативы) строятся вокруг модели «владелец ассета + shared albums» и не дают групповых прав на иерархию папок без копирования ассетов под каждого пользователя — это ломает и виджет, и usability.

**Решение:**
Реализован собственный модуль фотогалереи:
- **Модель ACL**: копия KB ACL (ADR-018 стиль) — subjects `user`/`group`, уровни `viewer`/`uploader`/`manager`, наследование от родительской папки, создатель автоматически `manager`, portal admin — override.
- **Хранение**: PostgreSQL для метаданных (`photo_folders`, `photo_folder_permissions`, `photos`), локальная ФС для оригиналов (`/data/photos/originals/`) и thumbnail'ов (`/data/photos/thumbs/{id}/{200|600|1600}.webp`).
- **Обработка**: Pillow + pillow-heif, генерация трёх размеров WebP q=85, извлечение EXIF (strip GPS по умолчанию), ARQ-pipeline `process_photo_upload`.
- **Отдача**: Nginx `X-Accel-Redirect` на internal-локации `/internal/photos-thumbs/`, `/internal/photos-originals/`; ACL-проверка на уровне backend перед редиректом; `Cache-Control: public, max-age=604800, immutable` для thumbnails, `no-store` для оригиналов.
- **Импорт ~1 ТБ**: загрузка вручную через UI после деплоя; CLI-скрипт `python -m app.scripts.import_photos` (dry-run/apply) запланирован в Step 11.
- **Admin UI**: секция «Фотогалерея» во вкладке «Модули» (toggle, widget_limit, max_size_mb, allowed_mime, strip_gps).

**Альтернативы (отклонены):**
- **Готовый self-hosted фотохостинг с per-user ассет-моделью** — требует копирования ссылок на ассеты в персональные альбомы пользователей, что несовместимо с виджетом «свежие фото» и кратно усложняет администрирование при росте архива.
- **Nextcloud Photos** — зависит от Phase 5 (Nextcloud OIDC-миграция заблокирована), нет API для групповых прав на альбомы, Collabora lock-in.
- **Piwigo** — PHP-стек, нет OIDC без платных плагинов, UX устарел.
- **PhotoPrism** — модель «всё принадлежит одному пользователю» неприменима к корпоративному архиву.
- **Прямой iframe на сторонний фотосервис** — CSP-сложности, нет thumbnail proxy, нет общей ACL-модели с порталом.

**Последствия:**
- Создана миграция `014_photos` с тремя таблицами (`photo_folders`, `photo_folder_permissions`, `photos`).
- Новые volumes: `./upload_data/photos/originals` (rw в backend/worker, ro в nginx) и `./upload_data/photos/thumbs` (то же); они в `.gitignore`.
- Конфигурация модуля полностью runtime — через Admin UI → Модули → Фотогалерея (`/data/settings/modules.json`, ключ `photos`); env-переменных у модуля нет.
- Схема прав расширяется при появлении требований, нет зависимости от upstream-roadmap стороннего продукта.

---

## ADR-031: Архитектура собственного модуля фотогалереи

**Статус:** Принято (апрель 2026, Step 10.8). Развивает ADR-030.

**Контекст:**
ADR-030 зафиксировал решение писать собственный модуль; этот ADR описывает конкретную архитектуру: схему данных, обработку медиа, отдачу файлов, Admin UI, фронтенд.

**Решение:**

1. **Схема данных (миграция `014_photos`):**
   - `photo_folders` — иерархия с самоссылкой `parent_id`, материализованный `path` (slash-separated slugs), `slug` уникален в пределах одного родителя, `created_by` FK users (owner = manager автоматически), soft-delete через `deleted_at`.
   - `photo_folder_permissions` — `subject_type ∈ {user,group}`, `subject_id` (Keycloak `sub` или group id), `permission ∈ {viewer,uploader,manager}`, уникальная пара `(folder_id, subject_id)`.
   - `photos` — `folder_id` FK, `filename` (sanitized ASCII), `original_name`, `width/height`, `taken_at`, `exif` JSONB, `processed: bool` (true после ARQ-обработки), soft-delete.
   - Поле `inherit_permissions` зарезервировано на будущее (per-photo override) — на текущей фазе всегда true.

2. **ACL-сервис (`services/photos_acl.py`):**
   - `resolve_folder_permission` идёт по дереву вверх: portal admin → manager; created_by == user → manager; иначе direct permission, потом рекурсия по `parent_id` до 20 уровней; max(perm) выигрывает; manager на любом уровне → break (выше не нужно).
   - Кэш в Redis: ключ `photos_acl:{user_id}:folder:{folder_id}`, TTL 300с; инвалидация по folder (`SCAN photos_acl:*:folder:{id}`) при grant/revoke; по user (`SCAN photos_acl:{uid}:folder:*`) при смене ролей.
   - `_subject_ids_for_user` собирает Keycloak `sub` + список групп из `users.keycloak_groups`.

3. **Storage (`services/photos_storage.py`):**
   - Originals: `/data/photos/originals/{materialized_path}/{sanitized_filename}`. Имя файла стерилизуется в ASCII через NFKD + regex `[^A-Za-z0-9._-]+` → `-`; коллизии разрешаются `_unique_name` суффиксами `-N` или sha256-хвостом.
   - Path-traversal guard: `folder_fs_path` делает `.resolve()` и проверяет `startswith(ORIGINALS_ROOT.resolve())`.
   - Thumbnails: WebP q=85, три размера 200/600/1600 (виджет / grid / lightbox), плоско по `/data/photos/thumbs/{photo_id}/{size}.webp`, ленивая регенерация после повторной загрузки невозможна — cleanup при удалении.
   - HEIC/HEIF: `pillow-heif.register_heif_opener()` лениво в `_open_image`; нативные libheif/libde265 ставятся в Dockerfile.
   - EXIF: `Pillow.ExifTags`, по умолчанию strip GPS (управляется `strip_gps` в Admin UI), парсинг `DateTimeOriginal` в `taken_at`.
   - Pipeline: `POST /upload` → save original + INSERT photo (processed=false) → `enqueue_job('process_photo_upload', id)` → ARQ генерирует thumbnails + EXIF + UPDATE width/height/taken_at/processed=true.

4. **Отдача через Nginx X-Accel-Redirect:**
   - Backend проверяет ACL и отдаёт 200 с заголовком `X-Accel-Redirect: /internal/photos-thumbs/{id}/{size}.webp` (или `/internal/photos-originals/{path}/{name}`).
   - Nginx `internal;` локации мапятся на read-only volumes `./upload_data/photos/originals:ro` / `./upload_data/photos/thumbs:ro` в nginx-сервисе.
   - Thumbnails: `Cache-Control: public, max-age=604800, immutable`. Originals: `no-store` + `X-Content-Type-Options: nosniff`.

5. **Admin UI (`/data/settings/modules.json` — ключ `photos`):**
   - `enabled` (default true), `widget_limit` (1-50, default 8), `max_size_mb` (1-500, default 50), `allowed_mime` (CSV в форме → list[str]), `strip_gps` (default true).
   - Управление через `PUT /admin/modules/photos`; политика секретов не нужна (нет полей с секретами).

6. **Frontend:**
   - `PhotosWidget.vue` (главная) — 4×N сетка thumbnails 200px, скрыт если `configured=false`.
   - `PhotosIndexPage.vue` (`/photos`) — split-layout: дерево слева (`FolderNode.vue` рекурсивно), сетка thumbnails 600px справа, lightbox 1600px с prev/next, ссылка на оригинал, info-панель с EXIF.
   - Permissions modal — простой picker (subject_type + id + name + level), без интеграции с Keycloak users-search (планируется в Phase 6 как унификация с KB).
   - Upload — multiple file input, batch по 10 файлов, прогресс-бар.

**Альтернативы:**
- **Хранить thumbnails в БД (BYTEA)** — отклонено: 1ТБ архив × 3 размера → раздувание PostgreSQL без необходимости.
- **Регенерация thumbnails on-the-fly через FastAPI** — отклонено: CPU нагрузка на каждый запрос; кэш всё равно нужен на диске.
- **S3-совместимый storage (minio)** — отклонено: лишний слой; X-Accel-Redirect напрямую с tmpfs/диска быстрее и без extra-сервиса.
- **PIL вместо Pillow-SIMD** — выбран Pillow: SIMD-форк ломает совместимость с pillow-heif; производительности обычного Pillow достаточно при ARQ-pipeline.

**Последствия:**
- Зависимости backend: `Pillow>=10.3`, `pillow-heif>=0.16`. Системные пакеты в Dockerfile: `libheif1`, `libde265-0`, `libjpeg62-turbo`, `zlib1g`, `libwebp7`.
- Volumes: `./upload_data/photos/originals` (rw в backend/worker, ro в nginx) и `./upload_data/photos/thumbs` (то же); они в `.gitignore`.
- Nginx добавлены internal-локации `/internal/photos-thumbs/` и `/internal/photos-originals/`.
- Для импорта 1ТБ архива заказчик загрузит файлы вручную через UI после деплоя; CLI-импорт-скрипт остаётся в плане Step 11.

---

## ADR-033 — Hardening после rev.md (apr 2026)

**Дата:** 27 апреля 2026  
**Статус:** Принято

### Контекст
Перед prod-деплоем проведено комплексное ревью (rev.md). Подтверждено 40+ находок: 10 P0, 24 P1, 19 P2, 7 P3.

### Решение
Применить все P0/P1/P2 правки. Ключевые архитектурные изменения:

1. **Единый Redis pool** через `app.state.redis` (вместо двух глобальных).
2. **Shared cache invalidation** через Redis-version counters (`app/core/cache_version.py`) — для system_settings, modules, keycloak_config, jwks. Решает проблему рассинхрона между uvicorn workers и ARQ worker.
3. **Audit queue recovery pattern** — LMOVE queue→processing, очистка processing только после успешного INSERT. Гарантия at-least-once.
4. **Session_id rotation** при /auth/refresh — защита от долго-живущих украденных сессий.
5. **photo_folders rename** — commit БД до FS-операции, компенсация при сбое.

### Последствия
- Все админ-операции теперь в audit_log.
- Изменения в admin-настройках видны всем процессам в течение секунды (через Redis-версию), не 60 секунд TTL.

---

## ADR-034: files_acl_persistence — JSON-хранилище ACL файлового менеджера

**Статус:** Принято

**Контекст:**

Файловый менеджер (Phase 5) использует PostgreSQL-таблицу `file_folder_permissions` как основное хранилище ACL. Однако при деплое с пересозданием БД или при аварийном сбросе PostgreSQL все настроенные права папок теряются. Nextcloud и администратор при этом не знают, что надо заново выдать доступ. Восстановить структуру прав из бэкапа БД можно, но это дополнительный шаг, требующий участия сисадмина.

**Решение:**

Ввести дополнительный персистентный слой: JSON-файл `/data/settings/files-acl.json`, который:
- Записывается при каждом изменении прав (add/revoke/delete folder).
- Читается при startup ARQ-воркера для восстановления прав в PostgreSQL (если таблица пуста).
- Хранится в томе `settings_data`, который монтируется независимо от БД.

Реализация: `backend/app/services/files_acl_persistence.py`.

**Семантика источника правды:**
- PostgreSQL — основной источник для runtime-запросов (быстрые JOIN, транзакции).
- JSON — fallback: читается только если PostgreSQL-таблица пустая на старте.
- При расхождении (сбой между записью в БД и записью в JSON) — PostgreSQL побеждает. JSON перезаписывается при следующей успешной записи прав.

**Альтернативы:**
- Только PostgreSQL → отклонено: потеря прав при пересоздании БД без применения бэкапа.
- Только JSON → отклонено: нет транзакционных гарантий, нет FK, нет JOIN.
- Redis-кэш → отклонено: Redis очищается при рестарте контейнера и не является persistent хранилищем (AOF — best-effort, не гарантия).

**Последствия:**
- `/data/settings/files-acl.json` создаётся автоматически при первом изменении прав.
- Файл пишется атомарно через `tempfile.mkstemp + os.replace`, права `chmod 0600`.
- `asyncio.Lock` предотвращает race condition при параллельных записях в одном процессе.
- При горизонтальном масштабировании (несколько worker-процессов) возможны конкурентные записи — допустимо, т.к. последняя запись перетирает предыдущую, и при любом исходе данные консистентны (JSON отражает последнее состояние БД).
- Название `files_acl_persistence.py` (не `backup`) явно указывает на роль persistence layer, а не резервной копии.
- `_subject_ids_for_user` унифицирован: единственная реализация находится в `acl_base.subject_ids_for_user` и используется `files_acl.py`, `kb_acl.py`, `photos_acl.py`. При добавлении нового типа `auth_source` достаточно правки одного места.

---

## ADR-035: Silent refresh + retry-on-401 на фронте (май 2026)

**Статус:** Принято

**Контекст:**
Backend хранит сессию в Redis с `SESSION_TTL = 8h` и расширяет её sliding window при каждом запросе (`session_sliding_window` middleware, throttle 5 мин). Cookie `portal_session` выставляется на 8 часов. Endpoint `POST /auth/refresh` уже умел обменивать Keycloak refresh_token и ротировать `session_id`.

Однако `get_current_user` ([./backend/app/api/deps.py](../backend/app/api/deps.py)) на каждый запрос валидирует JWT `access_token` с `verify_exp=True`. Keycloak-default Access Token Lifespan — **5 минут**. Фронт никогда не вызывал `/auth/refresh` автоматически: функция `refreshSession()` была определена, но не использовалась, а HTTP-клиент при 401 сразу редиректил на `/login`. Реальный UX-эффект: пользователь, который 5 минут не делал ни одного API-запроса (например, говорил по телефону, читал длинную статью KB), вылетал на логин.

**Решение:**
1. **Silent refresh по таймеру** в `useAuthStore` ([./frontend/src/stores/auth.ts](../frontend/src/stores/auth.ts)): после успешного `loadUser()` запускается `setInterval(refreshAuth, 4 * 60_000)`. Запас 1 минуту перед KC-default 5 мин — даже при сетевом джиттере refresh успевает проскочить до истечения. Останов на `logout()`, `auth:expired`, `onScopeDispose`.
2. **Retry-on-401 с singleton-promise** в `api()` и `apiUpload()` ([./frontend/src/api/index.ts](../frontend/src/api/index.ts)). Любой 401 (кроме самого `/auth/refresh`) триггерит `refreshAuth()` → при успехе один повтор исходного запроса; при неудаче — старый `_handle401()` (диспатч `auth:expired` + редирект). Параллельные 401-ы из burst-а запросов коалесцируются: `_refreshPromise` — singleton, освобождается на `setTimeout(0)`.
3. **Никаких изменений на бэке**: вся существующая инфраструктура (`SESSION_TTL = 8h`, sliding window, ротация `session_id` в `/auth/refresh`) работала корректно — недостающим звеном был только клиент.

**Альтернативы и почему отклонены:**
- Поднять Access Token Lifespan в Keycloak до 8 часов — отклонено: теряется быстрый отзыв прав через Keycloak (revocation/disable account вступит в силу только через 8 ч), плюс нарушает best-practice «короткий access + длинный refresh».
- Динамический интервал по `exp` claim из JWT — отклонено как over-engineering: фронт не должен парсить JWT (иначе теряется HTTPOnly-инвариант), а возвращать `exp` отдельным полем в `/auth/me` — лишний контракт ради экономии ~30 секунд.
- Только retry-on-401 без таймера — отклонено: при простое в фоне (нет запросов вообще) Keycloak-сессия истечёт по `SSO Session Idle`, и refresh упадёт. Активный таймер каждые 4 мин держит KC-сессию живой ровно до тех пор, пока вкладка открыта.
- Ofetch встроенный `retry`/`retryStatusCodes` — отклонено: нет места для условной логики (refresh успел? давай повторим), и нет coalescing.

**Последствия:**
- Активный пользователь больше не вылетает каждые 5 минут — таймер тихо обновляет access_token в фоне.
- Сценарий «вкладка засуспендилась» (laptop sleep / browser tab discard): таймер пропускает срабатывание → первый же запрос после пробуждения получает 401 → retry-on-401 прозрачно ремонтирует сессию.
- Burst из N параллельных запросов на истёкшем токене вызывает ровно один `/auth/refresh` (singleton-promise), остальные ждут и ретраятся.
- Пользователь увидит редирект на `/login` только в трёх случаях: явный logout, отзыв сессии в Keycloak, простой ≥ `SSO Session Idle` (по умолчанию 30 мин у KC, в нашем `SESSION_TTL` — 8 ч).
- Рекомендуемые настройки Keycloak realm для прода: `Access Token Lifespan = 15 min` (можно поднять и интервал таймера до ~12 мин), `SSO Session Idle = 8h` (совпадает с `SESSION_TTL`), `SSO Session Max = 12h` (рабочий день + запас).

## ADR-036: Auto-SSO + локальный backdoor через `/auth/local` (май 2026)

**Статус:** Принято

**Контекст:**
До этого фронт показывал страницу `/login` с двумя кнопками — Keycloak SSO и локальная форма. На доменном ПК пользователь делал лишний клик на «Войти через Keycloak», хотя Kerberos-handshake мог бы пройти прозрачно. Сценарий «открыл портал — попал на главную без единого клика» не работал. Дополнительно: при сбое OIDC-callback (`error=`, ошибка обмена кода, неверный nonce) FastAPI бросал `HTTPException(401)` — пользователь видел белый экран JSON `{"detail":"..."}` без объяснения и без кнопки «попробовать ещё раз».

**Решение:**
1. **Auto-SSO для гостя:** router-guard и `_handle401` в `api/index.ts` редиректят неавторизованного пользователя сразу на `/api/v1/auth/login` (не на SPA-страницу). Доменный ПК → прозрачный Kerberos через Keycloak; не-доменный → форма Keycloak.
2. **`/auth/local` — backdoor для bootstrap-admin / DevOps**, не индексируется в публичном UI. Содержит ту же визуальную часть (split-hero), что и удалённая `LoginPage.vue`, но без кнопки SSO. При `LOCAL_AUTH_ENABLED=false` форма скрывается.
3. **`/auth/error?reason=...`** — заменяет белый экран FastAPI 401. Все error-paths в `auth.callback` (oidc_error, invalid_state, token_exchange_failed, jwt_invalid, nonce_mismatch) теперь возвращают `RedirectResponse('/auth/error?reason=sso_failed', 302)` + аудит-событие `auth.sso_failed` с `metadata.reason`. Кнопка «Войти снова» сбрасывает loop-counter и идёт на `/api/v1/auth/login`.
4. **Loop-protection** (вдохновлено keycloak-js / Auth.js): `sso_attempts` массив timestamps в `sessionStorage`, окно 30s, лимит 2. ≥ 2 редиректов за 30s → `/auth/error?reason=loop_detected` без авто-навигации. Сбрасывается при успешном `loadUser()` и при ручном клике «Войти снова».
5. **Logout НЕ убивает Keycloak SSO-сессию** (`kc_service.get_logout_url` больше не вызывается из `logout()`). Удаляется только серверная сессия в Redis + cookie. Keycloak-юзеров редиректит на `/auth/error?reason=logged_out`, локальных — на `/auth/local?logged_out=1`.
6. **Старые закладки `/login`** обслуживаются стаб-компонентом `AuthRedirectStub.vue`, который выполняет `window.location.replace('/api/v1/auth/login?redirect=...')` при монтировании.

**Альтернативы и почему отклонены:**
- Оставить SPA-страницу `LoginPage.vue` с кнопкой SSO — отклонено: нарушает требование «без единого клика для доменного юзера». При сбое cookie или Kerberos-handshake пользователь застревал на форме.
- `prompt=none` тихая проверка сессии в Keycloak — отложено как отдельная история. Сейчас loop-protection достаточно.
- Убить Keycloak SSO-сессию через end-session endpoint при logout — отклонено: для интранета приемлемо, что доменный пользователь автоматически перелогинится после logout (согласовано с product owner). Альтернатива даёт хуже UX (пользователь должен снова проходить Kerberos-handshake) без выгод по безопасности (рабочая станция всё равно доменная).
- Кастомный Keycloak login theme с брендингом портала — отдельный тикет, выполняется позже.

**Последствия:**
- Доменный пользователь открывает корень портала — попадает на главную без единого клика (Kerberos-handshake занимает ~200ms).
- Не-доменный пользователь видит форму Keycloak (а не страницу портала).
- Сбои callback больше не показывают белый экран JSON — пользователь видит понятную страницу с кнопкой «Попробовать ещё раз».
- Бесконечный loop при кривой настройке Keycloak / блокировке cookie ловится counter'ом и останавливается на `/auth/error?reason=loop_detected`.
- Bootstrap первого admin-а: после `setup.sh` админ открывает `/auth/local`, входит локально → попадает на `/admin`, добавляет себя в Keycloak / настраивает realm.
- Рассказ DevOps'у: «доступ к порталу когда Keycloak лежит» — `/auth/local` работает независимо.
- Аудит обогащён: тип события `auth.sso_failed` с `metadata.reason ∈ {oidc_error, invalid_state, token_exchange_failed, jwt_invalid, nonce_mismatch}`. SOC видит причину каждого сбоя.

## ADR-037: Bootstrap-only env, runtime-config в `system.json` (май 2026)

**Статус:** Принято

**Контекст:**
До этой правки часть параметров одновременно объявлялась и в `Settings` (Pydantic, читается из `.env`), и в `SystemSettings` (`/data/settings/system.json`, управляется через Admin UI). Это приводило к нескольким проблемам:
- ручное «слияние» при старте через цепочки `value or settings.X` — каждый call-site должен помнить про fallback;
- две правды для `portal_base_url`, `max_upload_size_mb`, `allowed_cidr`, `log_level`, `sentry_dsn`, `prometheus_metrics_enabled`, `arq_max_jobs`, `nc_files_root` и др.; админ менял значение в UI, а после рестарта оно перезатиралось из env;
- `.env.example` разрастался; новый параметр приходилось добавлять в три места (Settings, SystemSettings, .env.example).

**Решение:**
1. **Bootstrap (env, `app/core/config.py::Settings`)** — только то, что нужно ДО первой загрузки `system.json`: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `KEYCLOAK_*`, `ADMIN_EMAIL/PASSWORD`, `LOCAL_AUTH_ENABLED`, `SCREENSHOT_SERVICE_*`, `DB_ECHO/POOL_*`, `ENVIRONMENT`. Меняется редеплоем.
2. **Runtime (JSON, `app/core/system_config.py::SystemSettings`)** — всё остальное: `portal_base_url`, `*_max_size_mb`, `allowed_cidr`, `log_level`/`log_force_json`/`log_slow_request_ms`, `sentry_dsn`, `prometheus_metrics_enabled`/`metrics_token`, `arq_max_jobs`, `nc_files_root`/`nc_service_username`, `nextcloud_url`/`nc_service_app_password`. Меняется через Admin UI без рестарта.
3. **Однократная миграция:** `migrate_env_to_system_settings()` запускается на старте бэкенда и воркера ДО первого `load_system_settings()`. Если `/data/settings/system.json` отсутствует и в окружении присутствуют легаси-переменные из `_LEGACY_ENV_MAP` — формирует `SystemSettings(**kwargs)` и сохраняет файл атомарно. Идемпотентна: на втором запуске JSON уже есть → no-op.
4. **Deprecation warning:** если `system.json` существует, но легаси-переменные всё равно установлены, пишется `config.deprecated_env_vars_ignored` (warning) — оператор должен удалить их из `.env`.
5. **Все call-sites очищены** от паттерна `runtime_value or settings.legacy_value`. Источник один — `load_system_settings()`.

**Альтернативы и почему отклонены:**
- Только env (выкинуть JSON) — отклонено: лимиты загрузки, `allowed_cidr` и брендинг должны меняться через Admin UI без редеплоя. Это зафиксировано в ADR-020.
- Только JSON (выкинуть env) — отклонено: `DATABASE_URL`/`SECRET_KEY` нужны до того, как процесс сможет прочитать файл; кроме того, секреты лучше держать вне shared volume (Docker secrets, K8s Secret).
- Гибрид с приоритетом env над JSON — это и было исходное состояние; мы от него уходим.

**Последствия:**
- `.env.example` похудел: 16 переменных удалены. Новый параметр runtime — только в `SystemSettings` + миграция (если нужна).
- Существующие установки безопасно обновляются: при первом старте после деплоя их env-значения автоматически переезжают в `system.json`. Перезапуск с теми же env — no-op + warning.
- Тесты: `_stub_system_settings` — autouse session fixture в conftest, подменяет `_SYSTEM_SETTINGS_FILE` на tmp; `test_legacy_runtime_fields_removed` — regression-guard, чтобы случайно не вернули поле в `Settings`.
