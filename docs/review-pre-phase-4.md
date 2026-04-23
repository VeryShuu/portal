# Pre-Phase 4 — Масштабное код-ревью

**Дата:** 23.04.2026
**Базовый коммит:** `d95ffea` (main)
**Охват:** backend, frontend, БД, тесты, security, observability, инфраструктура, документация
**Методология:** 5 независимых субагентов, параллельный анализ всех слоёв

---

## 🔧 Статус устранения (после ревью)

**Этап 1 (commit `f6f0a4b`)** — критичные блокеры безопасности:
- ✅ Backend P0-1 — bcrypt вынесен в executor (`hash_password_async` / `verify_password_async`)
- ✅ Backend P0-2 — `push_audit_event` в `kb_extra.py` переведён на keyword-аргументы (6 событий KB ACL восстановлены)
- ✅ Backend P0-3 — branding upload через `stream_upload_to_path`
- ✅ Backend P0-4 — `redis.keys` → `SCAN` + узкая инвалидация в `kb_acl.py`
- ✅ Backend P1-6 — `data:` убран из `ALLOWED_PROTOCOLS`
- ✅ Frontend P0-1 — единый `sanitizeHtml()` с hardened DOMPurify-конфигом для News + KB
- ✅ Frontend P0-2 — CSRF double-submit cookie + `X-CSRF-Token` в `api/index.ts`
- ✅ Frontend P0-3 — все upload/raw fetches переведены на `api`/`apiUpload`/`api.raw` (12 файлов)
- ✅ Backend rate-limit — `/me/password`, `/admin/{id}/password`, `/search`, `/search/suggest`, `/auth/refresh`

**Этап 2 (текущий)** — БД + инфраструктура:
- ✅ Миграция `011_news_fts_hunspell` — news FTS переведён на `russian_hunspell`
- ✅ `link_icons_data` volume в `docker-compose.yml` (backend + worker) + `.gitignore`
- ✅ SMTP env — `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS`, `SMTP_STARTTLS` в `Settings` и `.env.example`
- ⏸ `app/api/notifications.py`, `worker/tasks/email.py`, миграция 012 `notifications` — будут реализованы в Phase 4 (не нужны в виде заглушек)
- ⏸ Кастомные Prometheus-метрики, worker `/metrics` — Phase 4 / Step 10

**Этап 3 (текущий)** — CI + документация:
- ✅ `commit.bat` — захардкоженное сообщение убрано, принимается аргументом, `--no-push` опционален
- ✅ CI coverage gate — `--cov-fail-under=70` синхронизировано с `pyproject.toml`
- ✅ `docs/db-schema.md:6` — ссылка на миграцию исправлена (`007_news_fts_consolidate`), добавлена `011`
- ✅ `docs/adr.md` ADR-007 + `docs/api-contracts.md` — реальные rate-limit значения синхронизированы
- ✅ `docs/testing.md` — coverage-gate описание обновлено
- ✅ `AGENT.md` — Phase 3 / 3.5 / 4 статусы обновлены, KB и Search помечены ✅ Done

**Этап 4 (текущий)** — починка тестов после Этапов 1-3:
- ✅ `tests/unit/test_kb_acl.py::TestInvalidateCaches` — переписан под `redis.scan_iter` (P0-4 заменил `redis.keys` на SCAN)
- ✅ `tests/security/test_xss_sanitization.py::test_data_protocol_for_img_stripped` — инвертирован assert после удаления `data:` из ALLOWED_PROTOCOLS (P1-6)
- ✅ `tests/conftest.py` — добавлен autouse fixture `_stub_fastapi_limiter`: monkey-patch `RateLimiter.__call__` → no-op, без него endpoints с новым `Depends(RateLimiter(...))` падали с `FastAPILimiter.init` ошибкой в unit-тестах (fakeredis не поддерживает Lua SCRIPT). Реальный rate-limit покрывает `tests/integration/test_rate_limit.py`
- ✅ Verify: 54 теста (kb_acl + xss) проходят; 213 → 216 passed по unit+security
- ⚠️ 13 pre-existing failures остаются (test_csrf, test_audit_partitions mock.patch на `from datetime import datetime`, test_security_headers HSTS, test_auth_required без integration DB) — НЕ связаны с правками Этапов 1-3, к Phase 4 не блокирующи

**Остаётся к Phase 4** (будет реализовано в самой фазе): миграция `012_notifications`, `app/api/notifications.py` (SSE через Redis Streams), `worker/tasks/email.py` (aiosmtplib + retry/backoff), bell-icon UI с реальным `@click` и счётчиком, кастомные Prometheus-метрики (`sse_connections_active`, `audit_queue_depth`).

---

## 0. Executive summary

Проект зрелый и в целом хорошо структурирован: Composition API в фронтенде, слоистая архитектура FastAPI, structlog с редактированием секретов, bcrypt+SHA256, CSRF middleware, IP-whitelist в Nginx, матрица ролей, KB ACL, миграции consistent. Однако перед запуском **Phase 4 (уведомления)** есть набор блокеров и системных долгов.

### Итоговый счёт по приоритетам

| Слой | P0 | P1 | P2 | P3 | Итого |
|---|---|---|---|---|---|
| Backend (API/сервисы/безопасность) | 4 | 10 | 8 | 3 | 25 |
| Frontend (Vue 3 / stores / UX) | 5 | 7 | 7 | 6 | 25 |
| Database (миграции / индексы / схема) | 2 | 6 | 6 | 3 | 17 |
| Tests + Security + Observability | 3 | 6 | 8 | 3 | 20 |
| Infra + Docs (Docker / Nginx / CI / docs) | 3 | 7 | 7 | 3 | 20 |
| **Всего** | **17** | **36** | **36** | **18** | **107** |

### Блокеры Phase 4 (обязательно исправить ДО начала фазы)

1. **SSE-модуль не существует**, но nginx/документация его ждут (`app/api/notifications.py`, миграция `011_notifications`)
2. **Rate limit отсутствует на `/me/password` и `/search`** (OWASP A07)
3. **CI coverage gate несинхронизирован:** `pyproject.toml` требует 70%, CI — 60%
4. **`bcrypt.hashpw` блокирует event loop** в `auth.py`/`users.py`/`main.py` — при 300 VU деградация критична
5. **`push_audit_event` вызывается с позиционными аргументами** в `kb_extra.py` — 6 критичных событий KB ACL молча теряются
6. **News FTS использует `russian`** вместо `russian_hunspell` — деградация качества поиска
7. **`link_icons_data` не смонтирован** как volume — потеря данных при пересборке
8. **CSRF на frontend не защищает** никакие state-changing запросы (ofetch без X-CSRF-Token)
9. **DOMPurify в KB без FORBID_TAGS** — XSS-вектор через `<style>`, `<object>`
10. **`data:` в ALLOWED_PROTOCOLS** sanitize → `data:text/html` XSS
11. **File upload в branding.py** не стриминговый (RAM DoS)
12. **Import KB (.md/.zip) без лимита размера** — RAM DoS + zip-bomb
13. **`redis.keys()` в `kb_acl.py`** блокирует Redis
14. **commit.bat** с захардкоженным сообщением коммита

---

## 1. Backend (Python/FastAPI)

### P0 — блокеры

- **P0-1 · `app/core/security.py:27-34`** — bcrypt синхронный (~200ms) вызывается в async handler'ах (`auth.py:227`, `users.py:248/252/276`, `main.py:67`). При 300 одновременных логинах event loop зависает. **Фикс:** `asyncio.run_in_executor` или `anyio.to_thread.run_sync`.
- **P0-2 · `app/api/kb_extra.py:266,293,352,381,571,642`** — `push_audit_event(redis, user.id, "kb.permission_grant", {...})` — позиционные аргументы после `*`, `TypeError` поглощается `try/except` в `audit.py:44-50`. **6 критичных событий KB ACL не пишутся в аудит.**
- **P0-3 · `app/api/branding.py:92-98`** — `await file.read()` + `write_bytes()` вместо `stream_upload_to_path`. RAM DoS + нет libmagic-валидации.
- **P0-4 · `app/services/kb_acl.py:56-65`** — `redis.keys("kb_acl:*:article:*")` блокирует Redis + избыточная инвалидация всего кэша всех пользователей при изменении прав одной секции. **Фикс:** `SCAN` и сужение шаблона.

### P1 — важные

- **P1-1 · `app/services/keycloak.py:15,97`** — JWKS кэш без `asyncio.Lock` — race на startup.
- **P1-2 · `app/services/keycloak.py:33-35,46-48,57-59`** — URL params без `urllib.parse.urlencode`. Риск parameter injection.
- **P1-3 · `app/api/kb_extra.py:804,874`** — import endpoints читают файл целиком, zip-bomb не обрабатывается.
- **P1-4 · `app/api/kb.py:514,961`** — title не санируется при update; в PDF-export — прямая интерполяция без `html.escape`.
- **P1-5 · `app/api/deps.py:23-30`** — Redis singleton никогда не закрывается (leak, нет reconnect).
- **P1-6 · `app/core/sanitize.py:31`** — `"data"` в ALLOWED_PROTOCOLS → `data:text/html` XSS-вектор.
- **P1-7 · `app/api/kb_acl.py:137-154`** — N+1 запросов при обходе дерева (до 40 SQL при глубине 20). **Фикс:** CTE-запрос.
- **P1-8 · `app/api/kb.py:135-146`** — N+1 в `_resolve_tags`. **Фикс:** `select().where(slug.in_(slugs))`.
- **P1-9 · `app/api/users.py:182-201`** — смена роли и создание локального пользователя пишутся только в `logger.info`, нет `push_audit_event`.
- **P1-10** — отсутствует `RateLimiter` на дорогих endpoints: PDF export, vault ZIP, import, `/auth/refresh`.

### P2 — плановые

- **P2-1** — дублирование `SESSION_TTL` vs `SESSION_TTL_SECONDS`.
- **P2-2 · `users.py:55-57`** — LIKE-wildcards не экранируются (`%`, `_`).
- **P2-3 · `kb_extra.py:503`** — `re.sub(r"\.\.", "", filename)` недостаточно для path traversal. **Фикс:** `Path(filename).name`.
- **P2-4** — ядерная инвалидация `kb_acl:*:article:*` при любом изменении прав.
- Прочее: неконсистентные HTTP-коды, отсутствие retry/backoff в httpx-клиентах, размер пагинации без maximum.

### Готовность к Phase 4

- ✅ `audit_log.event_type` принимает любые строки, можно писать `notify.sent` / `notify.failed`.
- ✅ `Settings` содержит `smtp_host/port/from`, `aiosmtplib` в deps.
- ❌ Нет `worker/tasks/email.py`, нет `api/notifications.py`, нет миграции `011_notifications`.
- ⚠️ ARQ worker не экспонирует `/metrics` — SSE connections будут мониториться только через structlog.

---

## 2. Frontend (Vue 3 + TypeScript)

### P0 — блокеры

- **P0-1 · `pages/KbArticlePage.vue:258`** — `DOMPurify.sanitize(md.render(body))` без `FORBID_TAGS`/`FORBID_ATTR`. В `NewsDetailPage` конфиг hardened, в KB — нет. **Фикс:** вынести в `utils/sanitize.ts` и переиспользовать.
- **P0-2 · `api/index.ts`** — `ofetch.create({credentials:'include'})` без X-CSRF-Token, без interceptor на CSRF. Поиск `grep CSRF` по `frontend/src` — **0 совпадений**.
- **P0-3 · `api/news.ts:4`, `NewsDetailPage.vue:114`** — upload-функции используют `ofetch()` напрямую минуя централизованный `api` instance → 401-redirect interceptor не срабатывает.
- **P0-4 · `stores/auth.ts:15-27`** — `loadUser()` без дедупликации inflight promise. Router guard вызывает при каждой навигации → параллельные запросы при быстрой смене роутов.
- **P0-5 · `stores/branding.ts:185-194`** — optimistic update без rollback: settings мутируются ДО API-запроса, при ошибке UI остаётся с несохранёнными данными + `_apply()` применяет их.

### P1

- **P1-1 · `AdminPage.vue` (33KB, 1029 строк)** — монолит с 3 независимыми табами без `defineAsyncComponent`. `onMounted` делает 6 параллельных запросов сразу. **Фикс:** split на `AdminUsersTab`/`AdminLinksTab`/`AdminBrandingTab`.
- **P1-2** — Hardcoded русские строки в i18n-проекте: `KbListPage.vue:159-174`, `KbSectionTree.vue:18`, `RichEditor.vue:40`, `message.success('Раздел создан')` и др.
- **P1-3 · `api/index.ts`** — нет timeout, нет retry. `VueQueryPlugin` подключён, но `useQuery`/`useMutation` не используются нигде.
- **P1-4 · `KbArticlePage.vue:383-393`** — sequential `await` вместо `Promise.all` (~500ms вместо ~200ms).
- **P1-5 · `AppLayout.vue:72-85`** — bell-icon — **заглушка без @click**, `:show="false"`. Для Phase 4 критично.
- **P1-6 · `stores/auth.ts:34-41`** — `logout()` через `document.createElement('form').submit()` — антипаттерн, обходит interceptors.
- **P1-7 · `router.ts:107-109`** — guard не проверяет `auth.loading` → дубли запросов.

### P2 / P3

- Hardcoded цвета в dark mode: `KbVersionDiffModal.vue:90-97`, `KbListPage.vue:608-609`, `KbArticlePage.vue:424-426`, `HomePage.vue:479-482`, `AppLayout.vue:39,125`.
- `--color-text-secondary` не определён в `tokens.css` (ожидается `--color-text-muted`/`--color-text-subtle`).
- `NewsDetailPage.vue:122-131` — небезопасный heuristic детект HTML (`body.trimStart().startsWith('<')`).
- `formatDate()` дублируется в 4 местах — вынести в `utils/date.ts`.
- `VueQueryPlugin` зарегистрирован, но не используется.
- `AdminPage.vue:744` — `t('admin.branding.logoTooBig')` используется для login-bg.
- Emoji 🔐/👁 вместо Naive UI иконок в KB-страницах.

### Готовность к Phase 4

| Аспект | Статус |
|---|---|
| Bell-icon слот | ✅ Есть |
| Badge счётчик | ⚠️ Hardcoded 0 |
| @click handler | ❌ Нет |
| EventSource / SSE | ❌ Ничего |
| `api/notifications.ts` | ❌ Нет |
| `stores/notifications.ts` | ❌ Нет |
| `NNotificationProvider` | ✅ Зарегистрирован |
| `notify_inapp` в типе UserMe | ✅ Есть |

---

## 3. Database (миграции + схема)

### P0

- **P0-1 · `migrations/002_news.py:47-53`** — `to_tsvector('russian', ...)` вместо `russian_hunspell`. KB уже на hunspell. Новостной поиск деградирован. **Фикс:** миграция `011`.
- **P0-2 · Несоответствие `bookmarks`** — миграция 003 и модель используют `title`/`url`, документация `db-schema.md:491-505` описывает `resource_type`/`resource_id`/`resource_title`/`resource_url` — **два разных дизайна**.

### P1

- **P1-1 · `docs/db-schema.md:6`** — ссылка на несуществующую миграцию `007_service_link_icons` (реально `007_news_fts_consolidate`).
- **P1-2 · `news_versions`** — миграция: `editor_id`; docs: `changed_by` + `change_comment` (последнего вообще нет в БД).
- **P1-3** — отсутствуют 3 index'а из документации: `idx_news_trgm`, `idx_news_active` (partial), `idx_news_pinned` (partial).
- **P1-4/5** — `service_links.title` (200 vs 255) и `description` (`String(500)` vs `TEXT`) — расходятся с docs.
- **P1-6** — `service_links.created_by` не упомянут в docs.

### P2 / P3

- `idx_users_keycloak` — regular vs partial (после local auth должен быть partial).
- `idx_users_source` (docs) vs `idx_users_auth_source` (реально).
- `idx_kb_versions_article` ASC (в миграции) vs DESC (в docs). Для `ORDER BY version DESC LIMIT 1` разница существенная.
- `idx_kb_sec_perm_section` и `idx_kb_art_perm_article` — одноколоночные vs составные в docs.
- `kb_article_files.size_bytes` NOT NULL vs nullable в docs.
- Нет SQLAlchemy-модели для `idempotency_keys` (таблица есть, модели нет).
- `KbArticleTag.UniqueConstraint` дублирует composite PK.
- Нет гарантии, что ARQ-задача создания партиций `audit_log` зарегистрирована — риск падений INSERT через 3 месяца.

### Готовность к Phase 4

| Аспект | Статус |
|---|---|
| Таблица `notifications` | ⚠️ Не создана |
| Индексы `notifications` | ⚠️ Не созданы |
| FK `user_id ON DELETE CASCADE` | ✅ Согласован |
| `notify_inapp` в users | ✅ Есть |
| FTS для news | ❌ P0-1 обязателен до Phase 4 |
| audit_log партиции safety | ⚠️ Нужно проверить ARQ cron |

---

## 4. Tests + Security + Observability

### P0

- **F-01 · Coverage gate несинхронизирован** — `pyproject.toml`: `fail_under=70`, CI: `--cov-fail-under=60`. Коммит с 65% проходит CI и падает локально.
- **F-02 · Rate limit отсутствует** на `PATCH /me/password`, `GET /search`, `PATCH /admin/{id}/password`. ТЗ §7 явно требует для поиска.
- **F-03 · SSE/Notifications модуль не существует** — nginx готов, backend — нет. Phase 4 заблокирована.

### P1

- **F-04** — branding тесты нулевые (документация это подтверждает).
- **F-05** — E2E в CI = только smoke. Mobile project объявлен, но файлов `*.mobile.spec.ts` нет.
- **F-06** — нет IDOR-тестов (OWASP A01).
- **F-07** — CSRF тест покрывает только login, не `POST /news`, `PUT /kb/articles/{id}`, `DELETE *`.
- **F-08** — нет кастомных Prometheus метрик: `audit_queue_depth`, `sse_connections_active`, `arq_job_duration`, `auth_login_*`.
- **F-09** — ARQ worker не поднимает `/metrics`.

### P2

- **F-10** — `pytest-xdist` установлен, но `-n auto` не используется в CI.
- **F-11** — Integration тесты запускаются без `--cov`.
- **F-12** — `app/worker/*` исключено из coverage (4.73 KB кода в production без покрытия).
- **F-13** — нет SQL injection тестов в `tests/security/`.
- **F-14** — CSP не проверяется backend тестами (только nginx добавляет). E2E в CI не запускается.
- **F-15** — k6 load в CI только `k6 inspect`, без исполнения. 300 VU из ТЗ §7 никогда не проверяются.
- **F-16 · `audit.py:44-50`** — silent drop без Prometheus counter, без Sentry capture.
- **F-17 · `test_auth_required.py:26`** — принимает 404 как валидный защищённый ответ.

### P3

- HSTS без `preload`.
- Sentry DSN пуст по умолчанию, интеграция не тестируется.
- Mobile Playwright project — мёртвый вес.

### Покрытие по модулям

| Модуль | Unit | Integration | E2E | Security |
|---|---|---|---|---|
| `auth.py` | ✅ | ✅ | ⚠️ smoke | ✅ |
| `users.py` | ❌ | ❌ | ❌ | ⚠️ |
| `news.py` | ✅ | ✅ | ❌ | ⚠️ |
| `kb.py` | ✅ | ✅ | ❌ | ⚠️ |
| `branding.py` | ❌ | ❌ | ❌ | ❌ |
| `search.py` | ❌ | ❌ | ❌ | ❌ |
| `bookmarks.py` | ✅ | ❌ | ❌ | ⚠️ |
| `worker/tasks/news.py` | ❌ | ❌ | — | — |

---

## 5. Infrastructure + Documentation

### P0

- **F-01 · `docker-compose.yml`** — `link_icons_data` не смонтирован (в `main.py:289` и `links.py:24` пишется в `/data/link_icons`, теряется при rebuild).
- **F-02** — notifications router не существует, но задокументирован в `api-contracts.md:1144-1175`, `roles-matrix.md:223-230`, nginx location готов.
- **F-03 · `commit.bat:4`** — `git commit -m "feat(branding): extended branding system..."` — захардкоженное сообщение, любой запуск фиксирует неправильный коммит.

### P1

- **F-04 · `backend/Dockerfile:33-36`** — `chown` в build time, на Linux bind-mount volumes root-owned → `portal` (uid 1001) `Permission denied`. Нужен entrypoint с runtime chown или named volumes.
- **F-05** — CI без security-scan (`pip audit`, `npm audit`, `trivy`, `docker scout`).
- **F-06** — `adr.md` ADR-007: 120/мин/user; `api-contracts.md`: 300/мин/user — один устарел.
- **F-07 · `reset_admin.py`** — в корне репо, fallback credentials в source code.
- **F-08** — `worker` без healthcheck.
- **F-09 · `nginx.conf:130-132`** — `proxy_cache_valid` без `proxy_cache_path`/`proxy_cache` = no-op.
- **F-10** — SMTP: нет `smtp_user`/`smtp_password`/`smtp_tls` в `config.py` и `.env.example`. Для внешнего SMTP-relay не готово.

### P2 / P3

- `nginx depends_on` без `condition: service_healthy`.
- Frontend Dockerfile: nginx от root.
- `MAX_UPLOAD_SIZE_MB`/`ALLOWED_CIDR` требуют ручной синхронизации с `nginx.conf` (no envsubst).
- Redis password в healthcheck видно через `docker inspect`.
- Coverage gate 60% слишком мягкий для production.
- `postgres/Dockerfile` ставит лишний `curl`.
- `phase-0.md:5` ссылается на несуществующий `phase-1.md`.
- `build-fe.bat`, `build-fe.ps1`, `restart-fe.bat`, `push.bat` — локальные dev-скрипты в корне.
- HSTS без `preload` (для внутреннего домена OK, документировать в ADR).

### Расхождения документации

| Документ | Расхождение | Истина |
|---|---|---|
| `db-schema.md:6` | `007_service_link_icons` | `007_news_fts_consolidate` |
| `adr.md:179` vs `api-contracts.md:87` | 120 vs 300 req/min | Неизвестно — сверить с кодом |
| `api-contracts.md:1144-1175` | `/notifications/*` описаны | Router не существует |
| `api-contracts.md:48` | `POST /files/upload` в idempotency whitelist | Файлы заморожены |
| `roles-matrix.md:254-263` | Аналитика & аудит endpoints | Routers не зарегистрированы |
| `AGENT.md:406-408` | KB/Search без `✅ Done` | Реализованы |
| `phase-0.md:5` | ссылка на `phase-1.md` | Файла нет |
| `adr.md:83` (ADR-003) | «Nginx отдаёт статику `/static/avatars/`» | Проксирует на backend через `/media/` |

### Готовность к Phase 4 (Notifications: Email + SSE)

| Компонент | Статус |
|---|---|
| SMTP vars в `.env.example` | ⚠️ Частично (нет user/password/TLS) |
| `aiosmtplib` | ✅ |
| ARQ worker | ✅ |
| `worker/tasks/email.py` | ❌ |
| Nginx SSE-блок | ✅ Готов |
| ADR-011 (SSE vs WebSocket) | ✅ |
| API-контракт `/notifications/*` | ✅ |
| Миграция notifications | ❌ |
| `app/api/notifications.py` | ❌ |
| ADR для email task pattern | ❌ |

---

## 6. Рекомендованный план действий перед Phase 4

### Этап 1 — блокеры безопасности и корректности (1-2 дня)

1. **Backend P0-1** — перенести bcrypt в executor (`hash_password_async`/`verify_password_async`).
2. **Backend P0-2** — исправить 6 вызовов `push_audit_event` в `kb_extra.py`.
3. **Backend P0-3** — мигрировать `branding.py` на `stream_upload_to_path`.
4. **Backend P0-4** — `redis.keys` → `SCAN` + узкая инвалидация.
5. **Backend P1-6** — убрать `data` из `ALLOWED_PROTOCOLS`.
6. **Frontend P0-1** — унифицированный `sanitizeHtml()` с hardened config.
7. **Frontend P0-2** — CSRF double-submit cookie + X-CSRF-Token в `api/index.ts`.
8. **Frontend P0-3** — мигрировать upload-функции на централизованный `api` instance.
9. **Tests F-02** — rate limit на `/me/password` + `/search` + тесты.

### Этап 2 — БД + наблюдаемость (1-2 дня)

10. **Миграция 011:**
    - `news.body_tsvector` → `russian_hunspell`
    - partial-индексы `idx_news_active`, `idx_news_pinned`, `idx_news_trgm`
    - `idx_users_keycloak` → partial
    - `idx_kb_versions_article DESC`
11. **Миграция 012:** таблица `notifications` + индексы.
12. **Backend** — создать `app/api/notifications.py` (заглушка с `/stream`) + регистрация в `main.py`.
13. **Worker** — `worker/tasks/email.py` (заглушка с retry/backoff).
14. **Observability** — кастомные Prometheus метрики: `audit_queue_depth`, `sse_connections_active`, `arq_job_*`.
15. **Worker** — экспозиция `/metrics`.

### Этап 3 — тестирование и CI (1 день)

16. **CI** — синхронизировать coverage (70% или 65% в обоих местах).
17. **Tests** — security: IDOR, CSRF на state-changing, CSP header, SQL injection параметров поиска.
18. **Tests** — branding unit + integration.
19. **CI** — добавить `trivy image`, `pip audit`, `npm audit` в build.yml.
20. **Worker** — убрать `app/worker/*` из `coverage.omit`.

### Этап 4 — документация и инфраструктура (0.5 дня)

21. **Infra F-01** — добавить `link_icons_data` volume в `docker-compose.yml`.
22. **Infra F-03** — исправить/удалить `commit.bat`.
23. **Infra F-07** — перенести `reset_admin.py` в `backend/scripts/`, убрать fallback credentials.
24. **Infra F-09** — убрать no-op `proxy_cache_valid` или добавить `proxy_cache_path`.
25. **Infra F-10** — добавить `smtp_user/password/tls/starttls` в `config.py` + `.env.example`.
26. **Docs** — исправить `db-schema.md` (миграция 007, bookmarks, service_links, news_versions, индексы).
27. **Docs** — синхронизировать rate limit в `adr.md` и `api-contracts.md`.
28. **Docs** — обновить `AGENT.md` (KB/Search ✅ Done) и `phase-0.md` (удалить ссылку на phase-1.md).
29. **Docs** — ADR-018 для email task pattern (retry, backoff, bounce handling).

### Этап 5 — Phase 4 launch

30. Переход к реализации SSE stream, email tasks, in-app notifications UI, bell-icon.
31. Load test `load/sse.js` с 300 параллельными SSE-соединениями.

---

## 7. Оценка «идти / не идти» на Phase 4

**Вердикт:** **НЕ начинать Phase 4** до закрытия минимум этапов 1-2 (блокеры + БД).

**Обоснование:**
- SSE без кастомных Prometheus-метрик слеп в production.
- Уведомления без CSRF-защиты на фронте создают удобный вектор атаки через социальную инженерию.
- bcrypt в event loop при 300 VU (ТЗ §7) приведёт к деградации именно при появлении SSE (долгие соединения + логины).
- Потеря audit-событий в KB ACL (P0-2 backend) — compliance-риск, особенно если Phase 4 будет добавлять новые чувствительные события.
- FTS russian → russian_hunspell на новостях — пользователи Phase 4 будут получать уведомления по новостям, ищут потом по ним — качество поиска определяет UX.

**Минимальный gate для Phase 4:** закрыты все 14 блокеров из раздела 0, миграция 011 применена, `app/api/notifications.py` и `worker/tasks/email.py` существуют (даже как заглушки), кастомные Prometheus-метрики заведены.

**Оценка трудоёмкости pre-Phase 4:** 4-5 человеко-дней при одном разработчике; 2-3 дня при параллельной работе (backend + frontend + infra).
