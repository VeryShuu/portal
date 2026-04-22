# Тестирование

> Последнее обновление: апрель 2026 — комплексная система покрытия (unit / integration / security / e2e / load).

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
│   └── test_kb_*.py
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
| `test_kb_*.py` | Slugify, optimistic locking (409), permissions, soft-delete, версионирование, view-dedup |

### Backend Integration (real PG + Redis)

| Файл | Что покрывается |
|------|-----------------|
| `test_migrations.py` | Alembic upgrade/downgrade idempotency |
| `test_news_db.py` | INSERT/UPDATE/SELECT с реальной БД, FTS-поля, `target_departments` |
| `test_session_redis.py` | save/get/refresh/delete, TTL, replace-on-update |
| `test_kb_search.py` | tsvector, pg_trgm fallback, ILIKE accent-insensitive |
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
| `backend-unit` | push/PR | unit + security, coverage gate `--cov-fail-under=60` |
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

## Известные ограничения

1. **`fakeredis`** используется в unit-тестах rate-limit, реальный Redis — в integration.
2. **`load/portal-load.js`** не запускается в CI (требует staging-инстанс) — только `k6 inspect`.
3. **Playwright E2E** в CI ограничен `smoke.spec.ts` (без поднятия backend); полные сценарии — против staging.
4. **Coverage gate** = 60% (поднимется до 70% после Phase 5/6).
