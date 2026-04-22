# Code Review — Phase 0 / 1 / 2 / 2.1

Дата: 2026-04-22
Источник: 3 параллельных subagent ревью (backend opus-4-7-think, frontend gpt-5-3-codex, docs/tests sonnet-4-6-think).

Формат: статус `[ ]` pending → `[x]` fixed. После закрытия всех P0+P1 — переход к Phase 3.

---

## P0 — КРИТИЧНО (блокирует Phase 3)

### Безопасность (XSS / RCE / Open redirect / DoS)

- [x] **P0-1**. XSS в HTML-экспорте новости: `news.title` подставляется в f-string без экранирования.
  - Файл: `backend/app/api/news.py:618-638` (функция `_build_export_html`)
  - Fix: `html.escape(news.title)` + санитизация `news.body` через `bleach.clean()`

- [x] **P0-2**. Raw HTML `news.body` сохраняется без санитизации (XSS при просмотре).
  - Файл: `backend/app/services/news.py::create_news` / `update_news`
  - Fix: `bleach.clean(body, tags=ALLOWED, attributes=...)` перед записью в БД

- [x] **P0-3**. Open redirect в `/auth/login?redirect=...` — нет проверки на относительный путь.
  - Файл: `backend/app/api/auth.py:50-68` (функция `login`)
  - Fix: валидация `redirect_after`: должен начинаться с `/`, не должен начинаться с `//` или `/\`, должен быть в whitelist префиксов

- [x] **P0-4**. DoS через `await file.read()` ДО проверки размера (10 ГБ → OOM).
  - Файлы: `backend/app/api/news.py:208,327,454`, `backend/app/api/users.py:148`
  - Fix: streaming чтение с накоплением + ранний break при `len > MAX`; либо `Content-Length` header check + `request.stream()`

- [x] **P0-5**. MIME-валидация только через `file.content_type` (клиент-поставляемый).
  - Файлы: все upload endpoints (`news.py`, `users.py`)
  - Fix: `python-magic` (`magic.from_buffer(content[:2048], mime=True)`) — проверка реального MIME

- [x] **P0-6**. URL validation на фронте пропускает `javascript:` / `data:` схемы.
  - Файлы: `frontend/src/pages/AdminPage.vue:289`, `frontend/src/pages/LinksPage.vue:191`, `frontend/src/stores/links.ts:75`
  - Fix: `const u = new URL(value); if (!['http:', 'https:'].includes(u.protocol)) throw`

- [x] **P0-7**. Path traversal в `_inline_body_images` (Markdown `![](../../etc/passwd)`).
  - Файл: `backend/app/api/news.py` (функция `_inline_body_images`)
  - Fix: `Path(NEWS_MEDIA_DIR / path).resolve().is_relative_to(NEWS_MEDIA_DIR.resolve())`

### Функциональные баги

- [x] **P0-8**. Broken endpoint `POST /users/admin/sync` — enqueue в несуществующий модуль.
  - Файл: `backend/app/api/users.py:175` enqueue'ит `app.worker.tasks.users.sync_users_from_keycloak`
  - Worker (`backend/app/worker/main.py:26`) знает только `app.worker.tasks.news.sync_users_from_keycloak`
  - Fix: создать `backend/app/worker/tasks/users.py` с задачей или поправить путь enqueue

- [x] **P0-9**. Schema drift: модель `News.body_tsvector: Text` vs миграция `002` создаёт колонку `body_tsv tsvector`.
  - Файлы: `backend/app/models/news.py:40`, `backend/migrations/versions/002_news.py:47-58`
  - Index `idx_news_fts` создан на `body_tsv`, модель ссылается на `body_tsvector` — FTS не работает
  - Fix: переименовать в одном месте (предпочтительно — модель синхронизировать с миграцией, изменить тип на `TSVECTOR`)

- [x] **P0-10**. FastAPI dependency injection через `= ...` Ellipsis default ломает inject.
  - Файл: `backend/app/api/news.py:369-370` (функция `reorder_gallery`)
  - Fix: убрать `= ...`, оставить только тип-аннотацию (`editor: EditorDep, db: DbDep`)

- [x] **P0-11**. `target_roles` в новостях сохраняется, но НЕ применяется в фильтре таргетинга.
  - Файл: `backend/app/services/news.py:17-31` (функция `_targeting_filter`)
  - Fix: добавить условие `or_(News.target_roles.is_(None), News.target_roles == [], News.target_roles.contains([user.role]))`

### Контракты (docs vs реализация)

- [x] **P0-12**. Draft endpoint: docs `{draft_title, draft_body}`, код принимает `UpdateNewsRequest` (`{title, body, ...}`).
  - Решение: правим docs под код (имена полей `title`/`body` уже используются фронтом)
  - Файл: `docs/api-contracts.md:508-513`

- [x] **P0-13**. Пагинация: docs декларируют `?limit=20&offset=0`, код использует `?page=1&page_size=20` (для `/news`, `/users`).
  - Решение: правим docs (фронт уже работает с `page/page_size`)
  - Файл: `docs/api-contracts.md` все list-endpoints

- [x] **P0-14**. Bookmarks DTO рассинхрон: docs `{resource_title, resource_url, order_index}`, код `{title, url, sort_order}`.
  - Решение: правим docs (БД и код уже на этих именах, миграция 003)
  - Файл: `docs/api-contracts.md:810-844`

---

## P1 — СЕРЬЁЗНО

### Безопасность

- [x] **P1-15**. CSRF: `SameSite=Lax` без Origin/Referer-check (заявлено в ADR-013, в коде нет).
  - Файл: `backend/app/main.py` (middleware) — добавить middleware проверки `Origin` для POST/PUT/PATCH/DELETE

- [x] **P1-16**. Account-linking без проверки `email_verified` claim — риск takeover bootstrap-admin.
  - Файл: `backend/app/api/auth.py::_upsert_user`
  - Fix: при account-linking требовать `claims.get("email_verified") is True`, иначе 403

- [x] **P1-17**. bcrypt SHA256 pre-hash — нестандартное решение (несовместимость с внешними утилитами).
  - Решение: задокументировано в ADR-018 (truncation 72-байт обходим pre-hash, alternatives отвергнуты)
  - Файл: `backend/app/core/security.py:21-23`
  - Fix: либо документировать в ADR (если truncation 72-байт нужен), либо убрать pre-hash

- [x] **P1-18**. Playwright launch per-request — 1-2 сек latency + OOM при concurrent.
  - Файл: `backend/app/api/news.py` (функция `_render_pdf`)
  - Fix: browser pool в lifespan (singleton `browser`, contexts per-request)

- [x] **P1-19**. Sync I/O в async handler (`with open() as f: f.write(content)`).
  - Файлы: `backend/app/api/news.py:221`, `backend/app/api/users.py:157`, `backend/app/api/news.py:349,464`
  - Fix: `aiofiles.open(...)` или `asyncio.to_thread(...)`

- [x] **P1-20**. Race в `_upsert_user` при concurrent первом логине одного email.
  - Файл: `backend/app/api/auth.py:317-374`
  - Fix: `pg_advisory_xact_lock(hash(email))` перед SELECT

- [x] **P1-21**. Утечка Redis-соединений (нет close в lifespan).
  - Файл: `backend/app/main.py` lifespan / `backend/app/core/redis.py`
  - Fix: `await redis_client.close()` в shutdown

- [ ] **P1-22**. Audit events отсутствуют для удаления cover/gallery/attachment.
  - Файл: `backend/app/api/news.py` (функции `delete_news_cover`, `delete_gallery_image`, `delete_attachment`)
  - Fix: добавить `push_audit_event` с типами `news.cover_deleted`, `news.gallery_image_deleted`, `news.attachment_deleted`

- [x] **P1-23**. `startsWith('/')` пропускает `//evil.tld` (protocol-relative redirect).
  - Файл: `frontend/src/pages/LoginPage.vue:181`
  - Fix: `/^\/(?!\/)/.test(rawRedirect)` + проверка отсутствия `\\`

- [x] **P1-24**. CSP заголовок не выставляется в nginx SPA-конфиге (заявлен в ADR-013).
  - Файл: `frontend/nginx.spa.conf`
  - Fix: `add_header Content-Security-Policy "default-src 'self'; ..." always;` одной строкой

- [x] **P1-25**. Memory leak: `addEventListener('keydown')` без `removeEventListener` (HMR + setup re-run).
  - Файл: `frontend/src/components/AppLayout.vue:320-323`
  - Fix: `onMounted` + `onBeforeUnmount` с явным `removeEventListener`

- [x] **P1-26**. Race autosave vs save (оба PUT одновременно при клике "Опубликовать" пока крутится autosave).
  - Файл: `frontend/src/pages/NewsFormPage.vue:314-322,469-480`
  - Fix: `if (saving.value) return` в autosave; либо `AbortController` отменяющий autosave при manual save

- [ ] **P1-27**. `download_url` ожидается фронтом, но не задокументирован в API-контракте.
  - Файл: `docs/api-contracts.md:583-589` (response schema attachments)
  - Fix: добавить поле `download_url: string` в schema `AttachmentPublic`

- [ ] **P1-28**. DELETE /news: матрица `roles-matrix.md` admin-only, код позволяет editor+admin.
  - Решение: оставить editor+admin (фактическое поведение); поправить матрицу
  - Файл: `docs/roles-matrix.md`

### Frontend контракты

- [x] **P1-29**. Поиск без `AbortController` — race на быстром вводе в `GlobalSearch.vue`.
  - Файл: `frontend/src/components/GlobalSearch.vue`
  - Fix: AbortController + cancel предыдущего запроса

- [ ] **P1-30**. E2E-тесты глотают ошибки через `.catch(() => {})`.
  - Файл: `frontend/tests/e2e/*.spec.ts`
  - Fix: убрать catch'и, явно проверять ожидаемые failure-модели

---

## P2 — Минорно

- [ ] **P2-31**. `tests/unit/test_links_bookmarks.py::test_bookmark_reorder` — assertion `bms[0].id == bms[1].id` всегда False.
  - Fix: переписать assertion на корректную проверку sort_order

- [ ] **P2-32**. `docs/db-schema.md` упоминает поля `draft_title`, `draft_body`, `updated_by`, отсутствующие в миграциях.
  - Fix: убрать из docs или пометить "запланировано v2"

- [ ] **P2-33**. `docs/db-schema.md` использует `order_index`, миграции и модели — `sort_order`.
  - Fix: глобально переименовать в docs на `sort_order`

- [ ] **P2-34**. `docs/api-contracts.md` GET /ready: docs указывают `nextcloud` check + `"degraded"` статус, код возвращает только `db`+`redis` + `"error"`.
  - Fix: правим docs под текущую реализацию, добавляем nextcloud-check после разблокировки Phase 5

- [ ] **P2-35**. `/auth/me` не возвращает `auth_source`, фронт не может определить тип аккаунта.
  - Fix: добавить `"auth_source": user.auth_source` в `backend/app/api/auth.py:269-285`

- [ ] **P2-36**. `/news` query-параметры `category` и `is_pinned` задокументированы, но не реализованы.
  - Fix: добавить параметры в `list_news` и фильтры в `get_news_list`

- [ ] **P2-37**. `service_links` поля `description` и `updated_at` в коде, но не в `db-schema.md`.
  - Fix: дополнить docs

- [ ] **P2-38**. `idx_users_source` создаётся в миграции 004, в docs показан в исходной таблице users.
  - Fix: пометка `(добавлен в 004)`

- [ ] **P2-39**. `audit_log.user_id` — без FK, в ERD-диаграмме показано как связь без уточнения.
  - Fix: явная пометка "no FK" в легенде ERD

- [ ] **P2-40**. `news_versions.version_number` в docs vs `version` в коде.
  - Fix: правим docs

- [ ] **P2-41**. Roles-matrix указывает пути `/admin/users/sync`, `/admin/users/{id}/role`; код — `/users/admin/sync`, `/users/admin/{id}/role`.
  - Fix: правим docs

---

## Тесты — пропуски (T-серия)

- [ ] **T1**. Нет API integration-тестов через `httpx.AsyncClient(app)` + Testcontainers (только `test_migrations.py`).
  - Fix: создать `backend/tests/integration/test_api_*.py` с реальным приложением

- [ ] **T2**. News gallery/attachments/export — ноль тестов.
  - Fix: `tests/unit/test_news_media.py` + integration

- [ ] **T3**. Upload-ветки 413/422/404 не покрыты.

- [ ] **T4**. Account-linking логика только булевыми mock'ами, без реального DB-сценария.
  - Fix: integration test `existing local user with same email + Keycloak login → linked, role preserved`

- [ ] **T5**. Bootstrap-admin race с pg_advisory_xact_lock — без integration-теста.

- [ ] **T6**. `pg_advisory_xact_lock` в bookmarks reorder + concurrent POST не тестируется.

- [ ] **T7**. `services/audit.py::push_audit_event` — ноль тестов.
  - Fix: unit + проверка graceful fail при Redis-ошибке

- [ ] **T8**. Rate-limit 5/15 min на `/auth/local/login` — нет теста превышения.

- [ ] **T9**. `PATCH /me/preferences`, `POST /me/avatar` (413, 422), смена пароля (403 для Keycloak-пользователя) — не покрыты.

- [ ] **T10**. Frontend E2E — только 2 тривиальных теста (redirect, spinner). Нужны: login flow (local + SSO), news CRUD + cover upload, bookmarks drag-n-drop, gallery upload + reorder, attachment download.

- [ ] **T11**. `services/session.py::get_session_from_request` — без тестов.

- [ ] **T12**. `api/links.py` — `GET /{id}/sso-url` (с/без id_token, 404), `PUT/DELETE /{id}` 403 для reader — нет тестов.

- [ ] **T13**. `api/users.py admin/local` — 409 (email exists), 403 (local_auth disabled) — не покрыто.

---

## Открытые вопросы (требуют решения до начала работ)

- **B1**. Phase-3 KB endpoint `/kb/articles/{id}/draft` — какие имена полей? (унифицировать с news)
- **B2**. Включать ли `bleach`-санитизацию для всех Markdown-полей или только для tipTap-редактора?
- **B3**. Browser pool для PDF — singleton или pool на N контекстов? (300 пользователей, оценочно ≤5 concurrent PDF)
- **B4**. CSRF middleware — global или per-route декоратор?
- **B5**. Email-verified gate для account-linking — при отсутствии claim'а отклонять или fallback на server-config flag?

---

## Порядок исполнения

1. **Этап A — P0 security**: 1, 2, 3, 4, 5, 6, 7
2. **Этап B — P0 functional**: 8, 9, 10, 11
3. **Этап C — P0 contract sync (docs)**: 12, 13, 14
4. **Этап D — P1 security**: 15, 16, 17, 23, 24
5. **Этап E — P1 perf/leaks**: 18, 19, 20, 21, 25, 26, 29
6. **Этап F — P1 audit + контракты**: 22, 27, 28, 30
7. **Этап G — Тесты**: T1-T13 (приоритет T1, T2, T4, T7, T10)
8. **Этап H — P2 cleanup docs**: 31-41

После закрытия A-F + T1+T2+T4+T7 → переход к **Phase 3 (KB + Search)**.
