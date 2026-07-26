# Тестирование

> **Когда читать:** стратегия тестов, команды запуска, CI, покрытие.
> **Ключевой код:** `backend/tests/`, `frontend/tests/unit/**/*.spec.ts` (Vitest), Playwright e2e-спеки в `frontend/tests/e2e/`.
> **Generated-компаньон:** `tests.generated.md` (список тестов; не править руками).
> **Активный план доработки:** `wip/test-coverage-hardening.md`.
> **ADR:** 037.

> Последнее обновление: июль 2026 — итерация 18 (test-audit remediation: устранены фейк-тесты admin-tabs-smoke + property-based tests через Hypothesis + nightly-marker для jq/envsubst-тестов). Замеры 2026-07-26: Backend — **3814** unit + **77** security тестов (0 failures, 5 skipped по `@pytest.mark.nightly`-маркеру, 14 warnings), покрытие **81.32%** по merged unit+security (гейт 75%). Frontend — **2130** Vitest-тест в **216** spec-файлах; пороги зафиксированы: `lines 65 / functions 52 / branches 59 / statements 66`. Playwright e2e — 11 спеков (включая `@a11y` пилот через `@axe-core/playwright`), проекты chromium/firefox/webkit/mobile. Lint/типизация: `ruff` 0 errors, `mypy .` 0 issues, `i18n:check` OK. Итерации 16-17 — см. git-историю.

> **Итерация 18 (test-audit remediation):** по результатам аудита системы тестирования устранены:
> - **7 фейк-тестов** в `admin-tabs-smoke.spec.ts` (`catch { expect(true).toBe(true) }` проглатывал любую ошибку mount'а → тесты были всегда «зелёными», но ничего не проверяли). Честный mount теперь работает; вскрыт дефект мокинга `@vicons/ionicons5` (Proxy ломался на named-export validation) — заменён на явный список иконок.
> - **Property-based tests (Hypothesis)** для `meetings/bookings_service._compute_diff` — 5 инвариантов (conservation, disjoint, reflexive, symmetric direction-swap, non_participant_changed passthrough) на 280+ примерах каждый. Зависимость `hypothesis>=6.100.0` добавлена в dev-extras.
> - **`kb_markdown.py` покрытие 36% → 64%** через async-mock тесты `get_section_path` / `get_or_create_section_by_path` / `zip_section` (ранее нетестируемые async DB-функции).
> - **`@pytest.mark.nightly` для nginx render-config.sh тестов** (требуют jq/envsubst/POSIX sh) — auto-skip через хук `pytest_collection_modifyitems` в `conftest.py`; skip-причина стала самодокументируемой («nightly marker: set NIGHTLY=true» вместо «jq not available»).
> - Регенерирован `docs/tests.generated.md` (+20 тестов).

> В итерации 17 найден и исправлен production-баг: `app/core/limiter.py` ловил несуществующее исключение `pyredis.exceptions.NoScriptException` (правильное имя `NoScriptError`) → при FLUSH Redis'а лимитер падал вместо перезагрузки Lua-скрипта. Покрыто регрессионным тестом `test_patched_call_reloads_lua_script_on_noscripterror`. См. обновлённый ADR-043 (грабли №4, №5).

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
│   ├── test_audit.py
│   ├── test_security.py
│   ├── test_session.py
│   ├── test_news_service.py
│   ├── test_news_categories.py
│   ├── test_links_bookmarks.py
│   ├── test_logging.py
│   ├── test_branding.py         ← _load_settings/_save_settings, API-эндпоинты, email-настройки
│   ├── test_analytics.py
│   ├── test_admin_users.py
│   ├── test_modules.py
│   ├── test_notifications.py
│   ├── test_search.py
│   ├── test_system_settings.py
│   ├── test_uploads.py
│   ├── test_worker_tasks.py     ← audit + metrics worker tasks
│   ├── test_files_acl.py
│   ├── test_files_acl_persistence.py
│   ├── test_nextcloud_service.py
│   ├── test_nextcloud.py
│   ├── test_nc_federation.py
│   ├── test_keycloak_service.py
│   ├── test_photos_acl.py
│   ├── test_photos_storage.py
│   ├── test_core_utils.py
│   ├── test_kb_acl.py           ← ACL алгоритм, Redis-кэш, filter_accessible, batch-resolve, visibility
│   ├── test_kb_service.py       ← slugify, record_article_view, _resolve_tags, set_article_tags
│   ├── test_kb_markdown.py      ← slugify, optimistic locking, версионирование, etc.
│   ├── test_kb_articles.py      ← API роуты kb/articles: list/create/get/update/delete/restore
│   ├── test_kb_versions.py      ← API роуты kb/versions: list/restore/diff
│   ├── test_kb_sections.py      ← API роуты kb/sections: tree/create/update/delete
│   ├── test_kb_export_import.py ← export md/zip/vault/pdf; import md+vault
│   ├── test_tls_status.py       ← cert/key parsing, notAfter+subject, OSError/TimeoutError
│   ├── test_webdav.py           ← _webdav_url/_resolve_url/_parse_propfind, health/list/create/delete/move
│   ├── test_collabora.py        ← _try_richdocuments_ocs, _try_direct_editing, get_collabora_url[_via_federation]
│   ├── test_auth_routes.py      ← config/me/logout/local-login/refresh маршруты
│   ├── test_audit_routes.py     ← _build_filters, GET /audit /event-types /queue/depth /export.csv
│   ├── test_news_routes.py      ← list/get/create/update/delete/restore/purge/versions/trash
│   ├── test_news_export.py      ← _file_to_data_uri, _inline_body_images, export/html/md/pdf
│   ├── test_links_api.py        ← list/get/create/update/delete/reorder/sso_redirect/icon
│   ├── test_bookmarks.py        ← favicon proxy, CRUD, reorder; расширяет test_bookmarks_favicon.py
│   ├── test_files_upload.py     ← upload, open_in_collabora, idempotency, NC-ошибки
│   ├── test_files_folders.py    ← get tree/folder, create/update/delete с NC
│   ├── test_files_ops.py        ← _bulk_inflight_key, DELETE /file, bulk-delete/move
│   ├── test_feedback_service.py ← feedback_service + feedback_repo + _common mapper-функции
│   ├── test_keycloak_admin.py   ← _is_unsafe_ip, _validate_keycloak_url, settings/test/sync маршруты
│   ├── test_users_me_routes.py  ← GET/PATCH /me, POST avatar, PATCH password
│   ├── test_auth_callback_errors.py  ← OIDC callback ошибки → редирект /auth/error
│   ├── test_bookmarks_favicon.py     ← favicon-прокси, cache key, TTL
│   ├── test_concurrent_tasks.py      ← имитация multi-worker конкурентности
│   ├── test_files_bulk.py            ← bulk-delete / bulk-move файлов
│   ├── test_hydrate_custom_metrics.py ← middleware _hydrate_custom_metrics
│   ├── test_limiter.py               ← fastapi-limiter unit
│   ├── test_photos_permissions.py    ← права доступа к фото
│   ├── test_photos_sharing.py        ← share-токен, TTL, revoke
│   ├── test_worker_photos_tasks.py   ← ARQ: process_photo_upload, build_zip_job, import_scan_job, empty_photo_trash
│   ├── test_redirects.py             ← safe_redirect, защита от open-redirect
│   ├── test_user_attribute_mappings.py ← Pydantic-схемы маппингов атрибутов
│   └── test_users_public.py          ← публичный API пользователей
├── integration/                 ← real PostgreSQL + Redis (~30–90s)
│   ├── conftest.py              ← real_db_session / real_user / real_editor / real_admin
│   ├── test_api_smoke.py        ← smoke через ASGITransport + моки (без реального PG)
│   ├── test_migrations.py
│   ├── test_news_db.py
│   ├── test_news_api.py
│   ├── test_session_redis.py
│   ├── test_kb_search.py
│   ├── test_kb_acl_integration.py
│   ├── test_kb_media_integration.py
│   ├── test_local_auth.py
│   ├── test_local_auth_db.py
│   ├── test_account_linking.py
│   ├── test_admin_users_db.py
│   ├── test_rate_limit.py
│   ├── test_audit_partitions_real.py
│   ├── test_analytics_db.py          ← аналитика через реальную БД
│   ├── test_bookmarks_race.py        ← race condition при создании закладок, MAX_BOOKMARKS_PER_USER
│   ├── test_files_bulk.py            ← bulk-операции файлов через реальный стек
│   └── test_rate_limit_endpoints.py  ← rate-limit для не-auth эндпоинтов
└── security/                    ← CSRF / XSS / headers / auth-required / passwords
    ├── conftest.py              ← авто-маркер security
    ├── test_security_headers.py
    ├── test_csrf.py
    ├── test_auth_required.py
    ├── test_session_fixation.py
    ├── test_xss_sanitization.py
    └── test_password_security.py

frontend/
├── tests/
│   ├── unit/                    ← Vitest (~4s)
│   │   ├── url.spec.ts
│   │   ├── sanitize.spec.ts
│   │   ├── router-guards.spec.ts
│   │   ├── rich-editor.spec.ts
│   │   ├── admin-page.spec.ts           ← lazy-loaded tab-компоненты AdminPage (import-only)
│   │   ├── api-types.spec.ts            ← type-safety API-клиентов
│   │   ├── auth.spec.ts                 ← useAuthStore: роли, loadUser, ошибки
│   │   ├── branding-store.spec.ts       ← useBrandingStore: isBannerActive, CSS vars
│   │   ├── email-tab.spec.ts            ← email-настройки в branding
│   │   ├── links-store.spec.ts          ← useLinksStore: CRUD, reorder
│   │   ├── modules-store.spec.ts        ← useModulesStore: enabled/disabled
│   │   ├── notifications-store.spec.ts  ← SSE, read/readAll/remove
│   │   ├── photos-store.spec.ts         ← usePhotosStore: loadRecent, ошибки
│   │   ├── photo-decomposition.spec.ts  ← usePhotoUpload composable
│   │   ├── theme-store.spec.ts          ← useThemeStore: dark/light toggle
│   │   ├── auth-store-sso.spec.ts       ← loop-protection и SSO state в useAuthStore
│   │   ├── department-colleagues.spec.ts ← DepartmentColleagues компонент
│   │   ├── extract-dropped-files.spec.ts ← extractDroppedFiles util (drag & drop)
│   │   ├── files-store.spec.ts          ← useFilesStore: папки, дерево, CRUD
│   │   ├── user-profile-view.spec.ts    ← UserProfileView: smoke + fetch коллег
│   │   ├── notifications-api.spec.ts    ← src/api/notifications.ts: все 5 функций
│   │   ├── auth-api.spec.ts             ← src/api/auth.ts: fetchMe/refresh/login/changePassword/URL-builders
│   │   ├── feedback-api.spec.ts         ← src/api/feedback.ts: CRUD, attachments, лимиты
│   │   ├── links-api.spec.ts            ← src/api/links.ts: links+bookmarks CRUD, SSO, icon upload
│   │   ├── files-api.spec.ts            ← src/api/files.ts: folders CRUD, permissions, bulk, upload, utils
│   │   ├── news-api.spec.ts             ← src/api/news.ts: CRUD, cover, gallery, trash, AbortSignal
│   │   ├── kb-api.spec.ts               ← src/api/kb.ts: sections/articles/versions/comments, export/import
│   │   ├── photos-api.spec.ts           ← src/api/photos.ts: folders, photos CRUD, tags, sharing, trash
│   │   ├── use-app-menu.spec.ts         ← useAppMenu: activeKey, menu visibility, handleMenuSelect
│   │   ├── router-guards-extended.spec.ts ← requireAuth/requireRole/requireModule guards
│   │   ├── app-layout-smoke.spec.ts     ← AppHeader/AppSider/HeaderUserMenu/AppLayout smoke
│   │   ├── global-search-smoke.spec.ts  ← GlobalSearch: show/hide/input/Esc/results
│   │   ├── files-table-smoke.spec.ts    ← FilesTable: renders/items/row-click/selectedKeys
│   │   ├── files-toolbar-smoke.spec.ts  ← FilesToolbar: folder name/permission tags/upload button
│   │   ├── files-bulk-permissions-smoke.spec.ts ← FilesPermissionsModal + FilesBulkBar
│   │   ├── kb-components-smoke.spec.ts  ← KbSectionTree/KbCommentsTab/KbVersionsTab/KbPermissionsModal
│   │   ├── photos-components-smoke.spec.ts ← PhotosGrid/LightboxModal/PhotosTrashView
│   │   ├── pages-smoke.spec.ts          ← mount smoke для 21 страницы src/pages/
│   │   ├── components-smoke-extra*.spec.ts ← SettingsPage + прочие компоненты (постепенно растаскивается, см. ниже)
│   │   ├── not-found-page.spec.ts       ← NotFoundPage.vue smoke (расселено из extra5)
│   │   ├── trash-page.spec.ts           ← TrashPage.vue smoke (расселено из extra5)
│   │   ├── link-visuals.spec.ts         ← useLinkVisuals: colorFor/faviconFor/shortUrl/onIconError
│   │   └── utils-coverage.spec.ts       ← triggerDownload с опциями и без
│   └── e2e/                     ← Playwright (~30–120s)
│       ├── smoke.spec.ts
│       ├── auth.spec.ts
│       ├── local-login.spec.ts
│       ├── security-headers.spec.ts
│       ├── kb-acl.spec.ts            ← ivanov/petrov/sidorov ACL-сценарии
│       ├── kb-media.spec.ts          ← media upload, vault ZIP import
│       ├── photos.spec.ts            ← фото-галерея, загрузка
│       ├── admin-login.spec.ts       ← локальный вход через /auth/local
│       ├── auth-sso-redirect.spec.ts ← auto-SSO redirect с page.route-стабом
│       ├── files-bulk.spec.ts        ← bulk-операции файлов E2E
│       └── a11y.spec.ts              ← @a11y axe-core baseline (login + root redirect, WCAG2A/AA critical+serious)
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
./scripts/run_pytest_unit.sh           # запуск unit-тестов
./scripts/run_pytest_integration.sh    # запуск integration-тестов
pytest tests/unit                      # только unit (без Docker)
pytest tests/security                  # только security (на in-memory app)
INTEGRATION_DB=true INTEGRATION_REDIS=true pytest tests/integration
pytest -m "not integration"            # unit + security без integration
pytest -m unit_with_db                 # REVIEW-2.1 кандидаты с реальной БД
pytest -n auto                         # параллельно через pytest-xdist
pytest --cov=app --cov-report=html     # покрытие → htmlcov/index.html
```

#### Запуск integration-тестов в dev-стеке (Docker)

`setup.sh` → пункт «Разработка» поднимает `docker-compose.yml` + `docker-compose.dev.yml`: backend пересобирается из стадии `test` Dockerfile, поэтому внутри контейнера уже доступны `pytest`, `ruff`, `mypy` и каталог `tests/`. PostgreSQL (5432) и Redis (6379) опубликованы на хост — `INTEGRATION_DB=true` / `INTEGRATION_REDIS=true` работают как изнутри контейнера, так и с хоста (если на хосте установлены `python` + зависимости).

```bash
# Из репозитория:
docker compose exec backend /app/scripts/run_pytest_unit.sh           # unit
docker compose exec backend /app/scripts/run_pytest_integration.sh    # unit + security + integration (INTEGRATION_DB=true INTEGRATION_REDIS=true)
docker compose exec backend pytest tests/integration/test_news_db.py  # точечный прогон
```

Хелперы `./backend/scripts/run_pytest_unit.sh` и `./backend/scripts/run_pytest_integration.sh` гарантируют единообразие флагов (`--no-cov -p no:cacheprovider`) между локалкой и CI.

### Frontend — unit

```bash
cd frontend
npm run test:unit
npm run test:unit:watch
```

### Frontend — E2E

`./frontend/playwright.config.ts` поднимает webServer через `E2E_MODE`:
- `E2E_MODE=preview` (по умолчанию в CI) — `npm run build && npx vite preview --port 5173 --strictPort` (продовая сборка, ближе к staging).
- `E2E_MODE=dev` (по умолчанию локально) — `npm run dev` (HMR, быстрее перезапуск).
- `E2E_NO_WEBSERVER=1` — не поднимать webServer (если стек уже запущен через `docker compose up`).

Проекты: `chromium` (PR + локально), `firefox` / `webkit` (без `*.mobile.spec.ts`, локально и в nightly), `mobile` (iPhone 13, только `*.mobile.spec.ts`). Конфиг: `fullyParallel: true`, `workers: 4` в CI; спеки `kb-acl`, `kb-media`, `photos` помечены `test.describe.configure({ mode: 'serial' })`, потому что используют shared state между тестами внутри describe.

E2E-фикстуры:

- `./frontend/tests/e2e/fixtures/run-id.ts` — `E2E_RUN_ID`, `runScoped(name)`, `runScopedEmail(local)` для уникальных префиксов сущностей и e-mail; предотвращает конфликты по UNIQUE-ключам при повторных/параллельных прогонах.
- `./frontend/tests/e2e/fixtures/api.ts` — `localLogin(page, email, password)`, `apiRequest(page, method, path, body?)` (через `page.evaluate` + CSRF double-submit) и `CleanupRegistry` с методами `trackUser/trackSection/trackArticle/trackPhotoFolder` + `flush()` (LIFO, best-effort) — вызывается в `afterAll`, чтобы не оставлять мусор в БД.

```bash
cd frontend
npx playwright install --with-deps chromium    # один раз (или 'firefox webkit')
npm run test:e2e                                # все спеки (E2E_MODE=dev локально)
E2E_MODE=preview npm run test:e2e               # против продовой сборки
npx playwright test tests/e2e/smoke.spec.ts     # один файл
E2E_BASE_URL=https://portal.staging E2E_NO_WEBSERVER=1 npx playwright test --project=chromium
npx playwright test --project=firefox           # дополнительная браузерная матрица
```

Чтобы прогнать локальный логин:

```bash
E2E_ADMIN_EMAIL=admin@local E2E_ADMIN_PASSWORD=Pass123! npm run test:e2e
```

### Accessibility (axe-core) — пилот `@a11y`

`./frontend/tests/e2e/a11y.spec.ts` использует `@axe-core/playwright` и проверяет страницы login + root redirect по тегам `wcag2a` / `wcag2aa`. Падает только на violations с `impact in {critical, serious}` — в выводе печатается `id`, `help` и количество затронутых узлов, чтобы можно было быстро локализовать проблему. Помечен тегом `@a11y` для grep-фильтрации:

```bash
npx playwright test --grep @a11y               # только a11y-сценарии
npx playwright test --grep-invert @a11y        # всё, кроме a11y
```

Новые a11y-чек-листы добавляются файлами рядом (`<page>-a11y.spec.ts`) или дополнительными `test('@a11y …')` блоками — chromium-проект подхватывает их автоматически.

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
| `unit_with_db` | Unit-стиль (лежит в `tests/unit/`), но требует реальную БД (REVIEW-2.1 migration path). Через корневой `tests/conftest.py` доступны фикстуры `real_db_session`/`real_user`/`real_editor`/`real_admin` из `tests/db_fixtures.py`; они сами вызывают `pytest.skip` без `INTEGRATION_DB=true`, так что обычный unit-прогон остаётся быстрым. Используется для постепенного перевода mock-heavy тестов (`test_kb_*`, `test_news_*`, `test_files_*`, `test_photos_*`) на честную БД |

`pytest.ini` включает `--strict-markers` — неизвестный маркер ломает прогон.

---

## Фикстуры (`conftest.py`)

| Фикстура | Скоуп | Назначение |
|----------|-------|------------|
| _(event loop)_ | session | Управляется декларативно через `asyncio_default_fixture_loop_scope = "session"` в `pyproject.toml` (pytest-asyncio ≥ 0.23); кастомный `event_loop` fixture удалён (deprecated в 0.24+) |
| `_engine` | session | AsyncEngine, `pool_pre_ping=True` (only integration) |
| `db_session` | function | SAVEPOINT-rollback вокруг каждого теста (быстрый изолированный тест) |
| `redis_client` | function | FLUSHDB перед/после, `decode_responses=True` |
| `app` | function | Reload `app.main` с пустым ADMIN_EMAIL (без bootstrap) |
| `client` | function | `AsyncClient` + ASGITransport, Origin=`http://test` |
| `authed_client_factory` | function | Фабрика клиентов с `dependency_overrides[get_current_user]` |
| `user_factory` / `news_factory` / `kb_article_factory` | function | In-memory инстансы SQLAlchemy-моделей через `polyfactory.SQLAlchemyFactory` (см. `tests/conftest.py`). Поддерживают `**overrides`; синхронизируются со схемой моделей автоматически — добавление колонки больше не требует ручного обновления фабрики. TSVECTOR-колонки (`body_tsvector`) подменяются на `None` через override `get_type_from_column` |
| `real_db_session` / `real_user` / `real_editor` / `real_admin` | function | SAVEPOINT + ROLLBACK для integration-сценариев (см. п. 11 «Известные ограничения») |
| `security_authed_client_factory` | function | Алиас `authed_client_factory` для `tests/security/`; сигнализирует, что no-op `_fake_db` внутри осознан (проверяем authz/headers/CSRF, не данные). Использование `authed_client_factory` вне allowlist фейлит CI (job `fake-db-allowlist`) |

---

## Покрытие

### Backend Unit (3891 unit+security тестов по замеру 2026-07-26, gate 75% на merged unit+integration; фактическое merged unit+security покрытие 81.32%)

| Файл | Что покрывается |
|------|-----------------|
| `test_config.py` | Pydantic Settings, валидация SECRET_KEY, asyncpg-driver, `test_legacy_runtime_fields_removed` (ADR-037) |
| `test_health.py` | `/health` всегда 200, `/ready` корректно реагирует на падение PG/Redis |
| `test_audit_partitions.py` | Имена партиций, создание/дропание, retention=12мес |
| `test_security.py` | JWT parse, claims-mapping, cookie helpers |
| `test_session.py` | Redis-сессии, rotation, TTL, SLO |
| `test_news_service.py` | Таргетинг, версии, soft-delete, отложенная публикация |
| `test_news_categories.py` | `_load`/`_save` round-trip, дубликаты (case-insensitive), CRUD-эндпоинты, права reader/editor/admin |
| `test_links_bookmarks.py` | URL-валидация, `hidden_link_ids`, reorder, SSO `id_token_hint` |
| `test_logging.py` | Redaction секретов/PII (рекурсивно), truncation, `_event_oversize`, contextvars, `_parse_level`, `add_service_name_processor`, `set_log_level` (stdlib + structlog фильтрация) |
| `test_audit.py` | `push_audit_event`: полный payload, пустой metadata, проглатывание ошибок Redis, минимальные аргументы, сложный metadata; `audit.log()`: INSERT + commit, пустой metadata, проглатывание DB-ошибки, проглатывание commit-ошибки |
| `test_branding.py` | `_load_settings`/`_save_settings` round-trip; `_find_file`/`_delete_files` с mock-FS; `BrandingSettings` валидация; GET/PUT branding + email API-эндпоинты; права reader/editor/admin — 30+ тестов |
| `test_analytics.py` | Dashboard-эндпоинт, агрегация событий, права admin |
| `test_admin_users.py` | CRUD пользователей, фильтрация, права admin |
| `test_modules.py` | Включение/выключение модулей, persist, права |
| `test_notifications.py` | CRUD уведомлений, SSE, markRead/markAllRead |
| `test_search.py` | FTS-поиск по разным сущностям, фильтры |
| `test_system_settings.py` | Настройки системы, валидация, reset, `TestEnvMigration` (ADR-037 migration) |
| `test_uploads.py` | `stream_upload_to_path`: overflow → 413, MIME whitelist → 422, magic-bytes detection, fallback к content_type; `iter_upload_chunks` |
| `test_worker_tasks.py` | `_parse_dt`, `flush_audit_queue` (lock/пустая очередь/батч), `refresh_custom_metrics` |
| `test_worker_files_tasks.py` | `startup_sync_nc_folders`: nextcloud_disabled / lock_held / NextcloudError / пустой ответ NC / создание папок + восстановление прав / lock release error / запуск без Redis (7 тестов; покрытие модуля 94%) |
| `test_worker_notifications_tasks.py` | `_esc` (HTML/quotes/None); `_get_smtp_config` (missing / valid / corrupt JSON); `_build_news_email_html`/`_build_suggestion_email_html` (escape + approve/reject ветки); `send_email_notification` (happy / TLS+STARTTLS+auth / SMTP error re-raise); `notify_news_published` (фильтрация по departments+roles, swallow per-user errors); `notify_suggestion_reviewed_email` (approve/reject subject) — 17 тестов; покрытие модуля 94% |
| `test_worker_news_tasks.py` | `_flatten_kc_attributes` (None / drop LDAP-KERBEROS / unwrap single / multi / skip non-str); `publish_scheduled_news` (нет строк / enqueue per row / close при ошибке); `_enqueue_news_notifications` (success / swallows redis-error); `archive_expired_news` (парсинг `UPDATE N` / weird → 0); `sync_users_from_keycloak` (happy / bulk-groups error / loop-error → status в Redis) — 14 тестов; покрытие модуля 94% |
| `test_worker_photos_tasks.py` | `_slugify_import` (ASCII / cyr fallback / спецсимволы / пустая / collapse); `process_photo_upload` (not found / soft-deleted / folder missing / missing file); `cleanup_deleted_photos` (пустой / one purged); `generate_folder_zip` (job not found); `cleanup_zip_jobs` (пустой / unlink+delete); `detect_missing_thumbnails` (пустой / enqueue); `empty_photo_trash` (lock held → skipped); `import_scan_run` (root missing → error; **success-path moves files** — flush_batch ранее давал silent `_flush_batch` failure из-за `db = AsyncMock()` без правильной модели sync/async методов; теперь `db = MagicMock()` + явные `AsyncMock` на `flush/commit/scalar/execute` + `nested_cm` с `__aenter__`/`__aexit__`) — 26 тестов; покрытие модуля 33% (тяжёлые ветки оставлены интеграционным тестам) |
| `test_kb_acl.py` | ACL алгоритм: `_perm_gte`, `resolve_section_permission`, `resolve_article_permission`, `require_*_permission`, `filter_accessible_*`, `invalidate_*_cache`, batch-resolve section/article, apply_article_visibility, cascade invalidation через db, empty subject_ids, pipeline exception — 77 тестов |
| `test_kb_service.py` | `_slugify` (ascii/empty/cyrillic), `record_article_view` (dedup/first-view), `_resolve_tags`, `set_article_tags` — 12 тестов |
| `test_kb_articles.py` | list/create/get/update/draft/delete/restore, idempotency, 403/404/409/422 — 27 тестов |
| `test_kb_versions.py` | list_versions, restore_version, diff_versions (vs current/identical) — 12 тестов |
| `test_kb_sections.py` | get tree, create (201/404-parent/slug-collision), update (success/self-parent/cycle), delete (204/404/children/articles) — 15 тестов |
| `test_kb_export_import.py` | export md/zip/vault/pdf; import md (skip/overwrite/create_new/too-large/bad-encoding); import vault (bad-zip/empty/skip/create_new) — 20 тестов |
| `test_kb_markdown.py` | Slugify, optimistic locking (409), soft-delete, версионирование, view-dedup, комментарии, feedback, поиск, дерево разделов, diff, YAML frontmatter, ZIP-структура |
| `test_tls_status.py` | нет cert/key, парсинг notAfter+subject, OSError/TimeoutError проглочены, пустой stdout — 9 тестов |
| `test_webdav.py` | `_webdav_url`/`_resolve_url`/`_nc_relative_path`/`href_to_db_nc_path`/`_headers`, `_parse_propfind`, health_check, list_folder, create_folder, delete, move, aclose — 43 теста |
| `test_collabora.py` | `_try_richdocuments_ocs` (200-ok/non-200/ocs-status), `_try_direct_editing` (ok/non-200/error), `get_collabora_url` (can_write=False/ocs-ok/direct-fallback/both-fail/empty-nc_path/empty-editor_url), `get_collabora_url_via_federation` — 20 тестов |
| `test_auth_routes.py` | config/me/logout/local-login/refresh, вспомогательные функции — 29 тестов |
| `test_audit_routes.py` | `_build_filters` (8 вариантов), GET /audit /event-types /queue/depth /export.csv — 19 тестов |
| `test_news_routes.py` | `require_news_read_access`, list/get/create/update/delete/restore/purge/versions, idempotency, trash — 28 тестов |
| `test_news_export.py` | `_file_to_data_uri`, `_file_to_data_uri_resized`, `_inline_body_images`, `_build_export_html`, `_is_within_size_limit`, `_content_disposition`, export/html/md/pdf — 31 тест |
| `test_links_api.py` | list/get/create/update/delete/reorder/sso_redirect/icon — 30 тестов |
| `test_bookmarks.py` | `_favicon_cache_key`, GET /favicon (кэш/invalid/error/non-200/oversized/corrupt), CRUD, reorder — 21 тест |
| `test_files_upload.py` | idempotency, 404 folder, empty file, blocked mime, NC error, upload, commit error, open_in_collabora — 11 тестов |
| `test_files_folders.py` | get tree/folder, create (201/422/409/502), update (no-rename/rename/nc-error), delete (204/nc-404/nc-5xx) — 14 тестов |
| `test_files_ops.py` | `_bulk_inflight_key`/`_try_set_inflight`/`_clear_inflight`/`_validate_bulk_names`, DELETE /file, bulk-delete, bulk-move — 23 теста |
| `test_feedback_service.py` | create_feedback, load_admin_or_404, update_status, add_reply, load_for_attachment, delete_attachment, repo helpers, _common mapper-функции — 32 теста |
| `test_keycloak_admin.py` | `_is_unsafe_ip`, `_validate_keycloak_url`, `_load_kc_settings`, GET/PUT settings, POST test/oidc+sync, GET sync/status — 31 тест |
| `test_users_me_routes.py` | GET/PATCH /me, POST avatar, PATCH password — 10 тестов |
| `test_files_acl.py` | ACL файлов: `perm_gte` все комбинации, `_subject_ids_for_user` (id + keycloak_id + groups), `resolve_folder_permission` (admin/created_by/cache-hit/cache-none/direct/inherit/no-access), `require_folder_permission` (ok + 403), `filter_accessible_folders` (admin/user), `invalidate_folder_cache` — 20+ тестов |
| `test_nextcloud_service.py` | WebDAV-клиент: `_webdav_url` (root/subpath/spaces), `_parse_propfind` (файлы/skip-root), `health_check` (200→True/exception→False), `list_folder`/`create_folder`/`delete`/`move`/`upload_stream` happy path + error cases — 15+ тестов |
| `test_auth_callback_errors.py` | OIDC callback: ошибки провайдера → редирект на `/auth/error?reason=sso_failed` |
| `test_bookmarks_favicon.py` | `favicon_cache_key`: префикс, case-insensitive origin, разные origin → разные ключи; GET `/bookmarks/favicon` — cache hit, miss, таймаут |
| `test_concurrent_tasks.py` | Fixture `concurrent_tasks`: имитация параллельного запуска воркеров, идемпотентность |
| `test_files_bulk.py` | `bulk_delete` / `bulk_move`: права, несуществующие папки, частичные ошибки |
| `test_hydrate_custom_metrics.py` | Middleware `_hydrate_custom_metrics`: Redis snapshot → Prometheus gauge, отсутствие snapshot |
| `test_limiter.py` | `fastapi-limiter` unit: key-builder, зависимость `get_redis` |
| `test_photos_permissions.py` | Права доступа к фото: owner / shared / denied |
| `test_photos_sharing.py` | Share-токен: создание, TTL, revoke, повторный доступ |
| `test_redirects.py` | `safe_redirect`: разрешённые пути, отклонение абсолютных URL, `javascript:`, `//host` |
| `test_user_attribute_mappings.py` | Pydantic-схемы маппингов атрибутов: валидация, CRUD-эндпоинты, права admin |
| `test_users_public.py` | Публичный API пользователей: профиль, коллеги по отделу, права |
| `test_helpdesk_messages_tx.py` | helpdesk/messages.py (94%): `add_agent_reply`/`assign_ticket` outbox-инвариант (no-commit), `add_requester_reply` reopen (pending/resolved→open), `_eager_load_attachments`, `fetch_ticket_with_messages` — 10 тестов |
| `test_helpdesk_notifications.py` | helpdesk/notifications.py (99%): `_select_agents_to_notify`, `_fan_out` (commit-до-publish), все 5 `notify_*` (получатели/type/body/edge-cases) — 16 тестов |
| `test_helpdesk_tickets_service.py` | helpdesk/tickets.py (99%): `_agent_filter_conditions` (5 фильтров), `resolve_requester_user` (3 ветки), `reopen_ticket`/`change_status` (IllegalTransitionError), `assign_ticket`, count/list/fetch (user+agent), `link_guest_tickets`, `create_ticket` (инвариант первого сообщения) — 32 теста |
| `test_helpdesk_worker_poll.py` | worker/tasks/helpdesk.py (92%): `_module_enabled`, `poll_helpdesk_mailbox` (no-redis/not_configured/lock_held/bytes-str), `auto_close_resolved_tickets` (no-commit/commit-инвариант), `send_helpdesk_digest` (schedule/идемпотентность/lock/happy-path), archive+cleanup — 22 теста |
| `test_mailing_recipients.py` | mailing_recipients.py (97%): `_escape_like` parametrize, `list_recipients` (фильтр/пагинация/total), `get_recipient_or_404`, `update_recipient` (IntegrityError→409), `soft_delete_recipient`, endpoint authz — 30 тестов |
| `test_meetings_series_service_unit.py` | meetings/series_service.py (87%): `_recompute_canonical_rrule`, `_apply_series_update_to_booking` (5 сценариев), `create_booking_series`/`update_series` happy path, `_load_bookings_bulk`, чистые helpers — 32 теста |
| `test_photos_tag_repo.py` | services/photos_tag_repo.py (100%): list_tags_with_usage с/без фильтра q, find_tag_by_name (±None), get_tag, delete_tag, list_photo_tags, clear_photo_tags — 8 тестов |
| `test_photos_share_repo.py` | services/photos_share_repo.py (100%): list_folder/list_my_photo (scalars), list_my_folder (join), get_photo/get_folder (±None), fetch_by_token, scalar_folder_by_token — 9 тестов |
| `test_photos_permission_repo.py` | services/photos_permission_repo.py (100%): list (±empty), find (±None), delete с/без subject_type (контракт опционального фильтра) — 6 тестов |
| `test_news_comments_repo.py` | api/news/comments_repo.py (100%): count_active_comments (scalar_one), list_comments, get_comment_authors (empty-short-circuit/non-empty), get_comment (±None), increment/decrement (проверка `greatest(..., 0)` — защита от отрицательного счётчика при гонке) — 10 тестов |
| `test_staff_service.py` | api/users/staff_service.py (100%): дедуп департаментов (trim+empty), дедуп users по id, дедуп hidden_user_ids, rollback-контракт при ошибке в любой из 3 мутаций, порядок replace→apply→apply→commit→fetch, empty-body — 9 тестов |
| `test_helpdesk_archive_partitions.py` | services/helpdesk/archive_partitions.py (100%): имена партиций + количество, дефолт months_ahead=3, year-rollover (strftime), skip существующих через pg_class, SQL-форма CREATE TABLE PARTITION OF — 8 тестов |
| `test_limiter.py` | core/limiter.py (93%): real_ip_identifier/email_identifier (X-Real-IP/fallback/JSON/form/malformed), `test_patched_call_*` (6) — покрыты все ветки monkey-patch ADR-043: redis-None→Exception, skip-маршрута-без-path, methods-None-match, custom identifier/callback, **NoScriptError-reload (регрессия на багфикс №4 ADR-043)**, default-callback при блокировке. Тесты вызывают `patched_call` напрямую, обходя session-fixture stub |

### Backend Integration (real PG + Redis)

Все integration-тесты используют SAVEPOINT-стратегию изоляции (`real_db_session`): каждый тест выполняется внутри SAVEPOINT, откатываемого в конце — данные не остаются в БД, нет TRUNCATE, нет блокировок.

| Файл | Что покрывается |
|------|-----------------|
| `test_api_smoke.py` | `/health` 200, `/auth/me` 401/200, `/news` 401/200/403, CSRF POST без Origin → 403 |
| `test_migrations.py` | Alembic upgrade/downgrade idempotency + параметризованный `test_migration_revision_round_trip(revision)` по каждой ревизии (`head → downgrade {rev}-1 → upgrade {rev} → upgrade head`); список ревизий формируется через `pytest_generate_tests` из `ScriptDirectory.walk_revisions` (без поднятия БД на этапе collection) |
| `test_news_db.py` | INSERT/UPDATE/SELECT с реальной БД, FTS-поля, `target_departments` |
| `test_news_api.py` | API новостей через реальную БД: создание, фильтры, пагинация |
| `test_session_redis.py` | save/get/refresh/delete, TTL, replace-on-update |
| `test_kb_search.py` | tsvector, pg_trgm fallback, ILIKE accent-insensitive |
| `test_kb_acl_integration.py` | viewer/editor/manager изоляция (14 тестов); `inherit_permissions=false`; файлы → 403; локальные пользователи в ACL |
| `test_kb_media_integration.py` | media upload → URL содержит article_id; X-Accel-Redirect при отдаче; vault ZIP import → статьи создаются (8 тестов); CSRF double-submit |
| `test_local_auth.py` | bcrypt, bootstrap-admin idempotency, account-linking |
| `test_local_auth_db.py` | bcrypt-roundtrip через `users.password_hash` |
| `test_account_linking.py` | Привязка local/keycloak аккаунтов |
| `test_admin_users_db.py` | CRUD пользователей через реальную БД |
| `test_rate_limit.py` | fastapi-limiter с реальным Redis: 5 попыток / 15 мин |
| `test_rate_limit_matrix.py` | Auto-discovery rate-limited маршрутов через `app.routes` + `route.dependant.dependencies` (поиск `RateLimiter` instances); для каждого endpoint выполняется `times+1` запросов с уникальным IP → ассерт финальный `429`. Sanity-check `test_discovery_finds_known_endpoints` защищает от поломки интроспекции |
| `test_audit_partitions_real.py` | partitioned table, начальные партиции, INSERT routing |
| `test_analytics_db.py` | Analytics-эндпоинты с реальной БД: агрегация событий, фильтры по периоду |
| `test_bookmarks_race.py` | Конкурентное создание закладок: `MAX_BOOKMARKS_PER_USER` не превышается при race condition |
| `test_files_bulk.py` | Bulk-операции файлов через реальный стек: bulk-delete, bulk-move, права |
| `test_rate_limit_endpoints.py` | Rate-limit для не-auth эндпоинтов с реальным Redis |

### Backend Security

| Файл | Что покрывается |
|------|-----------------|
| `test_security_headers.py` | X-Content-Type-Options, X-Frame-Options, Permissions-Policy, X-Request-Id echo / length-limit, HSTS только в prod |
| `test_csrf.py` | double-submit cookie chain, GET без Origin = ok, POST без Origin = 403, неверный Origin = 403, exempt-пути (callback/logout/collabora-federation), origin-only (local/login без токена), Referer-фолбэк, scheme-mismatch → 403, авто-выдача XSRF-TOKEN на safe-методах — 14 тестов. Прим.: Sec-Fetch-Site для logout тестируется в `test_auth_routes.py` (1055-1104) |
| `test_auth_required.py` | 9 protected endpoints без сессии = 401, admin-only для admin-эндпоинтов |
| `test_session_fixation.py` | Регенерация session ID при логине (protection against session fixation) |
| `test_xss_sanitization.py` | `<script>`, `<iframe>`, `<svg onload>`, `javascript:`, `<style>`, `<meta>` strip; data:image/png whitelisted; safe HTML preserved |
| `test_password_security.py` | bcrypt roundtrip, длинный пароль (>72 байт через SHA256-prehash), unicode, salt uniqueness |

### Конвенция «one component per file» для frontend smoke-тестов

Исторически в `tests/unit/` присутствуют сборные файлы `components-smoke-extra*.spec.ts` (5 шт., ~1.7K строк): каждый держит общий блок `vi.mock(...)` и несколько `describe(<Component>.vue, ...)` подряд. Это даёт минимум boilerplate в обмен на хрупкость (изменение мока в шапке валит чужие тесты) и плохой grep-onboarding.

Правило для нового кода:

- **smoke-тест компонента/страницы** ⇒ отдельный файл `tests/unit/<kebab-case-name>.spec.ts` (например, `not-found-page.spec.ts`, `trash-page.spec.ts`).
- Файл содержит ровно один `describe(<Component>.vue, ...)` и собственный, минимально-достаточный набор `vi.mock` для своих зависимостей.
- Имя файла соответствует компоненту в `kebab-case`, без префикса `components-`.
- Для уже расселённых блоков в `components-smoke-extra*.spec.ts` оставляется хвост-комментарий со ссылкой на новое расположение, чтобы grep по имени компонента находил оба места.

Постепенный план: при касании любого `describe` внутри `components-smoke-extra*.spec.ts` блок выносится в отдельный файл. Цель — полностью растащить «сборники» и удалить их.

✅ **Итерация 17 (2026-07-20)**: все 5 `components-smoke-extra*.spec.ts` растащены — 24 describe → 24 отдельных файла (112 тестов, контракт 1:1). Также растащен `pages-smoke.spec.ts`: 11 describe → 11 отдельных файлов (24 теста); 7 страниц уже имели поведенческие тесты и были исключены из растаскивания. Оригинальные сборные файлы удалены. Правило «one component per file» теперь соблюдается полностью — сборных smoke-файлов в `tests/unit/` больше нет.

Уже расселены ранее: `NotFoundPage.vue` → `tests/unit/not-found-page.spec.ts`; `TrashPage.vue` → `tests/unit/trash-page.spec.ts`.

### Frontend Unit (Vitest: 2111 тестов в 214 spec-файлах по замеру 2026-07-20; покрытие 66.67% lines / 60.58% branches / 54.26% funcs / 68.31% stmts; пороги подняты и зафиксированы 65/52/59/66; smoke-сборники `pages-smoke.spec.ts` + `components-smoke-extra{1..5}.spec.ts` растащены в 35 файлов; новые поведенческие тесты на NewsListPage/MyFeedbackPage/KbArticlePage; добавлены utils-тесты на `formatDate` (100%) и `sanitize` (100% lines / 95.65% branches); 15 нулевых файлов закрыты, в т.ч. composables useHomeNews/useManageDrawer/useCollabora/useStaffView/usePhoneFormat)

| Файл | Что покрывается |
|------|-----------------|
| `url.spec.ts` | `isSafeHttpUrl` отвергает `javascript:`/`data:`/`file:`/`vbscript:` |
| `sanitize.spec.ts` | DOMPurify XSS-щит для v-html |
| `router-guards.spec.ts` | `isLocalUser`, `redirectToLogin` с правильным redirect-параметром |
| `router-guards-extended.spec.ts` | `requireAuth` (ok/network-error/unauthenticated), `requireRole` (reader/editor/admin), `requireModule` (isEnabled/cache TTL) — 13 тестов |
| `rich-editor.spec.ts` | Smoke-импорт компонента (TipTap mocked) |
| `admin-page.spec.ts` | lazy-loaded tab-компоненты AdminPage (import-only, 11 тестов) |
| `api-types.spec.ts` | type-safety API-клиентов (23 теста) |
| `auth.spec.ts` | `useAuthStore`: роли, `loadUser`, ошибки сети |
| `branding-store.spec.ts` | `useBrandingStore`: `isBannerActive`, `loadSettings`, CSS-переменные |
| `email-tab.spec.ts` | email-настройки в branding: маскировка пароля, сохранение |
| `links-store.spec.ts` | `useLinksStore`: CRUD, reorder |
| `modules-store.spec.ts` | `useModulesStore`: enabled/disabled |
| `notifications-store.spec.ts` | SSE connect/disconnect, read/readAll/remove, reset |
| `notifications-api.spec.ts` | `src/api/notifications.ts`: `fetchNotifications`, `fetchUnreadCount`, `markRead`, `markAllRead`, `deleteNotification` — 9 тестов |
| `auth-api.spec.ts` | `src/api/auth.ts`: `fetchMe`, `refreshSession`, `localLogin`, `changePassword`, URL-builders (encoding, defaults) — 9 тестов |
| `feedback-api.spec.ts` | `src/api/feedback.ts`: CRUD, admin-маршруты, reply/status, `uploadFeedbackAttachment`, `deleteFeedbackAttachment`, лимиты — 12 тестов |
| `links-api.spec.ts` | `src/api/links.ts`: links+bookmarks CRUD, reorder, `getSsoUrl`, `uploadLinkIcon` — 14 тестов |
| `files-api.spec.ts` | `src/api/files.ts`: folders CRUD, permissions CRUD, bulk ops, upload, sync, `formatFileSize`, `fileIcon`, `isPreviewable*`, `isCollaboraFile`, `downloadFile`, `previewFile` — 62 теста |
| `news-api.spec.ts` | `src/api/news.ts`: CRUD, черновик, cover, gallery, attachments, categories, trash/restore/purge, AbortSignal — 30 тестов |
| `kb-api.spec.ts` | `src/api/kb.ts`: sections/articles/versions/comments CRUD, `suggestEdit`, export/import с strategy, `globalSearch+suggest` — 38 тестов |
| `photos-api.spec.ts` | `src/api/photos.ts`: folders CRUD, photos CRUD, tags, sharing, trash, zip — 58 тестов |
| `use-app-menu.spec.ts` | `useAppMenu`: `activeKey` для всех роутов, видимость меню по модулям/ролям, `handleMenuSelect` — 13 тестов |
| `app-layout-smoke.spec.ts` | `AppHeader` (5) / `AppSider` (5) / `HeaderUserMenu` (4) / `AppLayout` (5) — smoke renders/props/emits |
| `global-search-smoke.spec.ts` | `GlobalSearch`: show/hide, input, recent, Esc, results, no-results, reset — 10 тестов |
| `files-table-smoke.spec.ts` | `FilesTable`: renders, data table, file/dir items, row-click, selectedKeys — 9 тестов |
| `files-toolbar-smoke.spec.ts` | `FilesToolbar`: folder name, permission tags, upload/manage buttons, NProgress — 15 тестов |
| `files-bulk-permissions-smoke.spec.ts` | `FilesPermissionsModal` (4) + `FilesBulkBar` (8) — show/hide, count, emits, canUpload |
| `kb-components-smoke.spec.ts` | `KbSectionTree` (6) / `KbCommentsTab` (3) / `KbVersionsTab` (3) / `KbPermissionsModal` (4) |
| `photos-components-smoke.spec.ts` | `PhotosGrid` (7) / `LightboxModal` (6) / `PhotosTrashView` (6) |
| `pages-smoke.spec.ts` | ~~удалён в итерации 17~~ — растаскан в 11 отдельных файлов (`auth-*-page`, `news-*-page`, `kb-article-page`, `links-and-bookmarks-page`, `my-*-page`, `public-photo-page`); 7 страниц уже имели поведенческие тесты и были исключены из растаскивания |
| `components-smoke-extra*.spec.ts` | ~~удалены в итерации 17~~ — растасканы в 24 отдельных файла (`empty-state`, `skeleton-card`, `news-card`, `kb-article-*`, `staff-*`, `link-card`, `hero-block`, …). Правило «one component per file» теперь соблюдается полностью |
| `link-visuals.spec.ts` | `useLinkVisuals`: `colorFor`, `faviconFor`, `shortUrl`, `onIconError` — 12 тестов |
| `utils-coverage.spec.ts` | `formatDate`/`formatDateShort` (ru/en), `formatRelativeTime` (4 ветки abs<45/2700/79200/2592000 в обе стороны + граница 44s, через `vi.setSystemTime`), `formatSize`, `markdown`, `parseApiError` (401/403/422/500, FetchError, field translations), `triggerDownload`, `coverFocal` |
| `sanitize.spec.ts` | XSS-щит для v-html: DOMPurify base + 4 профиля (`sanitizeHtml`, `sanitizeHelpdeskHtml`, `sanitizeHtmlAllowIframe`, `sanitizeKbHtml`): script/iframe/style/onclick/javascript: strip, figure/figcaption whitelist, KB-домены iframe (youtube/rutube/vimeo/vk), allowedOrigins для sanitizeHtmlAllowIframe, style-sanitize hook edge-cases, malformed-URL catch-ветки — 53 теста |
| `photos-store.spec.ts` | `usePhotosStore`: `loadRecent`, ошибки, guard против двойного вызова |
| `photo-decomposition.spec.ts` | `usePhotoUpload` composable: интерфейс, uploadingActive |
| `theme-store.spec.ts` | `useThemeStore`: dark/light toggle |
| `auth-store-sso.spec.ts` | `useAuthStore`: loop-protection, SSO state, повторный fetchMe при redirect |
| `department-colleagues.spec.ts` | `DepartmentColleagues`: рендер списка, ошибки загрузки, пагинация |
| `extract-dropped-files.spec.ts` | `extractDroppedFiles`: файлы, директории, DataTransferItem API |
| `files-store.spec.ts` | `useFilesStore`: дерево папок, `fetchFolderDetail`, `createFolder`, `deleteFolder`, `syncFromNextcloud` |
| `user-profile-view.spec.ts` | `UserProfileView`: smoke-импорт, fetch коллег, навигация назад |
| `helpdesk-my-tickets-page.spec.ts` | `HelpdeskMyTicketsPage`: заголовок/кнопка, empty-state, список, goToTicket→router.push, error, create-modal, pagination-args — 7 тестов |
| `helpdesk-my-ticket-detail-page.spec.ts` | `HelpdeskMyTicketDetailPage`: load по route.params.id, форма ответа для открытого/алерт для закрытого, onReply+reload, goBack, error-handling — 7 тестов |
| `helpdesk-agent-inbox-page.spec.ts` | `HelpdeskAgentInboxPage`: фильтры/empty/список, goToTicket, onTake (success+reload/error), pagination/unassigned/q args — 8 тестов |
| `helpdesk-agent-ticket-detail-page.spec.ts` | `HelpdeskAgentTicketDetailPage`: load, Take vs n-select (assignee), onTake/onStatusChange/onReopen, visibility Reopen-кнопки, onReply, goBack — 10 тестов |
| `i18n-config.spec.ts` | `src/i18n/index.ts`: mode=composition, дефолт ru, fallback ru, оба message-объекта, loadLocale no-op, общий набор доменов — 6 тестов |

### Frontend E2E (Playwright)

| Файл | Сценарий |
|------|---------|
| `smoke.spec.ts` | `/login` рендерится, security-headers пришли |
| `auth.spec.ts` | OAuth-редирект, callback с ошибкой |
| `local-login.spec.ts` | Bootstrap admin → логин → главная; неверный пароль → остаётся на /login |
| `security-headers.spec.ts` | Браузер видит ожидаемые заголовки от nginx/backend |
| `kb-acl.spec.ts` | ivanov/petrov/sidorov ACL: grant → viewer читает, viewer не редактирует, inherit=false/true |
| `kb-media.spec.ts` | media upload → URL; vault ZIP import → статьи; CSRF double-submit |
| `photos.spec.ts` | фото-галерея: загрузка, просмотр, папки |
| `admin-login.spec.ts` | Локальный вход через `/auth/local`: admin bootstrap → логин → панель администратора |
| `auth-sso-redirect.spec.ts` | Auto-SSO redirect: `page.route`-стаб → ошибка SSO → `/auth/error` отображается |
| `files-bulk.spec.ts` | Bulk-операции файлов: выбор нескольких файлов → bulk-delete, bulk-move |

### Load (k6)

| Сценарий | Пороги |
|----------|--------|
| `smoke.js` | 1 VU, 5 итераций; p95 < 1s, checks > 99% |
| `baseline.js` | ramp 50 VU; p95 < 2s |
| `search.js` | 50 VU/1мин на `/search?q=...`; p95 < 1s, p99 < 1.5s — ТЗ §7 |
| `portal-load.js` | ramp 0→100→300 VU; `http_req_duration p95 < 2000ms`, `search_latency_ms p95 < 1000ms` — ТЗ §7 |

---

## CI (GitHub Actions)

Workflow определён в `./.github/workflows/ci.yml`. Реализованные job'ы:

| Job | Триггер | Что делает |
|-----|---------|-----------|
| `backend-lint` | push/PR | ruff check + format + mypy |
| `screenshot-unit` | push/PR | unit-тесты `screenshot-service/` (pytest, только `requirements-dev.txt` — `cookie_utils.py` не зависит от aiohttp/playwright, тяжёлый образ не нужен) |
| `backend-unit` | push/PR | unit + security, собирает `.coverage.unit` (`--cov=app --cov-report=`), без гейта на этом шаге; артефакт `coverage-data-unit` (retention 1 день) |
| `backend-integration` | push/PR (после `backend-lint` + `backend-unit`) | строит `portal-postgres:ci` (postgres:16 + hunspell-ru), поднимает postgres+redis, `alembic upgrade head`, `pytest tests/integration -rs --cov=app --cov-report= --reruns 2 --reruns-delay 1 --only-rerun "OperationalError\|ConnectionRefused\|ConnectionReset\|TimeoutError\|asyncpg\\..*Error\|redis\\.exceptions\\.ConnectionError"` (`INTEGRATION_DB=true INTEGRATION_REDIS=true`); артефакт `coverage-data-integration` |
| `backend-coverage` | push/PR (после `backend-unit` + `backend-integration`) | скачивает оба `coverage-data-*` артефакта, `coverage combine` → `coverage report` → `coverage xml + html`, енфорсит gate `--fail-under=75` (см. `[tool.coverage.run] parallel = true, relative_files = true` и `[tool.coverage.paths]` в `./backend/pyproject.toml`; `[tool.coverage.report] fail_under = 75`); артефакт `backend-coverage` (htmlcov + xml, retention 14 дней) |
| `frontend-lint` | push/PR | `npm run gen:types` → ESLint + `vue-tsc --noEmit` + i18n keys |
| `frontend-unit` | push/PR | Vitest (включает coverage-thresholds из `vite.config.ts`); артефакт `frontend-coverage` |
| `openapi-drift-check` | push/PR | перегенерирует `openapi.json` через `./backend/scripts/export_openapi.py`; падает с подсказкой команды, если результат отличается от закоммиченного |
| `frontend-types-drift` | push/PR | регенерирует `./frontend/src/api/types.gen.d.ts` (`npm run gen:types`); фейлит CI при drift → гарантирует, что сгенерированные типы в репозитории соответствуют `openapi.json` |
| `shellcheck` | push/PR | `shellcheck --severity=warning` по всем `*.sh` из `git ls-files` (не только `setup.sh`) |
| `coverage-comment` | PR only (после `backend-coverage` + `frontend-unit`, `pull-requests: write`) | скачивает `backend-coverage` + `frontend-coverage`, генерирует markdown через `irongut/CodeCoverageSummary@v1.3.0` (без токена) из `cobertura-coverage.xml` + `coverage.xml`, постит/обновляет sticky PR-комментарий через `marocchino/sticky-pull-request-comment@v2`. `cobertura`-репортер для frontend настроен в `./frontend/vite.config.ts` |
| `tests-generated-drift` | push/PR | ставит backend + frontend deps, прогоняет `bash scripts/list_tests.sh` (регенерирует `./docs/tests.generated.md`), фейлит CI при `git diff` — гарантирует синхронность сгенерированной описи тестов с реальным `pytest --collect-only` / `vitest list` |
| `frontend-e2e` | push/PR (после `backend-lint` + `frontend-lint`, timeout 20 мин) | строит `portal-postgres:ci` + redis, `alembic upgrade head`, поднимает uvicorn в фоне, `playwright install --with-deps chromium`, прогоняет `chromium`-проект в `E2E_MODE=dev` + `VITE_API_TARGET=http://localhost:8000` (vite-dev проксирует `/api`); артефакт `playwright-report/` (retention 14 дней) |
| `fake-db-allowlist` | push/PR | проверяет, что `authed_client_factory` (с no-op `_fake_db`) используется только из файлов в `./backend/tests/fake_db_allowlist.txt`; новые файлы вне списка фейлят CI. Stale-записи (есть в allowlist, нет в коде) — `::notice::`, не фейл, чтобы можно было постепенно сокращать |
| `compose-smoke` | push/PR | создаёт `base_data/upload_data/system_data/`, минимальный `.env`, поднимает `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis migrations backend`, smoke-проверяет `GET /docs`, `GET /openapi.json`, `GET /api/v1/users/me` (ожидает 401/403); tear-down на `always()` |
| `quality-gates` | push/PR | комплексный quality-gate: **complexity** (`radon cc app -n D` — блокирует любые rank-D+ функции с CC>10, фиксирует результат декомпозиции аудита 2026-07-20); **duplication** (`jscpd` frontend, fail >4%, см. `frontend/.jscpd.json`); **dead-code** (`knip` frontend, informational — `continue-on-error`, ложноположительные на публичных хук/тип-экспортах) |

### Nightly workflows

| Workflow | Триггер | Что делает |
|----------|---------|-----------|
| `./.github/workflows/nightly-flakes.yml` (`flake-detect`) | cron `17 2 * * *` + `workflow_dispatch` | поднимает PG+Redis, `alembic upgrade head`, прогоняет полный suite (`tests/unit tests/security tests/integration`) **5 раз** с `-p no:randomly -p no:cacheprovider`, агрегирует `FAILED `-строки из лога каждого прогона, печатает таблицу «тест → сколько раз упал» в `$GITHUB_STEP_SUMMARY`; артефакт `flake-reports/` (junit XML + логи, retention 30 дней) |
| `./.github/workflows/nightly-security.yml` (`zap-baseline`) | cron `37 3 * * *` + `workflow_dispatch` | поднимает PG+redis+uvicorn, запускает `ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://localhost:8000 -c zap-baseline.conf` с конфигом `./security/zap-baseline.conf`; парсит `zap-report.json` (High/Medium/Low/Info) в `$GITHUB_STEP_SUMMARY`; артефакт `zap-report/` (HTML+JSON, retention 30 дней); фейлит job при наличии High-risk alerts |

### Релизный конвейер (ADR-045 / ADR-046 / ADR-047)

Три job'а в `ci.yml`, формирующих pull-based деплой. Подробное обоснование и состав — в
[`adr.md`](./adr.md) (ADR-045 — GHCR + pull-deploy, ADR-046 — prod без клона репо,
ADR-047 — semver-lock).

| Job | Триггер | Что делает |
|-----|---------|-----------|
| `validate-release-tag` | только тег `v*` (на main-push — `skipped`, считается success) | валидирует формат semver (`^v[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$`, согласован с `scripts/release.sh`) и что тег указывает на коммит из истории `origin/main` (защита от релиза feature-ветки). `~10 сек`, `fetch-depth: 0` |
| `publish-images` | push в `main` **и** тег `v*` (НЕ на PR) | gate `needs: [backend-lint, backend-unit, backend-integration, frontend-lint, frontend-unit, frontend-e2e, compose-smoke, screenshot-unit, validate-release-tag]` — образ с упавшими интеграционными/e2e не уйдёт в GHCR. Matrix из 6 образов (`portal-backend`, `-frontend`, `-nginx`, `-nginx-config`, `-screenshot`, `-postgres`) с `cache-from/cache-to: type=gha`. Теги: на main — `sha-<7>` + `latest`; на `v1.2.3` — дополнительно `v1.2.3`, `v1.2`, `v1`. `permissions: packages: write`, actions пинены по SHA. `~8–12 мин` (с кэшем ~3–5 мин) |
| `deploy-bundle` | только тег `v*`, после `publish-images == success` | собирает `portal-deploy-bundle-<tag>.tar.gz` (~80 КБ): `docker-compose.yml` + `.env.example` + `setup.sh` + `monitoring/` целиком (overlay-конфиги + `node-exporter-textfile/` для локальной сборки `portal-storage-collector`, который не в registry). Аттачит к GitHub Release через `softprops/action-gh-release@<sha>`. `permissions: contents: write`. `~30 сек` |

> **Семантика тегов** (ADR-047): `latest` продолжаeт пушиться, но prod-контур
> (`setup.sh::preflight`) отвергает `IMAGE_TAG=latest` как implicit-deploy —
> прод обязан пиниться к релизному тегу `v1.x.x`. См. `docs/deploy.md` §12
> «Миграция с :latest на semver-lock».

### CODEOWNERS

`./.github/CODEOWNERS` разбит по подсистемам (CI/инфра, backend, backend/tests, migrations, frontend, frontend/tests, security, load, docs) — каждый PR с изменениями получает корректного ревьюера автоматически.

---

## Критерии приёмки (ТЗ §7)

- ✅ Unit-тесты пишутся одновременно с кодом
- ✅ Integration: реальный PG + Redis, alembic upgrade в CI
- ✅ Security: CSRF / XSS / headers / passwords / auth-required
- ✅ E2E ≥ 90% ключевых путей — 10/11 сценариев ТЗ §8.4 автоматизированы
- ✅ Load: k6 со сценариями smoke / baseline / search / 300 VU
- ✅ OWASP ZAP baseline — нет High-алертов (см. `docs/test-report.md`)

---

## Покрытие: Branding System (Step 6.8)

| Слой | Что покрывается |
|------|----------------|
| **Unit** | `_load_settings()` / `_save_settings()` round-trip; `_find_file` / `_delete_files` с mock-FS; `BrandingSettings` валидация (accent_color, banner_type); `isBannerActive` computed с `banner_expires_at` в прошлом/будущем |
| **Integration** | `GET /branding/settings` — возвращает defaults без файла; `PUT /admin/branding/settings` — forbidden для reader/editor; logo/favicon/login-bg upload → GET round-trip; размер > 2 МБ → 413 |
| **E2E** | Smoke: страница входа рендерится с кастомным portal_name; баннер отображается и закрывается кнопкой ✕; admin загружает логотип → отображается в AppLayout |
| **Security** | `PUT /admin/branding/settings` без cookie → 401; reader cookie → 403; XSS в `banner_text` — DOMPurify на фронте |

> ✅ Unit-тесты для branding реализованы в `test_branding.py` (30+ тестов). Integration-тесты не реализованы — покрываются unit-тестами с mock-FS и E2E smoke.

---

## Покрытие: Files / Nextcloud Integration (Phase 5)

| Слой | Что покрывается |
|------|----------------|
| **Unit** | `test_files_acl.py` — алгоритм ACL, рекурсия (20+ тестов); `test_nextcloud_service.py` — `_parse_propfind` (XML), `_webdav_url` (URL-кодирование), WebDAV-операции с httpx mock (15+ тестов); `test_uploads.py` — MIME-whitelist, magic-bytes, overflow 413 |
| **Integration** | Не реализованы; требуют мок-Nextcloud или реальный экземпляр |
| **E2E** | Не реализованы; требуют реальный Nextcloud с `portal-svc` App Password |
| **Security** | `GET /files/tree` без cookie → 401; reader без прав на папку → 403; модуль выключен → 503 |

> ℹ️ Интеграционные и E2E тесты для файлового модуля не реализованы — требуют реального Nextcloud с `NC_SERVICE_APP_PASSWORD`. Проверяются вручную на staging.

---

## Интеграционные и E2E `skip` — поведение по умолчанию

Часть тестов помечена `pytest.skipif`/`test.skip` и **по умолчанию пропускается** на чистой машине:

| Группа | Маркер skip'а | Чем включить |
|--------|---------------|--------------|
| Backend integration (real PG) | `INTEGRATION_DB` | `INTEGRATION_DB=true` + доступ к Docker (testcontainers поднимает `portal-postgres:16`) |
| Backend integration (real Redis) | `INTEGRATION_REDIS` | `INTEGRATION_REDIS=true` + Redis 7 (или fakeredis) |
| Frontend E2E (Playwright) | переменные `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD` | задать в env запуска (см. `frontend/tests/e2e/*.spec.ts`) |
| Migrations stepwise round-trip | вместе с остальной integration-группой | `INTEGRATION_DB=true` |

> Локально это удобно — но в CI оборачивается «зелёным» прогоном с нулевым покрытием.
> Поэтому в `.github/workflows/ci.yml` integration/e2e job'ы вынесены в `nightly/manual`,
> а в обычный PR-pipeline входят только unit + security + frontend unit. Для аудита
> фактически прогоняемых тестов используйте `pytest --co -q | tail` и `pytest -rs`
> (вывод reasons для пропусков).

---

## Известные ограничения

1. **`fakeredis`** используется в unit-тестах rate-limit, реальный Redis — в integration. `RateLimiter.__call__` подменяется no-op'ом в unit-тестах (fakeredis не поддерживает Lua SCRIPT, нужный fastapi-limiter); реальный rate-limit покрывает `./backend/tests/integration/test_rate_limit.py` + `test_rate_limit_endpoints.py`.
2. **`load/portal-load.js`** не запускается в CI (требует staging-инстанс) — только `k6 inspect`.
3. **Playwright E2E** в CI: `chromium`-проект на каждом PR/push (job `frontend-e2e` поднимает backend через uvicorn + PG/Redis); `firefox`/`webkit` — локально и в nightly. `fullyParallel: true`, `workers: 4` в CI; спеки с межтестовыми зависимостями (`kb-acl`, `kb-media`, `photos`) маркированы `test.describe.configure({ mode: 'serial' })`.
4. **Coverage gate** = 75% по объединённому отчёту backend (unit + security + integration через `coverage combine` в job `backend-coverage`, `[tool.coverage.run] parallel = true, relative_files = true`, `[tool.coverage.paths]` для маппинга CI-путей; `[tool.coverage.report] fail_under = 75` в `./backend/pyproject.toml`); frontend — 50% lines/functions/statements, 35% branches (`vite.config.ts` thresholds).
5. **KB ACL integration-тесты**: локальные пользователи используют `str(user.id)` как `subject_id` (не `keycloak_id`).
6. **KB Media integration-тесты**: все POST требуют CSRF double-submit (`XSRF-TOKEN` cookie = `x-xsrf-token` header) и `get_db` override для видимости uncommitted данных.
7. **Branding integration тесты** — не реализованы; покрываются unit-тестами с mock-FS и E2E smoke.
8. **Files (Nextcloud) integration/E2E тесты** — требуют мок-Nextcloud или реальный экземпляр с `portal-svc` App Password.
9. **Photos integration/E2E тесты** — требуют реального тома `/data/photos` и Pillow; запускаются вручную на staging.
10. **Worker tasks** (`photos.py`, 33%) — тяжёлые happy-path ветки (`generate_folder_zip`, `empty_photo_trash`, `import_scan_run`) требуют реальной БД и файловой системы; оставлены для integration-тестов. Остальные worker-модули покрыты unit-тестами: `files.py` 96%, `news.py` 86%, `notifications.py` 96%, `helpdesk.py` 92% (итерация 16), `audit.py` 96%, `metrics.py` 96%, `email_outbox.py` 96%.
11. **INTEGRATION_DB default-стратегия**: `real_db_session` использует SAVEPOINT + ROLLBACK (не TRUNCATE); `session.commit()` в тестах запрещён — переносит изменения за границу SAVEPOINT.
12. **Flake retry-policy**: `backend-integration` в CI использует `pytest-rerunfailures` с `--reruns 2 --reruns-delay 1` и whitelist по сетевым/БД-ошибкам (`OperationalError`, `ConnectionRefusedError`, `ConnectionResetError`, `TimeoutError`, `asyncpg.*Error`, `redis.exceptions.ConnectionError`). Нестабильность по другим причинам падает сразу. Для статистики flake'ов — nightly workflow `nightly-flakes` (5 прогонов, отчёт в `$GITHUB_STEP_SUMMARY` + артефакт `flake-reports/`).
13. **Pytest warning policy** (`./backend/pyproject.toml` → `[tool.pytest.ini_options].filterwarnings`): `error::DeprecationWarning`, `error::RuntimeWarning:app.*` — любые рантайм-предупреждения из `app.*` фейлят прогон (ловят корутины без `await`, неправильные моки в продкоде). Подавление `PytestUnraisableExceptionWarning` снято — все AsyncMock-долги починены поштучно (правило: для SQLAlchemy `AsyncSession` мокировать через `MagicMock()` + явные `AsyncMock` на async-методах (`execute`, `scalar`, `flush`, `commit`, `scalars` если awaited), а sync-методы (`add`, `begin_nested`) оставлять синхронными; для `async with db.begin_nested():` собирать `nested_cm = MagicMock()` с `__aenter__`/`__aexit__` = `AsyncMock`).
14. **Открытые пункты плана** — см. `./test.md` (раздел 0 — что уже сделано; разделы 1–9 — оставшиеся дефекты со сложностью и приоритетом).
