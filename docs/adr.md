# Architecture Decision Records (ADR)

> **Когда читать:** спорное/новое архитектурное решение — нужен контекст и обоснование «почему так».
> **Ключевой код:** зависит от ADR (ссылки на файлы внутри каждого решения).
> **ADR:** активные 001–047; отменённые/заменённые — `adr-archive.md`.

> Корпоративный интранет-портал
> Последнее обновление: июль 2026 (ADR-045 — CI-built images в GHCR + pull-based deploy; ADR-046 — prod-контур без клона репозитория; ADR-047 — semver-lock прод-деплоя)

Каждый ADR описывает одно архитектурное решение: контекст, альтернативы, выбор и обоснование.

> **Архив:** ADR со статусом «Заменено», «Superseded» или «зарезервирован/удалён» перенесены в [`./docs/adr-archive.md`](./adr-archive.md).

---

## Индекс активных ADR

- [ADR-001: Keycloak как единственный IdP](#adr-001-keycloak-как-единственный-idp)
- [ADR-032: Nextcloud — service account (Вариант A)](#adr-032-nextcloud-service-account-вариант-a)
- [ADR-003: Хранение аватаров в local volume (не PostgreSQL BYTEA, не Nextcloud)](#adr-003-хранение-аватаров-в-local-volume-не-postgresql-bytea-не-nextcloud)
- [ADR-004: UI — Naive UI (вместо PrimeVue)](#adr-004-ui-naive-ui-вместо-primevue)
- [ADR-005: WYSIWYG — TipTap v2 с dual-mode (Visual + Markdown)](#adr-005-wysiwyg-tiptap-v2-с-dual-mode-visual-markdown)
- [ADR-006: PDF-экспорт через выделенный screenshot-service (Playwright/Chromium)](#adr-006-pdf-экспорт-через-выделенный-screenshot-service-playwrightchromium)
- [ADR-007: Rate Limiting — fastapi-limiter (не slowapi)](#adr-007-rate-limiting-fastapi-limiter-не-slowapi)
- [ADR-008: Хранение контента в Markdown, не HTML](#adr-008-хранение-контента-в-markdown-не-html)
- [ADR-009: Оптимистичная блокировка (version field) вместо пессимистичной](#adr-009-оптимистичная-блокировка-version-field-вместо-пессимистичной)
- [ADR-010: ON DELETE RESTRICT на kb_sections.parent_id (не CASCADE)](#adr-010-on-delete-restrict-на-kbsectionsparentid-не-cascade)
- [ADR-011: SSE через Redis Streams (не pub/sub)](#adr-011-sse-через-redis-streams-не-pubsub)
- [ADR-012: Audit Log — async batch insert через ARQ (не синхронная запись)](#adr-012-audit-log-async-batch-insert-через-arq-не-синхронная-запись)
- [ADR-014: Idempotency — хранение только `{"id": uuid}`, не полного response body](#adr-014-idempotency-хранение-только-id-uuid-не-полного-response-body)
- [ADR-015: Docker healthcheck — `/ready`, не `/health`](#adr-015-docker-healthcheck-ready-не-health)
- [ADR-016: LocalLoginRequest — `str` вместо `EmailStr` для корпоративных доменов](#adr-016-localloginrequest-str-вместо-emailstr-для-корпоративных-доменов)
- [ADR-017: Dual-auth, единая Redis-сессия, роль из БД](#adr-017-dual-auth-единая-redis-сессия-роль-из-бд)
- [ADR-018: bcrypt SHA256 pre-hash для длинных паролей](#adr-018-bcrypt-sha256-pre-hash-для-длинных-паролей)
- [ADR-019: Настройки оформления — файловый store без БД](#adr-019-настройки-оформления-файловый-store-без-бд)
- [ADR-020: Admin UI как единая точка конфигурации](#adr-020-admin-ui-как-единая-точка-конфигурации)
- [ADR-021: Cookie Secure определяется по X-Forwarded-Proto, а не ENVIRONMENT](#adr-021-cookie-secure-определяется-по-x-forwarded-proto-а-не-environment)
- [ADR-022: Явная регистрация HEAD на branding file-эндпоинтах](#adr-022-явная-регистрация-head-на-branding-file-эндпоинтах)
- [ADR-023: SSE per-user connection limit через Redis sorted set](#adr-023-sse-per-user-connection-limit-через-redis-sorted-set)
- [ADR-024: SSRF-guard на user-supplied Keycloak URL](#adr-024-ssrf-guard-на-user-supplied-keycloak-url)
- [ADR-025: CSRF defense-in-depth — Origin strict-match + Double-Submit Cookie](#adr-025-csrf-defense-in-depth-origin-strict-match-double-submit-cookie)
- [ADR-027: Iframe embed в редакторе (TipTap)](#adr-027-iframe-embed-в-редакторе-tiptap)
- [ADR-028: Модули — Admin UI управление внешними интеграциями](#adr-028-модули-admin-ui-управление-внешними-интеграциями)
- [ADR-030: Собственный модуль фотогалереи](#adr-030-собственный-модуль-фотогалереи)
- [ADR-031: Архитектура собственного модуля фотогалереи](#adr-031-архитектура-собственного-модуля-фотогалереи)
- [ADR-033 — Hardening после rev.md (apr 2026): (зарезервирован/удалён)](#adr-033-hardening-после-revmd-apr-2026)
- [ADR-034: files_acl_persistence — JSON-хранилище ACL файлового менеджера](#adr-034-filesaclpersistence-json-хранилище-acl-файлового-менеджера)
- [ADR-035: Silent refresh + retry-on-401 на фронте (май 2026)](#adr-035-silent-refresh-retry-on-401-на-фронте-май-2026)
- [ADR-036: Auto-SSO + локальный backdoor через `/auth/local` (май 2026)](#adr-036-auto-sso-локальный-backdoor-через-authlocal-май-2026)
- [ADR-037: Bootstrap-only env, runtime-config в `system.json` (май 2026)](#adr-037-bootstrap-only-env-runtime-config-в-systemjson-май-2026)
- [ADR-038: Виджет «Время в городах» + погода через Open-Meteo (май 2026)](#adr-038-виджет-время-в-городах-погода-через-open-meteo-май-2026)
- [ADR-039: Nginx sidecar + inotify — динамическая перегенерация конфига](#adr-039-nginx-sidecar--inotify--динамическая-перегенерация-конфига)
- [ADR-040: Сетевая топология Docker — internal vs external сети](#adr-040-сетевая-топология-docker--internal-vs-external-сети)
- [ADR-041: Стратегия логирования — json-file driver и ротация](#adr-041-стратегия-логирования--json-file-driver-и-ротация)
- [ADR-042: Stable session_id при /auth/refresh — мультитаб-устойчивый silent refresh (июнь 2026)](#adr-042-stable-session_id-при-authrefresh--мультитаб-устойчивый-silent-refresh-июнь-2026)
- [ADR-043: fastapi-limiter 0.1.6 + starlette 1.x — monkey-patch совместимости (июль 2026)](#adr-043-fastapi-limiter-016--starlette-1x--monkey-patch-совместимости-июль-2026)
- [ADR-044: Observability-стек — Grafana + Loki + Prometheus + Alloy, удаление Sentry (июль 2026)](#adr-044-observability-стек--grafana--loki--prometheus--alloy-удаление-sentry-июль-2026)
- [ADR-045: CI-built images в GHCR + pull-based deploy (июль 2026)](#adr-045-ci-built-images-в-ghcr--pull-based-deploy-июль-2026)
- [ADR-046: Разделение контуров dev/prod — prod без клона репозитория (июль 2026)](#adr-046-разделение-контуров-devprod--prod-без-клона-репозитория-июль-2026)
- [ADR-047: Semver-lock прод-деплоя (июль 2026)](#adr-047-semver-lock-прод-деплоя-июль-2026)

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
- `POST /files/folders/{id}/upload` — 20/мин/user; `GET /files/download|preview` — 60/мин/user; bulk-delete/bulk-move — 3/мин/user
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

## ADR-014: Idempotency — хранение только `{"id": uuid}`, не полного response body

**Статус:** Принято

**Контекст:**
Idempotency middleware кэширует ответ для повторных запросов.

**Решение:** Хранить только `{"id": resource_uuid}` + `status_code`. Каждый POST-endpoint в whitelist обязан выставлять заголовок `X-Resource-Id: {uuid}`.

**Почему не полный body:**
- StreamingResponse (скачивание файла 500 МБ) нельзя сохранить в JSONB — БД умрёт
- Клиенту достаточно `id` для последующего GET

**Применяется только к whitelist:** `POST /news`, `POST /kb/articles`, `POST /files/folders` (+ вложенные `POST /files/folders/**`: upload, bulk), `POST /notifications/send`. TTL: 24 часа.

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
- При изменении `max_upload_size_mb` или `allowed_cidr` бэкенд создаёт файл-триггер в `/data/nginx/reload-trigger`. Генерацией `limits.conf` и `allowlist.conf` в `/data/nginx-conf/` занимается sidecar-контейнер `nginx-config` (alpine + jq + envsubst + inotify-tools) — он inotifies `/data/settings/system.json` и `/data/certs/`, рендерит конфиги из шаблонов в `nginx/templates/`.
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
>
> **Примечание (обновление май 2026, UX-рефакторинг):** Во вкладке `Admin → Модули` (`ModulesTab.vue`) остаются только мастер-переключатели модулей + Nextcloud-карточка + Video URL. Детальные настройки модулей с собственной страницей (Photos, Meetings) вынесены в самостоятельные компоненты `frontend/src/components/admin/PhotosModuleSettings.vue` и `MeetingsModuleSettings.vue`; они открываются drawer’ом непосредственно со страницы модуля (`?manage=module`, шестерёнка-кнопка в шапке/сайдбаре, видна только администратору). Это убирает дублирование «настройки модуля живут далеко от модуля» и сохраняет master-switch в одном месте. См. `composables/useManageDrawer.ts` и команды `manage-photos-module` / `manage-meetings-module` в Cmd+K palette.

**Альтернативы:**
- Оставить в env — отклонено: рестарт контейнера при смене API-ключа; нет UI для оператора.
- PostgreSQL таблица — избыточно: нет реляционных зависимостей; файл проще и не требует миграции.
- Redis — отклонено: volatile; данные теряются при рестарте Redis.
- Один общий `system.json` — отклонено: иная семантика (Nextcloud, CIDR, TLS); смешивание усложняет эволюцию схемы.

**Последствия:**
- `backend` и `worker` монтируют volume `./system_data/settings:/data/settings`.
- При компрометации `modules.json` — сохранённые настройки модулей скомпрометированы. Рекомендация: volume доступен только внутри Docker network.

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

3. **Storage (`services/photos_storage/` — пакет: `paths`/`originals`/`thumbnails`/`metadata`):**
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

**Дополнение (май 2026, по итогам ревью photo-ref.md):**

7. **Cron-самоисцеление пайплайна обработки (`detect_missing_thumbnails`):**
   - Запускается каждые 5 минут (`./backend/app/worker/main.py`).
   - Реквьюит фото с пропавшим `200.webp` (сброс `processed=false` и enqueue `process_photo_upload`).
   - Реквьюит фото в зависшем состоянии `processed=false` старше 2 минут (страховка от потерянных воркеров/перезапусков).
   - Использует уникальный `_job_id` с timestamp, чтобы обходить arq-дедуп failed-результатов и гарантировать повторный запуск.
   - Покрывает деградации БД↔диск (миграция файлов, повреждение, ручная чистка) и сбои воркера между INSERT photo и enqueue.

8. **Enqueue ARQ-задач строго после outer commit'а батча (#15):**
   - В `./backend/app/worker/tasks/photos/import_scan.py` ARQ `enqueue_job` для `process_photo_upload` вызывается только из `_flush_batch` после успешного `db.commit()`.
   - Ранее enqueue мог произойти до commit'а — worker подхватывал `photo_id`, отсутствующий в БД (race с MVCC visibility), и падал с `not found`.
   - Аналогичная инвариантность для `POST /upload`: enqueue делается роутером после commit'а транзакции аплоада.
   - В сочетании с пунктом 7 (`detect_missing_thumbnails`) получаем полное покрытие: даже если процесс упал между commit'ом и enqueue, cron подберёт фото в течение ≤5 минут.

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
4. **Session_id rotation** при /auth/refresh — защита от долго-живущих украденных сессий. ⚠️ **Отменено ADR-042** (июнь 2026): ротация ломала параллельные вкладки (cookie менялся на каждом silent refresh → «соседи» теряли сессию и слали в Keycloak отозванный refresh-токен). Теперь токены обновляются in-place под стабильным `session_id`; защита от угона сессии обеспечивается коротким Access Token Lifespan + HTTPOnly/Secure/SameSite cookie. Подробности и trade-off — в ADR-042.
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
3. **Никаких изменений на бэке**: вся существующая инфраструктура (`SESSION_TTL = 8h`, sliding window, обмен refresh-токена в `/auth/refresh`) работала корректно — недостающим звеном был только клиент. ⚠️ **Уточнение (ADR-042, июнь 2026):** ровно бэк-часть и пришлось доработать — ротация `session_id` на каждый refresh ломала параллельные вкладки. См. ADR-042 (in-place обновление токенов под стабильным `session_id` + per-session Redis-lock + коалесинг + кросс-табовый redirect-guard).

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

**⚠️ Уточнение (июнь 2026): устойчивость к фоновой вкладке.**
Изначальный «safety-net» retry-on-401 на практике не срабатывал для главного целевого сценария — вкладки, провисевшей в фоне/спавшей. Причина: `POST /auth/refresh` зависел от `CurrentUser` → `get_current_user` → `parse_jwt_claims(access_token, verify_exp=True)`. Когда фоновый `setInterval` заморожен браузером и access-токен (15 мин) истёк, эндпоинт отдавал **401 ещё до тела** — то есть отказывался рефрешить ровно тогда, когда refresh и нужен → жёсткий full-page bounce через SSO → при повторных триггерах добивался loop-guard → пугающий экран «Слишком много попыток входа».

Доработки:
1. **`/auth/refresh` развязан от валидного access-токена.** Введена облегчённая зависимость `get_user_for_refresh` ([./backend/app/api/deps.py](../backend/app/api/deps.py)): личность берётся из Redis-сессии (cookie `portal_session`) по `user_id`, **без** разбора JWT и проверки `exp`. Эндпоинт ([./backend/app/api/auth/me.py](../backend/app/api/auth/me.py)) переключён на `RefreshUser`; вся остальная логика (per-session lock, коалесинг 10s, обмен в Keycloak, in-place save под стабильным `session_id` — ADR-042, rate-limit 30/мин) и все 401-кейсы (нет cookie / нет сессии / нет refresh_token / `user.deleted_at`) сохранены. `/me` и обычные эндпоинты по-прежнему используют `CurrentUser` с `verify_exp=True` — проверку там НЕ ослабляем. Контракт `/auth/refresh` не меняется (тот же путь/сигнатура), меняется только поведение: теперь принимает истёкший access.
2. **Проактивный refresh по `visibilitychange`** в `useAuthStore` ([./frontend/src/stores/auth.ts](../frontend/src/stores/auth.ts)): при возврате вкладки в `visible` (если пользователь авторизован и с последнего refresh прошло > 60s) — немедленный `refreshAuth()` + переустановка 4-минутной каденции (фоновый таймер мог быть заморожен). Лечит токен **до** первого 401. Слушатель снимается в `onScopeDispose`.
3. **Грациозный re-login вместо `loop_detected`.** Если refresh при возврате из фона провалился (пользователь был авторизован, но Keycloak refresh_token уже мёртв: idle ≥ SSO Idle / max ≥ SSO Max / отозван) — вместо немой переадресации на SSO показываем спокойный экран `/auth/error?reason=session_expired` («Сессия истекла → Войти»). Этот путь **не** дёргает loop-counter (`redirectToSessionExpired`), поэтому легитимное истечение сессии больше не выглядит как «бесконечный редирект». Таймерный (foreground) путь сюда не ведёт: там access ещё жив ~15 мин и транзиентный сбой refresh не должен выбивать активного пользователя. Loop-guard остаётся backstop'ом только для настоящих циклов.

Эффект: возврат к вкладке после фона (вплоть до SSO Session Idle 8h) = тихий in-place refresh без редиректа и перезагрузки; реальное истечение сессии = понятный экран вместо пугающего loop-экрана.

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
7. **Истечение сессии учитывает тип входа (июнь 2026; расширено июль 2026).** Все три редирект-пути на фронте — `_handle401` (api-клиент), `redirectToSSO` (router guard) и `logout()` — симметрично уважают `auth_source`: локальная сессия уходит на форму `/auth/local?redirect=...` (`?logged_out=1` для logout), а не на `/api/v1/auth/login` (Keycloak SSO), который для local-пользователя только зациклил бы вход (у него нет Keycloak-учётки). Источник истины о типе — `_sessionAuthSource` в `api/index.ts`, который обновляется стором при каждой загрузке пользователя (`loadUser`/`loadBootstrap`/`setUser`); на клир НЕ сбрасывается, чтобы на момент 401 знать тип истёкшей сессии.

   **Холодный старт (июль 2026).** `_sessionAuthSource` — in-memory переменная модуля, по умолчанию `'keycloak'`. На новой вкладке/после закрытия браузера до первого `loadBootstrap` это значение теряется, и даже починенные редирект-пути уходили бы на SSO. Решение — бэкенд-управляемая cookie `portal_auth_method` (TTL 30 дней, `HttpOnly=False`): бэкенд ставит/обновляет её значением `'local'` или `'keycloak'` при каждом успешном логине (`local.local_login`, `_helpers._build_session_cookie_response`), а фронт инициализирует `_sessionAuthSource` из неё на старте модуля. Cookie содержит только маркер способа входа, без PII. **Переживает logout** (`logout.py` намеренно не удаляет её) — это позволяет локальному юзеру после logout снова попасть на `/auth/local` (а не на SSO). Если cookie нет (новое устройство, чистый браузер) — дефолт `'keycloak'` (UX для большинства доменных юзеров). Поле `last_auth_method` в ответе `/auth/config` опционально дублирует это знание для introspection. Симметрично п.5 (logout): local-вход всегда возвращается на `/auth/local`.

**Альтернативы и почему отклонены:**
- Оставить SPA-страницу `LoginPage.vue` с кнопкой SSO — отклонено: нарушает требование «без единого клика для доменного юзера». При сбое cookie или Kerberos-handshake пользователь застревал на форме.
- `prompt=none` тихая проверка сессии в Keycloak — отложено как отдельная история. Сейчас loop-protection достаточно. (Заготовка `get_silent_auth_url` удалена в июне 2026 как нереализованный мёртвый код; вернуть при возобновлении истории.)
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
- две правды для `portal_base_url`, `max_upload_size_mb`, `allowed_cidr`, `log_level`, `prometheus_metrics_enabled`, `arq_max_jobs`, `nc_files_root` и др.; админ менял значение в UI, а после рестарта оно перезатиралось из env;
- `.env.example` разрастался; новый параметр приходилось добавлять в три места (Settings, SystemSettings, .env.example).

**Решение:**
1. **Bootstrap (env, `app/core/config.py::Settings`)** — только то, что нужно ДО первой загрузки `system.json`: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `KEYCLOAK_*`, `ADMIN_EMAIL/PASSWORD`, `LOCAL_AUTH_ENABLED`, `SCREENSHOT_SERVICE_*`, `DB_ECHO/POOL_*`, `ENVIRONMENT`. Меняется редеплоем.
2. **Runtime (JSON, `app/core/system_config/_schemas.py::SystemSettings`)** — всё остальное: `portal_base_url`, `*_max_size_mb`, `allowed_cidr`, `log_level`/`log_force_json`/`log_slow_request_ms`, `prometheus_metrics_enabled`/`metrics_token`, `arq_max_jobs`, `nc_files_root`/`nc_service_username`, `nextcloud_url`/`nc_service_app_password`. Меняется через Admin UI без рестарта.
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

---

## ADR-038: Виджет «Время в городах» + погода через Open-Meteo (май 2026)

**Статус:** Принято

**Контекст:**
Команды распределены по нескольким часовым поясам (Москва, Владивосток, Сахалин, Пусан и др.). Сотрудники регулярно тратят время на «сколько у них сейчас?» перед звонком/письмом. Решено добавить на главную страницу компактный виджет с текущим временем и погодой в выбранных городах. Требования:

- настраиваемый список городов (CRUD + drag-and-drop порядок) через шестерёнку прямо на виджете (`?manage=world-clock`);
- адаптивная сетка кубиков (1 колонка для 1 города, 2 колонки для 2+);
- никакого backend-кода и схемных миграций — фича чисто фронтовая;
- погода — из бесплатного источника без ключей и регистрации; сбой источника не должен ломать UI.

**Решение:**

1. **Хранение городов — `localStorage`** (ключ `portal.worldClockCities.v2`). Дефолтный список (Москва/Владивосток/Сахалин/Пусан) с координатами захардкожен в `useWorldClockCities.ts`. Versioned ключ позволяет безопасно эволюционировать схему (`v1 → v2` при добавлении `lat/lon`).

2. **UI:**
   - `components/widgets/WorldClockWidget.vue` — виджет в правом сайдбаре `HomePage` между «Сервисами» и `PhotosWidget`. Кубики растягиваются `1fr / 1fr` под ширину контейнера.
   - `pages/admin/tabs/WorldClockTab.vue` — открывается drawer’ом со страницы `Home` (admin-кнопка-шестерёнка на самом виджете, `?manage=world-clock`, см. `composables/useManageDrawer.ts`); сортируемый список (sortablejs, drag-handle), модалка add/edit, сброс к дефолтам.

3. **Погода — Open-Meteo:** [open-meteo.com](https://open-meteo.com) выбран вместо OpenWeatherMap / wttr.in / Яндекс.Погоды по совокупности признаков:
   - бесплатно, без API-ключа, без регистрации (10 000 запросов/день/IP);
   - открытый CORS — браузер может ходить напрямую, без backend-прокси;
   - один батч-запрос для N координат (`?latitude=a,b,c&longitude=x,y,z`) → одна сетевая операция на все города;
   - есть EU-хостинг, open-source, понятный SLA.

   Альтернативы:
   - **OpenWeatherMap Free** — нужен ключ, держать его во фронте небезопасно, городить backend-прокси ради виджета часов — overkill.
   - **wttr.in** — нет CORS, тоже потребовал бы прокси.
   - **Яндекс/Gismeteo** — платные после небольшого free-tier.

4. **Геокодинг для админки:** Open-Meteo Geocoding API (`geocoding-api.open-meteo.com/v1/search?name=...`). Кнопка «📍» в форме города заполняет `lat`/`lon` и timezone по названию — админ не ищет координаты вручную.

5. **Кэш и обновление:**
   - Composable `useWorldClockWeather.ts` хранит `Record<cityKey, WeatherSample>` в `localStorage` (ключ `portal.worldClockWeather.v1`).
   - Refresh раз в **30 минут** (`REFRESH_MS`) + при первом монтировании, если данные старше TTL.
   - `setInterval` shared (refcount); чистится при размонтировании последнего инстанса виджета.
   - Любая сетевая ошибка (CSP, оффлайн, 5xx) тихо игнорируется — кубик откатывается на иконку день/ночь без температуры. Никаких alert-ов и спиннеров.

6. **CSP-allowlist:** в `nginx/render-config.sh::CSP` добавлены `https://api.open-meteo.com` и `https://geocoding-api.open-meteo.com` в `connect-src`. Без этого браузер режет fetch и виджет молча остаётся без погоды (см. эпизод дебага в логе разработки).

7. **WMO weather codes** маппятся в эмодзи (☀ ⛅ ☁ 🌫 🌧 🌨 ⛈) — без SVG-иконок и без зависимостей. ~20 строк кода, инлайн в composable.

**Альтернативы и почему отклонены:**

- **Хранение городов на бэкенде** (как часть branding или отдельная таблица) — отклонено: список идентичен для всей организации, кастомизация per-user не нужна, а одна общая запись отлично живёт в `localStorage` после первого деплоя; писать миграции и эндпоинты ради 4 строк JSON — несоразмерно. Если в будущем понадобится централизованное управление — миграция в branding-settings.
- **Аналоговые SVG-часы** — отклонено: тяжелее визуально, хуже на тёмной теме, не дают преимущества перед цифровым форматом для рабочего использования.
- **Полноразмерная карточка погоды** (давление, ветер, описание) — отклонено: виджет в сайдбаре должен быть лаконичен, расширенная погода — задача отдельной страницы (которую делать сейчас не планируется).
- **Расположение в HeroBlock** — отклонено: hero про брендинг, рабочая утилита там лишняя; в сайдбаре виден без скролла и не конкурирует с приветствием.

**Последствия:**

- Никаких backend-изменений, миграций БД, новых env-переменных. Полностью фронтовая фича.
- Зависит от внешнего сервиса open-meteo.com. Деградация: при недоступности виджет просто не показывает погоду, время продолжает работать.
- CSP теперь явно перечисляет два внешних домена для `connect-src`. При добавлении новых внешних API в будущем — править `render-config.sh` и не забывать про restart `nginx-config`/`nginx`.
- i18n: добавлены ключи `home.sections.worldClock`, `admin.tabs.worldClock`, `admin.worldClock.*` (RU/EN синхронизированы).

---

## ADR-039: Nginx sidecar + inotify — динамическая перегенерация конфига

**Статус:** Принято

**Контекст:**
Nginx требует TLS-конфигурацию, URL проксируемых сервисов и CSP-заголовки, которые зависят от runtime-настроек (хост портала, TLS-сертификат, список внешних origin'ов для CSP). Эти параметры изменяются оператором через Admin UI без перезапуска всего стека. Стандартная практика — либо перезапускать nginx при каждом изменении, либо использовать динамический upstream (например, consul-template / nginx-proxy).

**Решение:**

Два отдельных контейнера:

1. **`nginx-config` (sidecar):** минималистичный Alpine-контейнер (`./nginx/Dockerfile.config`), запускающий `./nginx/entrypoint-config.sh`. При старте рендерит nginx-include файлы (`limits.conf`, `allowlist.conf`, `ssl_server.conf`) из шаблонов (`./nginx/templates/`) по значениям `system.json` и сертификату из `/data/certs/`. После этого переходит в режим слежения: `inotifywait -m` отслеживает директории `/data/settings` и `/data/certs`. При любом релевантном событии (`close_write`, `moved_to`, `create`, `delete`) перезапускает рендер и прикасается (`touch`) к файлу `/data/nginx/reload-trigger`.

2. **`nginx` (основной):** nginx-контейнер через `entrypoint.sh` запускает nginx и параллельно запускает цикл мониторинга `reload-trigger`-файла (`inotifywait` или fallback `stat`). При изменении файла выполняет `nginx -s reload`. Конфиги подключаются через `include /data/nginx-conf/*.conf;` без знания о механизме их обновления.

Shared volume `/data/nginx-conf` — канал передачи конфигов от sidecar к nginx. Shared volume `/data/nginx` содержит только `reload-trigger`.

**Почему именно inotify:**
- Атомарная реакция на изменение, без polling-задержки. Особенно важно при смене TLS-сертификата: nginx должен перезагрузиться быстро, не держа старый сертификат в памяти.
- `inotifywait` — часть `inotify-tools`, доступна в Alpine без дополнительных репозиториев.
- Fallback на 60-секундный polling реализован для окружений, где inotify недоступен (некоторые VPS с ограниченным kernel).

**Альтернативы и почему отклонены:**
- **Один контейнер nginx + крон / watch-скрипт** — нарушает принцип одного процесса на контейнер; крон не работает с inotify, только polling.
- **consul-template / confd** — избыточная зависимость ради одного шаблона; требует запуска Consul или etcd.
- **nginx-proxy (jwilder)** — не покрывает кейс с runtime TLS и CSP, генерируемыми из admin-настроек.
- **Перезапуск всего стека** — неприемлемо для production; при смене сертификата простой составил бы время рестарта всех сервисов.
- **Webhook вместо inotify** — потребовал бы HTTP-endpoint в nginx-контейнере и изменения в backend при каждом сохранении настроек. Inotify прозрачнее: sidecar сам реагирует на факт записи файла.

**Поток данных:**

```
Admin UI → PATCH /admin/system → backend сохраняет system.json
                                       ↓ (inotifywait CLOSE_WRITE)
                              nginx-config рендерит конфиги
                                       ↓ (touch reload-trigger)
                              nginx получает inotify → nginx -s reload
```

**Последствия:**
- При отладке проблем с конфигом nginx нужно проверять: (1) `docker logs nginx-config` — успешность рендера; (2) содержимое `/data/nginx-conf/*.conf`; (3) `docker logs nginx` — факт reload и ошибки nginx.
- Если `nginx-config` падает, nginx продолжает работать со старым конфигом. Healthcheck `nginx-config` (проверка наличия непустого `ssl_server.conf`) предотвращает запуск nginx без конфига при cold start.
- Сервис `nginx` в `docker-compose.yml` явно зависит от `nginx-config: condition: service_healthy` — гарантия порядка запуска.
- `./nginx/render-config.sh` — единственное место логики шаблонизации; при добавлении новых параметров правится только этот скрипт.

---

## ADR-040: Сетевая топология Docker — internal vs external сети

**Статус:** Принято

**Контекст:**
Стек состоит из ~7 сервисов. Часть из них (postgres, redis, backend, worker, nginx-config, frontend) должна быть изолирована от внешней сети хоста — они взаимодействуют только между собой. Только nginx и (опционально) backend для DEV должны принимать входящие соединения снаружи.

**Решение:**

Два Docker-сетевых пространства:

- **`internal`** (`internal: true`) — bridge-сеть без выхода в интернет. В неё включены: `postgres`, `redis`, `backend`, `worker`, `nginx-config`, `frontend`, `screenshot-service`. Контейнеры из этой сети не могут инициировать соединения наружу и не доступны с хоста по IP (только через published ports).
- **`external`** (обычная bridge-сеть) — в неё включены `nginx` (публикует порты 80/443), `backend` и `worker`. Backend и worker требуют выхода в `external` для обращения к внешним сервисам (Keycloak, Nextcloud, SMTP), которые находятся вне Docker-стека.

Postgres и Redis находятся исключительно в `internal` и не публикуют порты в production. Это гарантирует, что даже при ошибке конфигурации firewall хоста БД недоступна извне.

**Staging-override (`docker-compose.staging.yml`):**
В staging postgres публикуется на `127.0.0.1:5432` и redis на `127.0.0.1:6379` — для выполнения дампов, интеграционных тестов и k6/zap прогонов. Bind на `127.0.0.1` (не `0.0.0.0`) означает, что порты доступны только с самого хоста (loopback), но не из внешней сети. Это приемлемо для staging-стенда, где хост находится в защищённом контуре.

**Production `.env`:**
В production-конфигурации переменные `POSTGRES_*` и `REDIS_PASSWORD` попадают в `.env` — файл ограничен правами `600` (создаётся `setup.sh`). Утечка через `docker inspect` теоретически возможна для пользователей с правами запуска docker-команд, что является стандартным допущением для docker-развёртываний без rootless mode.

**Альтернативы и почему отклонены:**
- **Одна сеть для всех** — отклонено: любой сервис мог бы напрямую достучаться до postgres в случае компрометации container escape.
- **Три сети (db / app / frontend)** — отклонено: усложняет compose-файл без существенного прироста безопасности при текущем масштабе; легко вернуться при росте требований.
- **Rootless Docker** — не реализовано на данном этапе; рекомендуется при переходе на production-grade инфраструктуру.
- **Публикация postgres на `0.0.0.0` в staging** — отклонено: заменено на `127.0.0.1`-bind для минимизации поверхности атаки.

**Последствия:**
- `internal: true` ограничивает как входящие, так и исходящие соединения за пределы Docker-сети: Docker не добавляет маршрут по умолчанию для контейнеров этой сети. Контейнеры в `internal` могут общаться между собой, но не могут инициировать соединения к внешним IP-адресам.
- В текущем compose-конфиге backend и worker включены одновременно в `internal` (для общения с postgres/redis/screenshot-service) и в `external` (для исходящих соединений к Keycloak/Nextcloud/SMTP, находящимся вне стека).

---

## ADR-041: Стратегия логирования — json-file driver и ротация

**Статус:** Принято

**Контекст:**
Все 7+ сервисов стека пишут логи в stdout/stderr. Docker по умолчанию накапливает их бесконечно. Без явной ротации логи на диске стенда могут переполнить его. Требования: логи должны быть доступны для ручного `docker logs`, ротироваться автоматически, не требовать инфраструктурных зависимостей (syslog, fluentd) на начальном этапе.

**Решение:**

Глобальный anchor `x-logging` в `docker-compose.yml`, применяемый ко всем сервисам через YAML-merge (`logging: *default-logging`):

```yaml
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "50m"
    max-file: "5"
    compress: "true"
    tag: "{{.Name}}"
```

При 7 сервисах максимальный объём логов: 7 × 50 МБ × 5 файлов = **1.75 ГБ** (в несжатом виде; с `compress: true` реально ~200–400 МБ для типичных текстовых логов). Это осознанный trade-off: достаточно для расследования инцидентов (5 × 50 МБ ≈ несколько суток при умеренной нагрузке), не переполняет диск при стандартном сервере с 50+ ГБ.

`tag: "{{.Name}}"` добавляет имя контейнера в каждый log-record — необходимо для фильтрации при агрегации.

**Staging/production разграничение:**
В staging `LOG_LEVEL: DEBUG` и `LOG_FORCE_JSON: "true"` (через compose-override). JSON-формат логов упрощает парсинг при последующей агрегации без изменения driver'а.

**Путь к централизованному сбору:**
Для перехода на centralized logging (Vector / Promtail / Fluentbit) достаточно заменить driver в anchor на `fluentd` или `loki` — все сервисы получат новый driver автоматически. Тег `{{.Name}}` уже обеспечивает нужную маркировку. До этого перехода текущая схема является минимально достаточной.

**Альтернативы и почему отклонены:**
- **`max-size: "10m"` (уменьшить)** — при verbose DEBUG-логировании 10 МБ может закрыть окно видимости менее чем за час. 50 МБ — разумный баланс.
- **`max-file: "10"` (увеличить файлы)** — удвоит максимальный объём до 3.5 ГБ; для текущего масштаба избыточно.
- **`driver: syslog`** — требует настроенного syslog-демона на хосте; нежелательная зависимость для docker-compose развёртывания.
- **`driver: none`** — логи недоступны; неприемлемо для production.
- **Vector/Promtail на старте** — избыточная сложность для MVP; архитектурно подготовлено (JSON-формат, тег), реализация откладывается до появления потребности в агрегированном поиске.

**Последствия:**
- Максимальный объём логов на диске: ~1.75 ГБ несжатых / ~400 МБ сжатых. Рекомендуется мониторить `df -h` на хосте.
- `docker logs <service>` работает в штатном режиме — оператор не теряет привычный инструмент отладки.
- При переполнении диска Docker начнёт отбрасывать новые записи (не старые). Это хуже потери старых логов с точки зрения оперативного мониторинга — дополнительный аргумент в пользу внешнего сборщика при росте нагрузки.

## ADR-042: Stable session_id при /auth/refresh — мультитаб-устойчивый silent refresh (июнь 2026)

**Статус:** Принято (заменяет пункт 4 ADR-033)

**Контекст:**
ADR-035 ввёл silent refresh по таймеру + retry-on-401. Endpoint `POST /auth/refresh` при этом **ротировал `session_id`**: генерировал новый id, писал сессию под ним, удалял старый, перевыставлял cookie (наследие ADR-033 P0 #4 — защита от долго-живущих украденных сессий).

Ротация ломается при нескольких вкладках одного пользователя:
- Вкладки A и B живут под одним cookie `portal_session = sid1`.
- Таймеры вкладок (каждые 4 мин) и retry-on-401 срабатывают почти одновременно → оба шлют `/auth/refresh`.
- A первой ротирует: `sid1 → sid2`, удаляет `sid1`, ставит cookie `sid2`. B всё ещё держит в запросе `sid1` (cookie у B обновится только после ответа) → её `get_session(sid1)` пуст → 401, либо B отправляет в Keycloak уже **отозванный** refresh-токен (Keycloak refresh token rotation) → `invalid_grant` → 401.
- Результат: «лишние» вкладки выбрасывает на логин; при массовом 401 (рестарт Redis / сбой Keycloak) все вкладки одновременно ломятся на `/auth/login`.

**Решение:**

*Backend* ([./backend/app/api/auth/me.py](../backend/app/api/auth/me.py), [./backend/app/services/session.py](../backend/app/services/session.py)):
1. **In-place обновление токенов под стабильным `session_id`** — cookie больше не меняется на каждый refresh, параллельные вкладки не теряют сессию. `session_id` остаётся неизменным на всё время сессии (создаётся при логине).
2. **Per-session Redis-lock** (`acquire_refresh_lock`/`release_refresh_lock`, `SET NX PX` + compare-and-delete через Lua) сериализует параллельные refresh из одного браузера: «лидер» обновляет токены, «ждуны» ждут и читают уже свежий refresh-токен, а не шлют отозванный. Инварианты таймингов (критично): `TTL (15s) > _KC_CLIENT_TIMEOUT (10s)` — лок переживает самый медленный refresh; `WAIT (15s) >= TTL` — ждун не сдаётся раньше, чем лок может легитимно удерживаться (иначе воспроизводится чинимая гонка). Лок best-effort: при таймауте поток продолжает без лока (деградация, не отказ).
3. **Коалесинг бурста** (`REFRESH_COALESCE_WINDOW_S = 10s`): если `refreshed_at` сессии в пределах окна, поток не дёргает Keycloak повторно (access-токен заведомо ещё жив, KC lifespan ≥ 5 мин) — гасит лавину рефрешей от N вкладок до одного реального обмена.
4. **Терпимость к гонке ротации**: если `kc_service.refresh_tokens` упал (`invalid_grant`), но `access_token` в сессии уже обновлён соседним потоком (lock мог истечь на медленном KC) — возвращаем `ok`, а не выбиваем пользователя.

*Frontend* ([./frontend/src/api/index.ts](../frontend/src/api/index.ts)):
5. **Кросс-табовый redirect-guard** (`auth_redirect_at` в `localStorage`, окно 8s): при жёстком 401 только одна вкладка (застолбившая метку) инициирует `window.location = /auth/login`; остальные лишь чистят локальное состояние (`auth:expired`) и ждут — после логина лидера общая cookie восстановится, их запросы пройдут. «Ждуны` **не** ставят `_redirectingOnExpiry` навсегда: если лидер упал/закрылся и cookie не восстановилась, следующий 401 за окном позволяет вкладке самой стать лидером (self-heal).

**Влияние на безопасность (trade-off):**
- Снимается ротация `session_id` (ADR-033 P0 #4). Защита от угона сессии теперь держится на: коротком Access Token Lifespan в Keycloak (быстрый отзыв прав), HTTPOnly + Secure + SameSite=Lax cookie (защита от XSS-кражи и CSRF), sliding `SESSION_TTL = 8h`, серверном logout (удаление Redis-сессии). Идентификатор сессии генерируется криптостойко (`secrets`) при логине и не появляется в URL/логах.
- Это осознанный размен «защита от фиксации идентификатора на каждый refresh» ↔ «работоспособный мультитаб». Ротация при смене привилегий (логин) сохраняется; именно она — основная защита от session fixation.

**Рекомендуемые настройки Keycloak (прод):** `Access Token Lifespan = 15 min`, `Revoke Refresh Token = ON` (rotation), `SSO Session Idle = 8h`, `SSO Session Max = 12h`.

**Тесты:** `backend/tests/unit/test_session.py` (lock helpers, инварианты таймингов, retry/timeout, suppress на release), `backend/tests/unit/test_auth_routes.py::TestAuthRefresh` (коалесинг без обращения к KC, терпимость к гонке), `frontend/tests/unit/cov-core-api-index.spec.ts` (follower не редиректит, self-heal за окном).

**Альтернативы и почему отклонены:**
- Оставить ротацию + чинить только фронт — отклонено: гонка отзыва refresh-токена принципиально неустранима на клиенте при ротации id на сервере.
- BroadcastChannel/SharedWorker для координации вкладок — отклонено как избыточное; `localStorage`-метка + серверный Redis-lock покрывают сценарии проще и без доп. рантайма.
- Глобальный (не per-session) lock — отклонено: сериализовал бы refresh разных пользователей, лишняя контеншн.

---

## ADR-043: fastapi-limiter 0.1.6 + starlette 1.x — monkey-patch совместимости (июль 2026)

**Статус:** Принято (обходной путь; пересмотреть при выходе фикса upstream)

**Контекст:**
Коммит `66a2fdf` (fix(deps): upgrade vulnerable dependencies) обновил `starlette` с 0.x до 1.x (требовалось для закрытия уязвимости). В starlette 1.x изменилась внутренняя структура `app.routes`: `include_router()` теперь оставляет wrapper-объекты `_IncludedRouter` (в `fastapi.routing`) без атрибутов `path`/`methods`, тогда как раньше включённые роуты «разворачивались» в плоский список `APIRoute` с `.path`.

`fastapi-limiter==0.1.6` (зафиксирован в стеке, AGENTS.md: «не использовать slowapi») в `RateLimiter.__call__` итерирует `request.app.routes` и обращается к `route.path` / `route.methods` без `getattr`-fallback → `AttributeError` на **каждом** rate-limited endpoint (`/auth/local/login`, `/api/v1/search`, `/api/v1/news`, `/api/v1/feedback`). 32 из 37 маршрутов в `app.routes` — `_IncludedRouter`.

**Решение:** Monkey-patch `RateLimiter.__call__` в `app/core/limiter.py::_patch_rate_limiter_for_starlette1`, применяется при импорте модуля (до регистрации роутов):
- Пропускает маршруты без `.path`/`.methods` через `getattr(route, "path", None)`.
- Полная type-аннотация `(self: RateLimiter, request: Request, response: Response)` — критично, см. грабли ниже.

**Грабли (важно!):**
1. **`from __future__ import annotations` — нельзя** в `app/core/limiter.py`. Этот импорт превращает аннотации `_patched_call` в строки (`'Request'`). После monkey-patch FastAPI интроспектит сигнатуру `RateLimiter.__call__` через `lenient_issubclass`, а `lenient_issubclass('Request', Request)` = `False` → FastAPI перестаёт узнавать `Request`/`Response` как special-case инъекции и требует их как query-параметры → `422 missing loc=["query","request"]`. Симптом: логин возвращает 422, а не 500/403. Это проявилось в первой итерации фикса и было最难уловимым.
2. **Образ backend вкомпилирован** (target `production` в `docker-compose.yml`), volume-mount только для `/data/*`. После правок backend-кода — `docker compose build backend`, иначе `docker compose restart` не подхватит изменения.
3. **`portal_base_url` без scheme ломает CSRF.** Значение `"portal.local"` (без `https://`) в `system.json` → `urlparse().scheme=""` → CSRF Origin-проверка (`middleware/csrf.py:56-61`) не матчит ничему → `403 CSRF: Origin mismatch` на local login. Теперь `_schemas.py` имеет `field_validator` на `portal_base_url`, добавляющий `https://` если scheme отсутствует.
4. **Опечатка в имени исключения redis-py** (найдена и исправлена в итерации 17, июль 2026): оригинальный fastapi-limiter ловил `pyredis.exceptions.NoScriptException`, но в redis-py исключение называется `NoScriptError`. При реальном FLUSH/перезапуске Redis (EVALSHA проваливается) `except`-branch искал несуществующий атрибут → `AttributeError` во время обработки исключения → исходный `NoScriptError` терялся, и лимитер падал вместо перезагрузки Lua-скрипта. Исправлено на `NoScriptError`; контракт покрыт `test_patched_call_reloads_lua_script_on_noscripterror`.
5. **Session-fixture `tests/conftest.py::_stub_fastapi_limiter` подменяет `RateLimiter.__call__` no-op'ом** для всех unit-тестов (fakeredis не умеет Lua SCRIPT). Тесты патча ADR-043 поэтому вызывают `patched_call` напрямую — иначе тестировали бы stub, а не реальный патч (что и происходило со старым `test_rate_limiter_skips_routes_without_path`, который passes against no-op). `patched_call` экспортирован из `app/core/limiter.py` на уровне модуля именно для этого.

**Альтернативы и почему отклонены:**
- **Обновить `fastapi-limiter` до 0.2.0** — отклонено: версия полностью переписана на `pyrate_limiter` (breaking changes: `FastAPILimiter` → `RateLimiter` для init, другой API) **и содержит ту же ошибку** `route.path` в `__call__`. Не решает проблему + ломает существующий код.
- **Даунгрейд starlette до 0.x** — отклонено: `66a2fdf` закрывал уязвимость безопасности, даунгрейд её вернёт.
- **Заменить `fastapi-limiter` на другое решение** — отложено: требует рефакторинга всех rate-limited endpoints (8 модулей), отдельная задача.

**Тесты:** `backend/tests/unit/test_limiter.py::test_patched_call_*` (6 тестов) — покрывают все ветки патча: skip-маршрута-без-path, methods-None, custom identifier/callback, NoScriptError-reload (регрессия на багфикс №4), default callback при блокировке, Exception при redis=None. Покрытие модуля 50%→**93%**. Все тесты вызывают `patched_call` напрямую, обходя session-fixture stub.

---

## ADR-044: Observability-стек — Grafana + Loki + Prometheus + Alloy, удаление Sentry (июль 2026)

**Статус:** Принято

**Контекст:**
Портал экспортировал Prometheus-метрики (`/metrics`), но consumer-стороны (централизованные логи, просмотр, alerting) не было: логи жили только в `docker logs` по контейнерам, алерты — только через Sentry (который не использовался и не планировался, SaaS-форма недопустима по политике интранет/VPN, self-hosted Sentry избыточно тяжёл). Требовалось: единый просмотр логов и метрик, alerting на проблемы (5xx, рост очереди аудита, падение воркера), всё offline-capable (интранет).

Слой логирования уже был подготовлен: structlog (`[./backend/app/core/logging.py](../backend/app/core/logging.py)`) отдаёт JSON в production, с contextvars (`request_id`, `service`), redaction секретов/PII — формат нативно совместим с Loki/ELK. `x-logging` anchor (`docker-compose.yml`, ADR-041) использует docker json-file driver с ротацией 50М×5; nginx пишет access-log в `/dev/stdout` через симлинк. Reference-стек Prometheus + Alertmanager + Grafana уже существовал в `monitoring/` (сессия от 2026-07-21) как overlay.

**Решение:**

Расширить существующий overlay `monitoring/docker-compose.monitoring.yml` до полного observability-стека (5 сервисов), **не трогая базовый `docker-compose.yml`**:

```
portal internal-сеть (network internal: true)
  ├─ backend/worker ──stdout(JSON structlog)──┐
  ├─ nginx ──stdout(JSON json_combined)───────┼──► alloy ──► loki ──┐
  └─ backend ──/metrics──────────────────────────► prometheus ──────┼──► grafana (:3001, 127.0.0.1)
                                                                    └──► alertmanager (:9093) ──► email
```

1. **Loki 3.7.3** (`monitoring/loki/config.yml`) — single-binary, retention 30d, compactor. `auth_enabled: false` (закрытый периметр `portal_internal`). Volume `loki-data`.
2. **Alloy 1.18.0** (`monitoring/alloy/config.alloy`) — `loki.source.docker` через Docker socket discovery контейнеров `portal-*`, `stage.docker` + `stage.json` парсинг structlog/nginx. Лейблы `service`/`level` (low-cardinality); `request_id` — **не лейбл** (high-cardinality), ищется через LogQL `| json | request_id="..."`.
3. **Grafana datasource Loki** (`provisioning/datasources/loki.yml`, `uid: loki`) + дашборд `portal-logs.json` (7 панелей: ошибки backend/worker, объём по сервисам/уровням, медленные запросы nginx, 5xx, audit-pipeline, трассировка по `request_id`).
4. **Alertmanager** (`alerts/alertmanager.yml`) — email-receivers через прямой SMTP-relay (env-параметризуемые `${ALERT_SMTP_*}`), независимый от portal email_outbox (критично: алерты уходят даже при падении backend).
5. **Exporters (инфраструктурные метрики)** — 4 exporter'а в `monitoring/docker-compose.monitoring.yml`, подключены к `portal_internal` (видят `postgres`/`redis`/`nginx` по DNS), скрейпятся Prometheus:
   - **postgres-exporter** `prometheuscommunity/postgres-exporter:v0.20.1` (`:9187`) — пул соединений, cache hit ratio, XID wraparound, размер БД, долгие транзакции, дедлоки. `DATA_SOURCE_NAME` собирается из `POSTGRES_*` env.
   - **redis-exporter** `oliver006/redis_exporter:v1.77.0` (`:9121`) — память/evictions, клиенты, keyspace hit rate. `REDIS_PASSWORD` из env.
   - **node-exporter** `prom/node-exporter:v1.12.1` (`:9100`) — диск (критично — `/data/photos`), CPU, RAM, load. Bind-mount `/proc`/`/sys`/`/` read-only.
   - **nginx-exporter** `nginx/nginx-prometheus-exporter:1.4.0` (`:9113`) — active connections, request rate. Скрейпит `stub_status` (`nginx/templates/proxy_locations.conf.tmpl`, точное совпадение `= /stub_status`, доступен только из `172.16.0.0/12`; работает в обоих режимах — HTTP-only и HTTPS).
   - Дашборд `portal-infrastructure.json` (`uid: portal-infra`) — 4 секции: PostgreSQL, Redis, Host, Nginx. Алерты — секции `portal-postgresql`, `portal-redis`, `portal-host`, `portal-nginx` в `portal.yml`.
6. **ARQ job-метрики** — декоратор `track_arq_job` (`backend/app/worker/tasks/metrics.py`) оборачивает все задачи в `WorkerSettings.functions`, пишет `started`/`succeeded`/`failed` + длительность в Redis-хэши (`arq:metrics:jobs`/`job_ms` через атомарный `HINCRBY`). `refresh_custom_metrics` затягивает их в `metrics:snapshot`, middleware гидрирует в `portal_arq_jobs_total{function,status}` / `portal_arq_job_duration_seconds{function}` через delta-increment. Дашборд Overview: failures/started/duration по функциям. Алерт `PortalArqJobFailures`.
7. **Business-метрики (outbox)** — `refresh_custom_metrics` дополнительно считает `count(*) GROUP BY status` для `email_outbox` и `messenger_outbox` (PENDING/DLQ/stale-SENDING), гидрирует в `portal_email_outbox_*` / `portal_messenger_outbox_*`. Без этого копящиеся/DLQ-ящиеся письма невидимы до жалоб юзеров. Алерты `PortalEmailOutboxBacklog/DLQ/Stuck` + mirror для messenger.
8. **Integration probes** — ARQ-cron `probe_integrations` (`backend/app/worker/tasks/integration_health.py`, каждые 60с) проверяет Keycloak (OIDC discovery), Nextcloud (status.php), SMTP (TCP-connect), Collabora (richdocuments). Результат 1/0 → Redis-хэш `integration:health` → gauge `portal_integration_up{integration}`. Не сконфигурированные → no data (не алерт). Алерт `PortalIntegrationDown`. `/ready` endpoint расширен non-fatal проверками тех же интеграций (portal остаётся ready при упавшем Keycloak — local-auth fallback).
9. **Synthetic probes** — ARQ-cron `run_synthetic_probe` (каждые 5 мин) вызывает screenshot-service `/probe` endpoint (Playwright), который логинится (local-auth) и проверяет загрузку SPA. Gauge `portal_synthetic_probe_up/duration_seconds{flow}`. Gated за `PROBE_ADMIN_EMAIL/PASSWORD` env. Алерт `PortalSyntheticProbeFailed`. Ловит regressions end-to-end, невидимые инфра-метрикам.
10. **Удаление Sentry** — полностью вычищен (см. коммит сессии 1): `sentry-sdk` убран из зависимостей, `core/sentry.py` удалён, `sentry_dsn` убран из `SystemSettings`, секция из Admin UI и i18n удалена. Ошибки теперь идут через structlog `logger.exception(...)` → Loki.

Запуск:
```bash
docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml \
  up -d prometheus alertmanager grafana loki alloy
```

**Альтернативы и почему отклонены:**
- **ELK / OpenSearch + Kibana** — отклонено: Elasticsearch прожорлив (~3–4 ГБ RAM), Elastic License 2.0 не чистый OSS. Оверкилл для ~300 юзеров. Loki индексирует только лейблы → лёгкий.
- **Graylog** — отклонено: требует OpenSearch + MongoDB, лишние движки.
- **Promtail вместо Alloy** — отклонено: Promtail в maintenance, Alloy — текущий активный проект Grafana (замена).
- **Перевод `x-logging` anchor на `loki` driver** — отклонено: ломает `docker logs`, риск для prod. Alloy читает поверх json-file driver, переиспользуя существующую ротацию (ADR-041).
- **Self-hosted Sentry** — отклонено: ~20 сервисов (Kafka, PostgreSQL, Redis, ClickHouse), заметно тяжелее всей Grafana-связки.
- **Включение obs-стека в базовый compose** — отклонено: наследуем решение из wip-плана (reference-конфиги в `monitoring/`, тяжёлые образы ~900 МБ не тащатся в базовый деплой).

**Грабли (важно!):**
1. **Loki 3.6+ и Alloy не содержат `wget`/`curl`** (busybox убран, upstream issues grafana/loki#20149, grafana/alloy#477). Встроенный HTTP-healthcheck (`/ready`, `/-/ready`) сделать нечем. Решение: healthcheck убран у обоих, готовность через `restart: unless-stopped` + ручная проверка с хоста.
2. **`${VAR:default}` синтаксис НЕ работает в alertmanager.yml** — Alertmanager (Go) раскрывает только `${VAR}` без дефолта. Дефолты задаются в overlay compose через `${ALERT_SMTP_HOST:-}`.
3. **Фиксированные UID datasource обязательны** (`uid: loki`, `uid: prometheus`) — без них Grafana генерирует случайные UID, дашборды не находят свои datasource'ы.
4. **Alloy `loki.write.endpoint` не имеет `batchwait`/`batchsize`** (это Promtail-атрибуты) — значения по умолчанию разумны (1 МБ/1с).
5. **Mount `alerts/` в prometheus `rules/` ломает Prometheus** — он пытается парсить `alertmanager.yml` как rules-файл и падает. Развели на файловый mount `portal.yml`.
6. **`single_binary` поле удалено в Loki 3.x** (было в 2.x) — вызывает `field single_binary not found` при парсинге. Single-binary теперь режим по умолчанию.

**Тесты:** smoke-тест на живом портале (сессия 2) — Loki `/ready → ready`, Alloy discovery находит все 10 контейнеров, structlog/nginx JSON парсится (service/level/request_id/status), сквозная корреляция nginx-access ↔ backend-request по `request_id`, Prometheus scrape `up`, Grafana автозагружает 2 datasource + 2 дашборда. `amtool check-config` SUCCESS, `alloy fmt --test` + semantic run OK.

**Последствия:**
- Логи централизованы в Loki (retention 30d), просмотр через Grafana (LogQL), больше не нужно `docker logs | grep`.
- Алерты (5xx, audit backlog, worker down) доставляются email админам через независимый SMTP-relay.
- Sentry полностью убран — меньше зависимостей, проще стек, нет внешнего phone-home.
- +~500–650 МБ RAM к overlay (Loki ~400 МБ, Alloy ~150 МБ), базовый compose не затронут.
- Архитектурно готово к добавлению трейсинга (Tempo) — отдельным overlay, Grafana уже есть.

---

## ADR-045: CI-built images в GHCR + pull-based deploy (июль 2026)

**Статус:** Принято

**Контекст:**
Деплой на прод выполнялся как `git pull` + `docker compose up -d --build` — образы собирались прямо на прод-сервере. Пауза при обновлении составляла ~5 минут (билд backend/frontend/nginx), сервер простаивал на компиляции, а откат означал снова `git checkout` + билд (ещё 5 минут и риск — какая именно версия сейчас бежит, было неясно).

Инфраструктура уже была наполовину готова: `docker-compose.yml` использовал `${IMAGE_TAG:-latest}` на 6 из 7 образов (исключения — `redis:7-alpine` upstream и `postgres` с тегом `:16`). Но `IMAGE_TAG` нигде не определялся (разрешался в `latest`), имен образов не было registry-префикса, и ни один CI-job не билдил/пушит образы. CI гонял 15 job'ов (lint/unit/integration/e2e/smoke), но публиковал только отчёты о покрытии.

Репозиторий — публичный (репо `VeryShuu/portal`), интранет-портал для ~300 сотрудников, ~30 секунд паузы при деплое приемлемы (blue-green не требуется).

**Решение:**

Перейти на **pull-based деплой**: CI собирает и публикует образы в GitHub Container Registry (GHCR), прод-сервер тянет готовые образы вместо локальной сборки.

1. **Registry: GHCR** (`ghcr.io/veryshuu/*`). Выбор обоснован:
   - Репозиторий публичный → GHCR **бесплатен безлимитно** (без minute/storage/egress-лимитов для публичных пакетов). Для приватного репо остался бы лимит 500 МБ storage + 1 ГБ egress/мес.
   - Встроенный `GITHUB_TOKEN` с `packages: write` — отдельный PAT не нужен, никаких секретов в workflow.
   - Уже экосистемно: `actions/checkout`, Dependabot, GitHub Issues — всё в одном аккаунте.

2. **Тегирование** (job `publish-images` в `.github/workflows/ci.yml`):
   - На каждый push в `main`: `sha-<7симв>` (точная привязка к коммиту для отката) + `latest` (указатель на HEAD main, continuous deploy).
   - При push semver-tag `v1.2.3`: дополнительно `v1.2.3`, `v1.2`, `v1` (для семантических релизов).
   - `postgres` тегируется единым `:16` (rolling, по major-версии PG) — как и в compose.
   - Job запускается **только на push** (`if: github.event_name == 'push'`), НЕ на `pull_request` — чтобы не пушить с PR-раннеров. Gate: `needs: [backend-lint, backend-unit, backend-integration, frontend-lint, frontend-unit, frontend-e2e, compose-smoke]` — в набор входят ВСЕ критичные job'ы, иначе образ с упавшими интеграционными/e2e ушёл бы в `:latest` (авто-деплой на прод).

3. **IMAGE_PREFIX — конфигурируемый registry-префикс** в `docker-compose.yml`:
   ```
   image: ${IMAGE_PREFIX:-}portal-backend:${IMAGE_TAG:-latest}
   ```
   Пустая `IMAGE_PREFIX` = локальная сборка (dev/staging не ломаются); `ghcr.io/veryshuu/` на проде = pull. Обратно-совместимо: существующие dev-окружения работают без изменений.

4. **6 образов в matrix** (backend с `target: production` используется 3 сервисами — backend/worker/migrations — по одному имени): portal-backend, portal-frontend, portal-nginx, portal-nginx-config, portal-screenshot, portal-postgres. Backend собирается один раз, `cache-from`/`cache-to: type=gha` ускоряет повторные сборки с ~6 до ~2 мин.

5. **`setup.sh` ветвит pull vs build** по `IMAGE_PREFIX` в `.env` (функция `run_compose`): на проде с префиксом — `compose pull` + `up -d` **всегда** (даже при «полном рестарте с очисткой», п.4 меню — на registry-проде локальная сборка не выполняется никогда); без префикса — `build` (`--no-cache` для п.4, инкремент `--build` иначе). Пункты 4 и 6 меню показывают оператору, какой режим применится, заранее.

**Альтернативы, рассмотренные и отвергнутые:**

- **Blue-green (два стека за nginx upstream).** Избыточно: 30 секунд паузы приемлемы для интранет-портала, а blue-green требует обратной совместимости миграций (старый и новый backend одновременно), что не всегда выполнимо.
- **Сборка на проде с разнесением `build` и `up`.** Убирало ~4.5 минуты (билд идёт при работающих контейнерах), но не решало воспроизводимость (какая версия бежит) и не давало лёгкого отката. Подходит как interim-шаг, но registry — правильное решение.
- **Docker Hub.** Для публичных образов безлимитно, но GHCR ближе к коду (один аккаунт, встроенный токен, интеграция с Actions).
- **Self-hosted registry (Harbor/registry:2).** Дополнительная инфраструктура для обслуживания — не оправдано при бесплатном GHCR.

**Грабли / одноразовые шаги:**

1. **Первый пуш в GHCR создаёт package приватным по умолчанию.** После первого успешного `publish-images` зайти на `github.com/users/VeryShuu/packages` и переключить каждый `portal-*` package в **public** — иначе `docker compose pull` на проде упадёт с 401 (анонимный pull приватного пакета запрещён). Для публичного репо это разовый ручной шаг.
2. **Откат = смена `IMAGE_TAG`, не `git checkout`.** Старая док-процедура `git checkout v1.(x-1).x` + `up -d` НЕ меняла образ (тот же тег из registry). Новая процедура: `IMAGE_TAG=sha-<старый>` в `.env` → `pull` → `up -d`. См. `docs/deploy.md` §10.3.
3. **Откат образа ≠ откат миграций.** Образ не делает `alembic downgrade`. Если новая версия накатила миграцию, откат образа оставит схему опередающей — downgrade отдельно через `docker compose run --rm migrations alembic downgrade -1`. Миграции 008→024 необратимы.
4. **`file:` в `build-push-action` — путь от корня репо**, не от `context`. Matrix содержит оба поля явно, чтобы соответствовать `docker-compose.yml` (где `dockerfile` указан относительно `context`).
5. **Actions пинены по SHA** (supply-chain hardening): `docker/login-action@06fb636f…`, `setup-buildx-action@bb05f3f5…`, `build-push-action@53b7df96…`. Dependabot обновит SHA. Floating-теги (`@v7`) можно перезаписать компрометацией репо action'а, а job имеет `packages: write`.

**Последствия:**
- Деплой-пауза: ~5 мин → ~30 сек (pull готовых образов).
- Воспроизводимость: на проде бежит ровно тот образ, что прошёл CI (тег `sha-<7>` однозначно идентифицирует коммит).
- Откат: смена `IMAGE_TAG` в `.env` + `pull` — секунды, а не повторный билд.
- Сервер не занимается компиляцией — CPU свободен для трафика.
- Dev-окружения не затронуты: `IMAGE_PREFIX=` пустая сохраняет локальную сборку.
- +1 CI-job (`publish-images`), ~8–12 мин на полный билд 6 образов (с кэшем ~3–5 мин), параллельно через matrix.

## ADR-046: Разделение контуров dev/prod — prod без клона репозитория (июль 2026)

**Статус:** Принято

**Связь:** Расширяет и уточняет [ADR-045](#adr-045-ci-built-images-в-ghcr--pull-based-deploy-июль-2026). ADR-045 оставил в силе требование `git pull` на проде (для `docker-compose.yml`, `.env`, bind-mount'а `init.sql`); ADR-046 это требование снимает.

**Контекст:**

ADR-045 перевёл деплой на pull-based: образы едут из GHCR. Но на прод-сервере **по-прежнему требовался полный клон репозитория**, потому что три артефакта жилі в дереве исходников:

1. `backend/migrations/init.sql` — bind-mount'ился в postgres как `/docker-entrypoint-initdb.d/01-init.sql:ro` (создаёт FTS-конфиг `russian_hunspell` и расширения при первом старте PG-кластера).
2. `docker-compose.yml` + `.env` — читаются `docker compose` из CWD.
3. `monitoring/docker-compose.monitoring.yml` + дерево `./monitoring/*` — для observability-overlay (см. ADR-044).

Процедура обновления в `docs/deploy.md` §10.1 по-прежнему начиналась с `git pull --ff-only`, а `setup.sh::update_production()` делал то же самое. На прод-сервере оказывалось ~200 МБ дерева исходников (backend/frontend/nginx/postgres/screenshot-service, тесты, доки), которое **никогда не использовалось** для работы портала — только чтобы `docker compose` нашёл compose-файл и init.sql.

Это противоречие (образы из registry, но репо всё равно клонируется целиком) хотелось закрыть: прод должен оперировать минимальным набором файлов, без дерева исходников, тестов, `.git`.

**Решение:**

Разделить два **контура** явно и сделать prod-контур самодостаточным без git-клона.

1. **Запечь `init.sql` в postgres-образ.** Раньше hunspell-файлы (`russian.dict/.affix/.stop`) уже копировались в образ через `postgres/Dockerfile`, а SQL-инициализация (`CREATE EXTENSION`, `CREATE TEXT SEARCH CONFIGURATION`) — bind-mount'илась. Теперь `init.sql` тоже `COPY`'ится в `/docker-entrypoint-initdb.d/01-init.sql`. Образ `portal-postgres:16` становится self-contained. Скрипты в `/docker-entrypoint-initdb.d/*` выполняются **только при первом старте** (пустой `PGDATA`), так что на уже развёрнутых стендах повторного срабатывания не будет — это меняет только источник на новых стендах.

   Чтобы COPY достал до `backend/migrations/init.sql`, build-context postgres поднят с `./postgres` на `.` (precedent: `frontend` уже собирается так). В корневой `.dockerignore` добавлен whitelist:
   ```
   !backend/migrations/init.sql
   !postgres/Dockerfile
   !postgres/hunspell/russian.stop
   ```

2. **Профиль контура (`.portal-profile`).** Машина фиксирует свой тип:
   - `prod` — продакшен: deploy-bundle без клона репо, образы из GHCR (`IMAGE_PREFIX=ghcr.io/veryshuu/`), local-build заблокирован, dev/staging-пункты меню скрыты.
   - `dev` — разработка/staging/CI: полный клон репо, локальная сборка, bind-mount'ы исходников, hot-reload.

   Файл `.portal-profile` machine-local (в `.gitignore`, как `.portal-mode` и `.env`). Default при отсутствии — `dev` (backward-compatible: всё работает как до ADR-046). Профиль выбирается интерактивно в `setup_env()`; он же подставляет `IMAGE_PREFIX` в `.env` автоматически.

   Внимание на разницу: `.portal-mode` хранит **последний запущенный режим** (prod/dev/staging), `.portal-profile` — **тип машины** (prod/dev). Семантически разные.

3. **Гейты в `setup.sh` по профилю:**
   - `run_compose()`: prod-контур + пустой `IMAGE_PREFIX` → явный err (local-build без исходников всё равно упал бы, но с непонятной ошибкой COPY).
   - `show_menu()`: prod-контур скрывает п.2 (Разработка), п.3 (Стейджинг); dev-контур скрывает п.6 (Обновить Production).
   - `main()` case 2/3/6: дублирующий guard на случай прямого ввода цифры.
   - `gen-dev-files`: в prod-контуре блокируется (override'ы со ссылками на `./backend/*` там бессмысленны).
   - `preflight()`: проверяет наличие `docker-compose.yml`, согласованность prod-профиля с `IMAGE_PREFIX`.
   - `update_production()`: если `.git` отсутствует и контур prod — git-pull пропускается тихо (обновление конфигурации делается распаковкой нового bundle).

4. **CI job `deploy-bundle`** (в `.github/workflows/ci.yml`): на релизном теге `v*` собирает tarball `portal-deploy-bundle-<tag>.tar.gz` с минимальным набором:
   - `docker-compose.yml`, `.env.example`, `setup.sh`, `DEPLOY-BUNDLE-README.md`
   - `monitoring/` целиком (overlay-конфиги + `node-exporter-textfile/` для локальной сборки `portal-storage-collector`, который не в registry)

   Исключено: `backend/`, `frontend/`, `nginx/`, `postgres/`, `screenshot-service/`, тесты, `*.md` (кроме README bundle), `.git`, `monitoring/loki/rules/fake/` (тестовые данные), `monitoring/textfile/storage.prom` (runtime, генерируется на месте).

   Tarball аттачится к GitHub Release через `softprops/action-gh-release@3bb12739` (SHA-pinned). Флоу на проде:
   ```
   gh release download v1.2.3 -p 'portal-deploy-bundle-*.tar.gz'
   tar xzf portal-deploy-bundle-*.tar.gz -C /opt/portal
   cd /opt/portal && ./setup.sh   # → п.5 (профиль prod) → п.1 (запуск)
   ```

**Альтернативы, рассмотренные и отвергнутые:**

- **Shallow/sparse git clone на проде.** Меньше автоматизации, но всё ещё требовало git на прод-сервере и `.git`-каталог. Bundle через Release — полностью декларирует состав prod-окружения и не тащит git-инфраструктуру.
- **Ручное копирование `docker-compose.yml` + `.env`.** Просто, но нет версионирования и не покрыт monitoring-overlay. Bundle с CI — воспроизводимо и привязано к релизному тегу.
- **Запечь monitoring-overlay в отдельный образ.** Loki/Prometheus/Grafana уже тянутся из upstream-registry; overlay — это конфиги + одна локальная сборка `portal-storage-collector`. Запекать конфиги в образ ломает ADR-044 (конфиги редактируются через bind-mount без пересборки). Bundle сохраняет текущую модель.

**Грабли / одноразовые шаги:**

1. **Build-context postgres изменился с `./postgres` на `.`** — это видимое нарушение принципа «context = каталог сервиса». Обосновано: нужен COPY файла вне `./postgres`. Альтернатива (sym/hardlink `init.sql` в `./postgres/` перед сборкой) нарушила бы single-source-of-truth. Whitelist в `.dockerignore` удерживает context маленьким (только 3 файла из всего репо).
2. **`init.sql` молча переименовывался в CI:** в compose-bind-mount целевое имя было `01-init.sql`, в CI-`docker run` — `00_init.sql`. После ADR-046 источник один (`COPY ... /docker-entrypoint-initdb.d/01-init.sql`), расхождение исчезло вместе с самими `-v`-mount'ами.
3. **`.portal-profile` default `dev`** — намеренно. Существующие dev-машины и CI-раннеры работают без изменений (никто не создавал `.portal-profile` → `dev` → local-build). Только явный выбор «prod» при `setup_env` переключает машину в registry-режим.
4. **Bundle ~80 КБ** (gzip), собирается за секунды. Не артефакт-гигант, не раздувает Release.

**Последствия:**

- Prod-сервер больше не требует git-клон репозитория: только deploy-bundle (~80 КБ) + образы из GHCR.
- `init.sql` — в образе postgres; bind-mount убран из 5 точек (`docker-compose.yml`, `setup.sh` heredoc, `ci.yml` ×2, `nightly-{flakes,security}.yml`).
- Dev/CI не затронуты: полный клон репо, `generate_dev_files()`, local-build, bind-mount'ы исходников — без изменений. `gen-dev-files` на CI-раннере работает как раньше (там dev-контур).
- Воспроизводимость prod-окружения: bundle версии `v*` ↔ образы того же тега ↔ коммит того же SHA. Три источника согласованы релизным тегом.
- +1 CI-job (`deploy-bundle`), запускается только на теге `v*`, ~30 сек.
- Миграции (`migrate.sh`, compose-сервис `migrations`) — без изменений, работают из образа backend.


## ADR-047: Semver-lock прод-деплоя (июль 2026)

**Статус:** Принято

**Связь:** Уточняет [ADR-045](#adr-045-ci-built-images-в-ghcr--pull-based-deploy-июль-2026) (п.2 тегирования — `:latest` больше не прод-дефолт) и [ADR-046](#adr-046-разделение-контуров-devprod--prod-без-клона-репозитория-июль-2026) (триада bundle↔образы↔commit теперь обязательна).

**Контекст:**

ADR-045 зафиксировал `:latest` как «continuous deploy» — указатель на HEAD main. Любой merge в `main` (включая автоматически смёрженные AI-сгенерированные PR'ы и Dependabot) пушит новый `:latest` в GHCR. На проде, где `IMAGE_TAG=latest` в `.env`, следующий `docker compose pull` забирает эту версию **без явного решения оператора**.

Свойства такого режима, оказывающиеся проблемными для интранет-портала с ручной моделью релиза:

1. **Implicit deploy без approval.** Нет точки «мы решили выкатить релиз X». Выкатка размазана по времени и merge'ам.
2. **«Какая версия на проде» — неизвестно без `docker image inspect`.** В git-истории коммита ≠ то, что бежит в контейнере.
3. **Откат = ручная смена `IMAGE_TAG=sha-XXXXXXX`** (легко забыть, какой SHA был предыдущим). Нет естественной семантики «предыдущий релиз».
4. **Любой merge потенциально едет на прод.** Включая правки, которые не предназначались для немедленного выката (feature-фрагменты, эксперименты, оказавшиеся в main через fast-forward).

Для портала на ~300 сотрудников с ручной моделью деплоя («команда явно решает выкатить v1.5.0») это неправильный дефолт.

**Решение:**

Перевести prod-контур на **обязательный pin к релизному тегу** `v1.x.x` в `.env` (`IMAGE_TAG=v1.x.x`). Прод больше не выкатывается автоматически — только когда оператор сознательно меняет тег.

1. **`IMAGE_TAG=v1.x.x` обязателен для prod-контура.** `setup.sh::preflight()` в prod-профиле (`.portal-profile=prod`) отвергает `IMAGE_TAG=latest` как `fatal=1` с понятным сообщением. Покрыты все точки входа (меню 1/4/6 → все зовут `preflight`).

2. **`:latest` остаётся пушиться в CI** (не убираем тег из publish-images). Это сохраняет обратную совместимость: dev-контур и эксперименты продолжают работать на `:latest`. Запрет — только на уровне prod-профиля в `setup.sh`, не на уровне registry.

3. **`docker manifest inspect` перед `compose pull`** в `run_compose()`: если оператор ошибся в теге (опечатка, тег ещё не опубликован), даёт сразу понятную ошибку с указанием тега и подсказкой, где посмотреть доступные (`gh release list` / вкладка Packages). Без этой проверки `docker compose pull` выдаёт невнятное `manifest unknown` где-то в середине лога.

4. **CI gate `validate-release-tag`** перед `publish-images`: на теге `v*` валидирует формат (`^v[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$`) и привязку тега к коммиту из `main`. Некорректный тег (`v1.5`, `v1.2.3-rc` без номера, `release-1`) → CI красный, образы не пушатся. На main-push job skipped (считается success), `publish-images` работает как прежде.

5. **`scripts/release.sh`** — эргономичная обёртка для ручного релиза: валидирует semver, проверяет чистое git-дерево, синхронизацию HEAD с `origin/main`, отсутствие тега, создаёт annotated tag и пушит. CI `validate-release-tag` остаётся вторым барьером (defense-in-depth, на случай тегирования в обход скрипта).

6. **Postgres остаётся `:16` rolling** (как в ADR-045). Схема БД управляется alembic-миграциями, не версией образа postgres; образ меняется редко (правки `init.sql`/Dockerfile). Pin postgres к semver добавил бы сложность без пропорциональной выгоды.

**Альтернативы, рассмотренные и отвергнутые:**

- **Не пушить `:latest` вообще.** Чище концептуально, но ломает существующий прод на `:latest` моментально и мешает dev/experiments. Запрет на уровне prod-профиля решает главную проблему мягче.
- **GitOps deploy-repo (отдельный репо с `docker-compose.yml` + `.env`, синхронизируемый Argo CD/Flux).** Энтерпрайз-уровень. Для 1 прод-сервера на compose — оверинжиниринг: добавляет инфраструктуру контроллера ради задачи, которую решает одна строка `IMAGE_TAG=v1.x.x` в `.env`.
- **Авто-deploy staging → prod по расписанию.** Не соответствует выбранной ручной модели релиза (см. стратегический выбор в обсуждении процесса). Требует сильного CI и обратной совместимости миграций, чего сейчас нет.
- **Pin postgres к semver через `POSTGRES_TAG`.** Добавил бы переменную и CI-тегирование ради редко меняющегося образа. Отвергнуто, `:16` rolling сохраняется.

**Грабли / одноразовые шаги:**

1. **Существующий прод на `:latest` сломается при следующем `update_production` после применения нового `setup.sh`.** Gate в `preflight` даст `fatal=1`, потребует выставить `IMAGE_TAG=v*` ДО пулла. Это намеренно (явный сигнал «мигрируй»). Порядок описан в `docs/deploy.md` §12 «Миграция с :latest на semver-lock»: сначала затегать текущий main как `v1.0.0`, выставить на проде, потом мёрджить ADR-047.
2. **`docker manifest inspect` требует network до registry.** В air-gap не сработает. Но pull-деплой сам требует сети, так что это не новая зависимость.
3. **Regex `^v[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$` допускает ведущие нули** (`v01.2.3`, `v1.2.3-rc01`). Semver строго запрещает, но для intranet-инструмента это допустимо — не ломает порядок тегов и не создаёт рисков. Если потребуется строгость — отдельная правка regex (одинаковая в CI и release.sh).
4. **Аннотированные теги (`git tag -a`) обязательны.** `release.sh` создаёт именно annotated; lightweight-теги (через `git tag v1.0.0` без `-a`) пройдут валидацию CI, но потеряют метаданные (дату/автора). На практике `release.sh` — единственный рекомендованный путь тегирования.
5. **Теги не переиспользуются.** `release.sh` отвергает существующий тег. Семантические версии — immutable: `v1.0.0` всегда указывает на один коммит. Откат = смена `IMAGE_TAG` на проде, не перезапись тега.

**Последствия:**

- Prod больше не выкатывается автоматически: только явная смена `IMAGE_TAG=v*` в `.env` → `setup.sh` п.6.
- «Какая версия на проде» = значение `IMAGE_TAG` в `.env` (один взгляд, без `docker inspect`).
- Откат = `IMAGE_TAG=v1.x.<предыдущий>` в `.env` → `setup.sh` п.6 (семантически понятно, без поиска SHA).
- Релизный процесс формализован: `./scripts/release.sh <ver>` → ждём CI → выставляем на проде. Защищён от опечаток и тегирования случайных веток.
- Dev/CI не затронуты: `IMAGE_TAG=latest` остаётся корректным дефолтом в dev-контуре (gate не срабатывает, profile=dev).
- +1 CI-job (`validate-release-tag`), ~10 сек, только на тегах `v*`.
- `:latest` продолжает пушиться и быть доступным — для dev/experiments и плавной миграции существующих инсталляций.


