# Тестирование

> Последнее обновление: апрель 2026 — комплексная система покрытия (unit / integration / security / e2e / load). После Phase 3.5: KB ACL unit-тесты, скрипт миграции HTML→MD. После Step 6.8: Branding System.

---

## Стратегия

Многоуровневая пирамида:

```
                  ┌────────────────────────┐
                  │   Load (k6)            │  300 VU, p95 < 2s, search < 1s
                  └────────────────────────┘
                ┌──────────────────────────────┐
                │   E2E (Playwright)           │  ключевые сценарии (≥90%)
                └──────────────────────────────┘
              ┌──────────────────────────────────┐
              │   Security (CSRF/XSS/headers)    │  обязательные перед релизом
              └──────────────────────────────────┘
            ┌────────────────────────────────────────┐
            │   Integration (real PG + Redis)        │  миграции, FTS, rate-limit
            └────────────────────────────────────────┘
          ┌────────────────────────────────────────────┐
          │   Unit (pytest, vitest)                    │  чистая бизнес-логика
          └────────────────────────────────────────────┘
```

Базовое правило: **тесты пишутся одновременно с кодом**. Pull-request без тестов не проходит ревью.

---

## Структура

```
backend/tests/
├── conftest.py                  ← env vars, фабрики (User/News/KbArticle), AsyncClient, маркеры
├── unit/                        ← быстрые, без Docker (~3–10s)
│   ├── test_config.py
│   ├── test_health.py
│   ├── test_audit_partitions.py
│   ├── test_security.py
│   ├── test_session.py
│   ├── test_news_service.py
│   ├── test_links_bookmarks.py
│   ├── test_local_auth.py
│   ├── test_logging.py
│   ├── test_kb_acl.py           ← ACL алгоритм, Redis-кэш, filter_accessible
│   └── test_kb_*.py             ← slugify, optimistic locking, версионирование, etc.
├── integration/                 ← real PostgreSQL + Redis (~30–90s)
│   ├── conftest.py              ← real_db_session / real_user / real_editor / real_admin
│   ├── test_migrations.py
│   ├── test_news_db.py
│   ├── test_session_redis.py
│   ├── test_kb_search.py
│   ├── test_local_auth_db.py
│   ├── test_rate_limit.py
│   └── test_audit_partitions_real.py
└── security/                    ← CSRF / XSS / headers / auth-required / passwords
    ├── conftest.py              ← авто-маркер security
    ├── test_security_headers.py
    ├── test_csrf.py
    ├── test_auth_required.py
    ├── test_xss_sanitization.py
    └── test_password_security.py

frontend/
├── tests/
│   ├── unit/                    ← Vitest (~2s)
│   │   ├── url.spec.ts
│   │   ├── sanitize.spec.ts
│   │   ├── router-guards.spec.ts
│   │   └── rich-editor.spec.ts
│   └── e2e/                     ← Playwright (~30–120s)
│       ├── smoke.spec.ts
│       ├── local-login.spec.ts
│       └── security-headers.spec.ts
└── playwright.config.ts         ← chromium + mobile проекты, junit + html report

load/                            ← k6
├── smoke.js                     ← 1 VU, для CI
├── baseline.js                  ← 50 VU
├── search.js                    ← прицельный поиск
└── portal-load.js               ← 300 VU per ТЗ §7
```

---

## Запуск

### Backend — все тесты

```bash
cd backend
pip install -e ".[dev]"
pytest                                 # unit + integration + security
pytest tests/unit                      # только unit (без Docker)
pytest tests/security                  # только security (на in-memory app)
INTEGRATION_DB=true INTEGRATION_REDIS=true pytest tests/integration
pytest -m "not integration"            # unit + security без integration
pytest -n auto                         # параллельно через pytest-xdist
pytest --cov=app --cov-report=html     # покрытие → htmlcov/index.html
```

### Frontend — unit

```bash
cd frontend
npm run test:unit
npm run test:unit:watch
```

### Frontend — E2E

Требует запущенный стек (`docker compose up`) или `npm run dev`.

```bash
cd frontend
npx playwright install --with-deps chromium    # один раз
npm run test:e2e                                # все спеки
npx playwright test tests/e2e/smoke.spec.ts     # один файл
E2E_BASE_URL=https://portal.staging npx playwright test --project=chromium
```

Чтобы прогнать локальный логин:

```bash
E2E_ADMIN_EMAIL=admin@local E2E_ADMIN_PASSWORD=Pass123! npm run test:e2e
```

### Load (k6)

```bash
# 1 VU smoke
k6 run load/smoke.js

# Прицельный поиск
BASE_URL=https://portal.staging k6 run load/search.js

# Полная нагрузка из ТЗ §7
BASE_URL=https://portal.staging \
  ADMIN_EMAIL=admin@local \
  ADMIN_PASSWORD=Pass123! \
  k6 run load/portal-load.js
```

---

## Маркеры (pytest)

| Маркер | Описание |
|--------|---------|
| `integration` | Требует реальный PostgreSQL + Redis (`INTEGRATION_DB=true` / `INTEGRATION_REDIS=true`) |
| `security` | Auth-required, CSRF, XSS, headers, passwords |
| `slow` | > 1s — можно фильтровать локально через `pytest -m "not slow"` |

`pytest.ini` включает `--strict-markers` — неизвестный маркер ломает прогон.

---

## Фикстуры (`conftest.py`)

| Фикстура | Скоуп | Назначение |
|----------|-------|------------|
| `event_loop` | session | Один loop на сессию (нужен для async фикстур со scope=session) |
| `_engine` | session | AsyncEngine, `pool_pre_ping=True` (only integration) |
| `db_session` | function | SAVEPOINT-rollback вокруг каждого теста (быстрый изолированный тест) |
| `redis_client` | function | FLUSHDB перед/после, `decode_responses=True` |
| `app` | function | Reload `app.main` с пустым ADMIN_EMAIL (без bootstrap) |
| `client` | function | `AsyncClient` + ASGITransport, Origin=`http://test` |
| `authed_client_factory` | function | Фабрика клиентов с `dependency_overrides[get_current_user]` |
| `user_factory` / `news_factory` / `kb_article_factory` | function | In-memory `SimpleNamespace` для unit-тестов |
| `real_db_session` / `real_user` / `real_editor` / `real_admin` | function | TRUNCATE-cleanup для integration-сценариев |

---

## Покрытие

### Backend Unit (~100+ тестов)

| Файл | Что покрывается |
|------|-----------------|
| `test_config.py` | Pydantic Settings, валидация SECRET_KEY, MAX_UPLOAD_SIZE_MB, asyncpg-driver |
| `test_health.py` | `/health` всегда 200, `/ready` корректно реагирует на падение PG/Redis |
| `test_audit_partitions.py` | Имена партиций, создание/дропание, retention=12мес |
| `test_security.py` | JWT parse, claims-mapping, cookie helpers |
| `test_session.py` | Redis-сессии, rotation, TTL, SLO |
| `test_news_service.py` | Таргетинг, версии, soft-delete, отложенная публикация |
| `test_links_bookmarks.py` | URL-валидация, `hidden_link_ids`, reorder, SSO `id_token_hint` |
| `test_local_auth.py` | bcrypt, bootstrap-admin idempotency, account-linking |
| `test_logging.py` | Redaction секретов/PII, truncation, contextvars |
| `test_kb_acl.py` | ACL алгоритм: `_perm_gte`, `resolve_section_permission`, `resolve_article_permission`, `require_*_permission`, `filter_accessible_*`, `invalidate_*_cache` — 37 тестов |
| `test_kb_*.py` | Slugify, optimistic locking (409), soft-delete, версионирование, view-dedup, комментарии, feedback, поиск, дерево разделов, diff, YAML frontmatter, ZIP-структура |
| `test_files_acl.py` | ACL файлов: `perm_gte` все комбинации, `_subject_ids_for_user` (id + keycloak_id + groups), `resolve_folder_permission` (admin/created_by/cache-hit/cache-none/direct/inherit/no-access), `require_folder_permission` (ok + 403), `filter_accessible_folders` (admin/user), `invalidate_folder_cache` — 20+ тестов |
| `test_nextcloud_service.py` | WebDAV-клиент: `_webdav_url` (root/subpath/spaces), `_parse_propfind` (файлы/skip-root), `health_check` (200→True/exception→False), `list_folder`/`create_folder`/`delete`/`move`/`upload_stream` happy path + error cases — 15+ тестов |

### Backend Integration (real PG + Redis)

Все integration-тесты используют SAVEPOINT-стратегию изоляции (`real_db_session`): каждый тест выполняется внутри SAVEPOINT, откатываемого в конце — данные не остаются в БД, нет TRUNCATE, нет блокировок.

| Файл | Что покрывается |
|------|-----------------|
| `test_migrations.py` | Alembic upgrade/downgrade idempotency |
| `test_news_db.py` | INSERT/UPDATE/SELECT с реальной БД, FTS-поля, `target_departments` |
| `test_session_redis.py` | save/get/refresh/delete, TTL, replace-on-update |
| `test_kb_search.py` | tsvector, pg_trgm fallback, ILIKE accent-insensitive |
| `test_kb_acl_integration.py` | viewer/editor/manager изоляция (14 тестов); `inherit_permissions=false`; файлы → 403; локальные пользователи в ACL |
| `test_kb_media_integration.py` | media upload → URL содержит article_id; X-Accel-Redirect при отдаче; vault ZIP import → статьи создаются (8 тестов); CSRF double-submit |
| `test_local_auth_db.py` | bcrypt-roundtrip через `users.password_hash` |
| `test_rate_limit.py` | fastapi-limiter с реальным Redis: 5 попыток / 15 мин |
| `test_audit_partitions_real.py` | partitioned table, начальные партиции, INSERT routing |

### Backend Security

| Файл | Что покрывается |
|------|-----------------|
| `test_security_headers.py` | X-Content-Type-Options, X-Frame-Options, Permissions-Policy, X-Request-Id echo / length-limit, HSTS только в prod |
| `test_csrf.py` | GET без Origin = ok, POST без Origin = 403, неверный Origin = 403, /auth/callback exempt |
| `test_auth_required.py` | 9 protected endpoints без сессии = 401, admin-only для admin-эндпоинтов |
| `test_xss_sanitization.py` | `<script>`, `<iframe>`, `<svg onload>`, `javascript:`, `<style>`, `<meta>` strip; data:image/png whitelisted; safe HTML preserved |
| `test_password_security.py` | bcrypt roundtrip, длинный пароль (>72 байт через SHA256-prehash), unicode, salt uniqueness |

### Frontend Unit (Vitest)

| Файл | Что покрывается |
|------|-----------------|
| `url.spec.ts` | `isSafeHttpUrl` отвергает `javascript:`/`data:`/`file:`/`vbscript:` |
| `sanitize.spec.ts` | DOMPurify XSS-щит для v-html |
| `router-guards.spec.ts` | `isLocalUser`, `redirectToLogin` с правильным redirect-параметром |
| `rich-editor.spec.ts` | Smoke-импорт компонента (TipTap mocked) |

### Frontend E2E (Playwright)

| Файл | Сценарий |
|------|---------|
| `smoke.spec.ts` | `/login` рендерится, security-headers пришли |
| `local-login.spec.ts` | Bootstrap admin → логин → главная; неверный пароль → остаётся на /login |
| `security-headers.spec.ts` | Браузер видит ожидаемые заголовки от nginx/backend |

### Load (k6)

| Сценарий | Пороги |
|----------|--------|
| `smoke.js` | 1 VU, 5 итераций; p95 < 1s, checks > 99% |
| `baseline.js` | ramp 50 VU; p95 < 2s |
| `search.js` | 50 VU/1мин на `/search?q=...`; p95 < 1s, p99 < 1.5s — ТЗ §7 |
| `portal-load.js` | ramp 0→100→300 VU; `http_req_duration p95 < 2000ms`, `search_latency_ms p95 < 1000ms` — ТЗ §7 |

---

## CI (GitHub Actions)

| Job | Триггер | Что делает |
|-----|---------|-----------|
| `backend-lint` | push/PR | ruff check + format + mypy |
| `backend-unit` | push/PR | unit + security, coverage gate `--cov-fail-under=70` (синхронизировано с `pyproject.toml`) |
| `backend-integration` | push/PR | services postgres+redis, init.sql, alembic upgrade, integration-тесты |
| `frontend-lint` | push/PR | ESLint + tsc + i18n keys |
| `frontend-unit` | push/PR | vitest |
| `frontend-e2e` | PR only | Playwright smoke (`tests/e2e/smoke.spec.ts`) — артефакт `playwright-report` |
| `load-smoke` | PR only | `k6 inspect` — статическая валидация скриптов |

Покрытие выгружается в Codecov с флагом `backend-unit`.

---

## Критерии приёмки (ТЗ §7)

- ✅ Unit-тесты пишутся одновременно с кодом
- ✅ Integration: реальный PG + Redis, alembic upgrade в CI
- ✅ Security: CSRF / XSS / headers / passwords / auth-required
- ⏳ E2E ≥ 90% ключевых путей — расширяется по мере добавления модулей
- ✅ Load: k6 со сценариями smoke / baseline / search / 300 VU
- ⏳ OWASP ZAP — ручной прогон в Phase 11

---

## Покрытие: Branding System (Step 6.8)

| Слой | Что покрывается |
|------|----------------|
| **Unit** | `_load_settings()` / `_save_settings()` round-trip; `_find_file` / `_delete_files` с mock-FS; `BrandingSettings` валидация (accent_color, banner_type); `isBannerActive` computed с `banner_expires_at` в прошлом/будущем |
| **Integration** | `GET /branding/settings` — возвращает defaults без файла; `PUT /admin/branding/settings` — forbidden для reader/editor; logo/favicon/login-bg upload → GET round-trip; размер > 2 МБ → 413 |
| **E2E** | Smoke: страница входа рендерится с кастомным portal_name; баннер отображается и закрывается кнопкой ✕; admin загружает логотип → отображается в AppLayout |
| **Security** | `PUT /admin/branding/settings` без cookie → 401; reader cookie → 403; XSS в `banner_text` — DOMPurify на фронте |

> ℹ️ Unit и integration тесты для branding ещё не написаны — планируются в Phase 11 финальное тестирование. GET-эндпоинты проверяются E2E smoke.

---

## Покрытие: Files / Nextcloud Integration (Phase 5)

| Слой | Что покрывается |
|------|----------------|
| **Unit** | `test_files_acl.py` — алгоритм ACL (20+ тестов); `test_nextcloud_service.py` — WebDAV-клиент (15+ тестов) |
| **Integration** | Не реализованы; требуют мок-Nextcloud или реальный экземпляр |
| **E2E** | Не реализованы; требуют реальный Nextcloud с `portal-svc` App Password |
| **Security** | `GET /files/tree` без cookie → 401; reader без прав на папку → 403; модуль выключен → 503 |

> ℹ️ Интеграционные и E2E тесты для файлового модуля запланированы на Phase 11 (финальное тестирование). Для запуска потребуется `NC_SERVICE_APP_PASSWORD` и реальный Nextcloud.

---

## Известные ограничения

1. **`fakeredis`** используется в unit-тестах rate-limit, реальный Redis — в integration.
2. **`load/portal-load.js`** не запускается в CI (требует staging-инстанс) — только `k6 inspect`.
3. **Playwright E2E** в CI ограничен `smoke.spec.ts` (без поднятия backend); полные сценарии — против staging.
4. **Coverage gate** = 70% (актуально — Phase 5 реализована).
5. **KB ACL integration-тесты** ✅ реализованы (`test_kb_acl_integration.py`, 14 тестов); запускаются с флагом `INTEGRATION_DB=true`. Особенность: локальные пользователи используют `str(user.id)` как `subject_id` (не `keycloak_id`).
6. **KB Media integration-тесты** ✅ реализованы (`test_kb_media_integration.py`, 8 тестов); все POST требуют CSRF double-submit (`XSRF-TOKEN` cookie = `x-xsrf-token` header) и `get_db` override для видимости uncommitted данных.
7. **Скрипт миграции HTML→MD** (`backend/scripts/migrate_kb_html_to_md.py`) — не входит в pytest; запускается вручную через `python scripts/migrate_kb_html_to_md.py --dry-run` перед production-деплоем Phase 3.5.
8. **Branding unit/integration тесты** — не реализованы; покрываются E2E smoke в Phase 11.
9. **Phase 5 (Nextcloud) integration/E2E тесты** — не реализованы; требуют мок-Nextcloud или реальный экземпляр с `portal-svc` App Password.
10. **Phase 4.5 (Photos) integration/E2E тесты** — не реализованы; требуют реального тома `/data/photos` и Pillow.
11. **INTEGRATION_DB default-стратегия**: `real_db_session` использует SAVEPOINT + ROLLBACK (не TRUNCATE); `session.commit()` в тестах запрещён — переносит изменения за границу SAVEPOINT.
