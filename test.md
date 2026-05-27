# План устранения недочётов системы тестирования

> Ревью от мая 2026. База: backend (~1715 unit + 70 security + ~250 integration), frontend (~982 vitest, 10 e2e), CI: `./.github/workflows/ci.yml`.
> Шкала сложности: **S** — часы, **M** — 1–3 дня, **L** — неделя, **XL** — спринт+.

---

## 0. Уже сделано в этой итерации

- **1.2** — переписаны слабые ассерты в `./frontend/tests/e2e/smoke.spec.ts` и `./frontend/tests/e2e/auth.spec.ts` (проверка HTTP-кодов, конкретных DOM-элементов, осмысленных URL-условий).
- **3.1** — удалены кастомные `event_loop` фикстуры из `./backend/tests/conftest.py` и `./backend/tests/integration/conftest.py`; в `./backend/pyproject.toml` добавлен `asyncio_default_fixture_loop_scope = "session"`, поднят `pytest-asyncio>=0.23.5`, убран `ignore` для `event_loop fixture` deprecation. Все 1715 unit + 70 security тестов проходят.
- **3.3** — добавлен `E2E_MODE=dev|preview` в `./frontend/playwright.config.ts`; в CI по умолчанию `preview` (build + `vite preview`), локально — `dev`.
- **3.5** — добавлены Playwright-проекты `firefox` и `webkit` в `./frontend/playwright.config.ts` (исключают mobile-спеки).
- **5.3** — удалены 8 бесполезных `pytest.importorskip("fastapi"/"httpx"/"sqlalchemy")` из integration-тестов (`test_account_linking.py`, `test_api_smoke.py`, `test_files_bulk.py`, `test_news_api.py`, `test_analytics_db.py`); ruff-нарушения из-за порядка импортов исправлены.
- **6.2** — `shellcheck`-job в `./.github/workflows/ci.yml` теперь проверяет все `*.sh` через `git ls-files`, а не только `setup.sh`.
- **6.3** — добавлен новый job `frontend-types-drift` в `./.github/workflows/ci.yml`: регенерирует `frontend/src/api/types.gen.d.ts` и фейлит CI при drift.
- **7.2** — расширен `./.github/CODEOWNERS` с разбивкой по подсистемам (CI/инфра, backend, frontend, security, load, docs).
- **2.3** — `backend-integration` теперь собирает `--cov=app` в `.coverage.integration` (был `--no-cov`). Новый job `backend-coverage` в `./.github/workflows/ci.yml` скачивает оба артефакта (`coverage-data-unit`, `coverage-data-integration`), делает `coverage combine`, печатает report, генерирует `coverage.xml` + `htmlcov`, енфорсит gate `--fail-under=70`. В `./backend/pyproject.toml` добавлены `parallel = true`, `relative_files = true` в `[tool.coverage.run]` и `[tool.coverage.paths]` для маппинга CI-путей.
- **3.4** — добавлен `pytest-rerunfailures>=14.0` в `./backend/pyproject.toml [project.optional-dependencies].dev`. `backend-integration` job в `./.github/workflows/ci.yml` теперь использует `--reruns 2 --reruns-delay 1 --only-rerun "OperationalError|ConnectionRefusedError|ConnectionResetError|TimeoutError|asyncpg\\..*Error|redis\\.exceptions\\.ConnectionError"`. Создан новый workflow `./.github/workflows/nightly-flakes.yml`: cron `17 2 * * *` + `workflow_dispatch`, прогоняет полный suite 5 раз, агрегирует упавшие тесты в `$GITHUB_STEP_SUMMARY` и загружает `flake-reports/` (30 дней).

### Спринт 1 (быстрые победы)

- **6.1** — в `./frontend/vite.config.ts` добавлен `cobertura`-репортер в `coverage.reporter`. В `./.github/workflows/ci.yml` добавлен job `coverage-comment` (только PR, `permissions: pull-requests: write`): скачивает артефакты `backend-coverage` + `frontend-coverage`, формирует markdown через `irongut/CodeCoverageSummary@v1.3.0` (без токена) и постит/обновляет sticky-комментарий через `marocchino/sticky-pull-request-comment@v2`.
- **7.1** — в `./.github/workflows/ci.yml` добавлен job `tests-generated-drift`: устанавливает backend + frontend deps, прогоняет `bash scripts/list_tests.sh`, фейлит CI при изменении `docs/tests.generated.md`. Сам `./docs/tests.generated.md` регенерирован под текущее состояние.
- **1.1** — в `./.github/workflows/ci.yml` добавлен job `frontend-e2e` (нужен `backend-lint` + `frontend-lint`, timeout 20 мин): docker-PG (`portal-postgres:ci` с hunspell) + redis, `alembic upgrade head`, uvicorn в фоне, `playwright install --with-deps chromium`, прогон `E2E_MODE=dev` + `VITE_API_TARGET=http://localhost:8000` (vite-dev проксирует `/api`). Артефакт `playwright-report/` на 14 дней.

### Спринт 3 (стратегия)

- **2.4** — в `./frontend/vite.config.ts` подняты coverage-пороги: `lines`/`statements` 50→60, `branches` 35→60, `functions` 50→45 (текущий факт ~63/79/49); в `coverage.exclude` добавлен barrel `src/queries/index.ts`. Запуск `vitest run --coverage` зелёный.
- **5.2** — из `./backend/pyproject.toml` `[tool.ruff.lint.per-file-ignores]` для `tests/*` удалён `F401`; 99 нарушений `unused-import` авто-исправлены в 55 файлах `tests/unit/`, `tests/integration/`, `tests/security/`. TODO-комментарий в `pyproject.toml` обновлён (теперь на очереди `F811`, `F841`). Sample-прогон `pytest tests/unit/{test_uploads,test_security,test_webdav,test_worker_tasks}.py` — 101 passed.
- **5.4** — аудит дублей: единственное пересечение по имени файла `test_files_bulk.py` (unit — Pydantic-валидация `validate_bulk_names`/`BulkDeleteRequest`, integration — endpoint+DB). Имена тест-функций между `tests/unit/` и `tests/integration/` не пересекаются. Перекрытий требующих чистки не найдено — пункт закрыт.
- **4.3** — установлен `@axe-core/playwright` (frontend dev-deps). Добавлен `./frontend/tests/e2e/a11y.spec.ts` с двумя пилотными тестами, помеченными `@a11y`: страница `/login` и корневой redirect (`/`). Каждый тест прогоняет `AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa'])`, фильтрует violations по `impact in {critical, serious}` и в случае ошибки печатает структурированное сообщение с id/help/количеством узлов. Job `frontend-e2e` в CI запускает все спеки в `tests/e2e/` — новый файл подхватывается автоматически.
- **5.1** — `user_factory`/`news_factory`/`kb_article_factory` в `./backend/tests/conftest.py` переписаны с `SimpleNamespace` на `polyfactory.SQLAlchemyFactory[Model]` (`_UserFactory`/`_NewsFactory`/`_KbArticleFactory`, `__set_relationships__ = False`). Сохранён исторический `_make(**overrides)`-API. Чтобы polyfactory не падал на PG-`TSVECTOR` (`body_tsvector` в `News`/`KbArticle`), `SQLAlchemyFactory.get_type_from_column` пропатчен через `_drop_tsvector_columns` — для TSVECTOR-колонок возвращается `type(None)` (значение `None`, БД сама посчитает tsvector). В `./backend/pyproject.toml` добавлен `polyfactory>=2.18.0`. Полный backend unit+security suite (1785 тестов) зелёный.
- **2.1** (инфраструктура + integration-стабилизация) — заложены рельсы для постепенной миграции mock-heavy unit-тестов на реальную БД, попутно починены integration-тесты под dev-стек.

  Стабилизация integration-сьюта (181 тест зелёный в dev-стеке `docker-compose.yml` + `docker-compose.dev.yml` с `INTEGRATION_DB=true INTEGRATION_REDIS=true`):
  - **asyncio loop-scope**: в `./backend/pyproject.toml` добавлен `asyncio_default_test_loop_scope = "session"` (ранее был только fixture-scope). Без этого session-scoped фикстуры и function-scoped тесты крутились в разных event-loop'ах → каскадные `got Future attached to a different loop` / `another operation in progress`. Это лечит ~95% падений.
  - **meetings booking-conflict (PendingRollbackError)**: `create_booking` / `update_booking` в `./backend/app/services/meetings/bookings_service.py` теперь делают **pre-check через `_get_conflict_details` ДО основной вставки** и поднимают `BookingConflict(details)` при найденном пересечении. Старый паттерн `async with db.begin_nested(): await db.flush(); except IntegrityError: ... _get_conflict_details(db, ...)` оставлен как race-safe fallback, но `_get_conflict_details` после неуспешного flush больше не дёргается (в `join_transaction_mode="create_savepoint"` session-state остаётся в `PendingRollbackError`, и любой `db.execute` падает). В race-кейсе теперь поднимается `BookingConflict([])` — детали уже доступны клиенту через pre-check.
  - Точечные баги тестов: `./backend/tests/integration/test_news_db.py` — Bookmark.url=NOT NULL и двойной `monkeypatch.setattr` для `_NEWS_MEDIA_DIR` (импортируется в `services/news/crud.py` через `from ._helpers import _NEWS_MEDIA_DIR`); `./backend/tests/integration/test_rate_limit_matrix.py` — корректный prefix `/api/v1` (был задублирован) + skip-list для маршрутов, короткозамыкающихся 503/404 до RateLimiter (`/ocs/v2.php`, `/files/folders/*`, `/files/download`, `/files/preview`); `./backend/tests/integration/test_rate_limit_endpoints.py` — `POST → PATCH /users/me/password`; `./backend/tests/integration/test_staff_directory_db.py` — `attributes.office → attributes.city` (соответствует `users_repo.list_offices`); `./backend/tests/integration/test_meetings_series.py` — распаковка `tuple[list[MeetingBooking], BookingDiff]` из `update_series`.

  Инфраструктура: (1) В `./backend/pyproject.toml` зарегистрирован маркер `unit_with_db` (`[tool.pytest.ini_options].markers` + `addinivalue_line` в `./backend/tests/conftest.py`). (2) Фикстуры `real_db_session`/`real_user`/`real_editor`/`real_admin` вынесены из `./backend/tests/integration/conftest.py` в новый модуль `./backend/tests/db_fixtures.py` и реэкспортируются из корневого `./backend/tests/conftest.py` — теперь доступны из `tests/unit/` и `tests/security/` (фикстуры сами вызывают `pytest.skip` без `INTEGRATION_DB=true`, так что обычный unit-прогон остаётся быстрым). Цель — каждый кандидат (`test_kb_*`, `test_news_*`, `test_photos_*`, `test_files_*` — см. ниже) переводится поэтапно через `@pytest.mark.unit_with_db` + замену `MagicMock/AsyncMock` на `real_db_session.execute(...)`. Top-кандидаты по числу моков (для приоритизации): `test_kb_acl.py` (173), `test_kb_articles.py`/`test_files_folders.py` (100), `test_files_ops.py` (82), `test_kb_versions.py` (73), `test_news_service.py`/`test_kb_export_import.py` (71), `test_files_upload.py` (68). Полные suites: backend 1780 unit+security + 181 integration + frontend 1053 — зелёные.
- **2.5** — в `./docs/testing.md` добавлен раздел «Конвенция "one component per file" для frontend smoke-тестов» (правила для нового кода, постепенный план растащить `components-smoke-extra*.spec.ts`). Из `./frontend/tests/unit/components-smoke-extra5.spec.ts` вынесены два блока: `NotFoundPage.vue` → `./frontend/tests/unit/not-found-page.spec.ts`, `TrashPage.vue` → `./frontend/tests/unit/trash-page.spec.ts` (минимально-достаточные `vi.mock`-шапки в каждом файле). На месте старых блоков оставлены хвост-комментарии со ссылкой на новое расположение. Полный vitest-suite (1053 теста, 63 файла) зелёный.

### Спринт 2 (укрепление)

- **1.4** — добавлен `./backend/tests/integration/test_rate_limit_matrix.py`: discovery rate-limited маршрутов через `app.routes` + `route.dependant.dependencies` (ищет `RateLimiter` instances), для каждого endpoint выполняет `times+1` запросов с уникальным IP и ассертит финальный `429`. Включает sanity-check `test_discovery_finds_known_endpoints` для защиты от поломки intro­спекции.
- **1.5** — `authed_client_factory` в `./backend/tests/conftest.py` снабжён предупреждением в docstring о no-op `_fake_db`; создан алиас `security_authed_client_factory` в `./backend/tests/security/conftest.py`. Создан `./backend/tests/fake_db_allowlist.txt` со списком 13 текущих unit-файлов. В `./.github/workflows/ci.yml` добавлен job `fake-db-allowlist`, фейлящий CI при появлении новых тестов вне allowlist (stale-entries — `::notice::`, не фейл).
- **4.1** — создан workflow `./.github/workflows/nightly-security.yml`: cron `37 3 * * *` + `workflow_dispatch`. Поднимает PG + redis + uvicorn, запускает `ghcr.io/zaproxy/zaproxy:stable zap-baseline.py` против `http://localhost:8000` с `security/zap-baseline.conf`, парсит JSON-отчёт (High/Medium/Low/Info) в `$GITHUB_STEP_SUMMARY`, загружает `zap-report/` (30 дней) и фейлит при наличии High-risk alerts.
- **6.4** — в `./backend/tests/integration/test_migrations.py` добавлены фикстура `_at_head`, helper `_all_revisions`, hook `pytest_generate_tests` (читает `ScriptDirectory.walk_revisions` без поднятия БД) и параметризованный `test_migration_revision_round_trip(revision)`: `head → downgrade {rev}-1 → upgrade {rev} → upgrade head` с понятными per-revision test-ids.
- **6.5** — в `./.github/workflows/ci.yml` добавлен job `compose-smoke`: создаёт `base_data/upload_data/system_data/`, генерирует минимальный `.env`, поднимает `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis migrations backend`, smoke-проверяет `/docs`, `/openapi.json`, `/api/v1/users/me` (ожидает 401/403), tear-down на `always()`.
- **1.3** — добавлены `./frontend/tests/e2e/fixtures/run-id.ts` (`E2E_RUN_ID`, `runScoped`, `runScopedEmail`) и `./frontend/tests/e2e/fixtures/api.ts` (`localLogin`, `apiRequest`, `CleanupRegistry` с `trackUser/trackSection/trackArticle/trackPhotoFolder` и LIFO-flush). Спеки `kb-acl.spec.ts`, `photos.spec.ts`, `kb-media.spec.ts` переведены на run-scoped имена и `cleanup.flush()` в `afterAll`.
- **3.2** — в `./frontend/playwright.config.ts` выставлены `fullyParallel: true` и `workers: 4` (CI). Спекам `kb-acl`, `photos`, `kb-media` (зависят от shared `let *Id` между тестами) добавлен `test.describe.configure({ mode: 'serial' })`, чтобы сохранить порядок при включённом параллелизме.

---

## 1. Критичные дефекты (пропускают регрессии в прод)

### 1.1. E2E-тесты не запускаются в CI
- **Где**: `./.github/workflows/ci.yml` содержит только `backend-lint/unit/integration`, `frontend-lint/unit`, `openapi-drift`, `frontend-types-drift`, `shellcheck`. Job `frontend-e2e` отсутствует.
- **Эффект**: 10 Playwright-спеков в `./frontend/tests/e2e/` (auth, kb-acl, kb-media, photos, files-bulk и т.д.) не выполняются ни разу при PR/push.
- **Сложность**: **M**. Нужен compose-стек (PG + Redis + backend + Keycloak-mock + frontend build → nginx). Бюджет ≤10 мин/прогон.
- **План**:
  1. Добавить job `frontend-e2e`, поднимающий backend через docker compose.
  2. Запускать только `chromium` в PR, `firefox`/`webkit`/`mobile` — в nightly.
  3. Артефакт: `playwright-report/` на 14 дней.

### 1.3. E2E реальные данные через продовый API, без фикстур и без teardown
- **Где**: `./frontend/tests/e2e/kb-acl.spec.ts`, `./frontend/tests/e2e/photos.spec.ts`, `./frontend/tests/e2e/kb-media.spec.ts`.
- **Эффект**: при повторном запуске накапливаются сущности → конфликты по уникальным ключам, шум в БД, нестабильность.
- **Сложность**: **M**.
- **План**:
  1. Ввести `tests/e2e/fixtures/` (создание admin/editor/reader через API + удаление в afterEach).
  2. Префиксы имён (`e2e-${runId}-…`) и nightly cleanup-job.

### 1.4. RateLimiter no-op в 100% unit-тестов
- **Где**: `./backend/tests/conftest.py:99-119`. `fakeredis` не поддерживает Lua → `RateLimiter.__call__` подменяется на no-op. Реальный rate-limit покрывает один файл `./backend/tests/integration/test_rate_limit.py`.
- **Эффект**: ошибки в декораторах `Depends(RateLimiter(...))` не ловятся.
- **Сложность**: **M**.
- **План**: параметризованный integration-тест: для каждого ratelimit-эндпоинта проверять, что 429 действительно возникает.

### 1.5. `_fake_db` в `authed_client_factory` возвращает пустые результаты
- **Где**: `./backend/tests/conftest.py:346-367`. Любой `.execute()` отдаёт `scalar_one=0`, `all=[]`, `first=None`.
- **Эффект**: security/unit «видят» 200/204 от хендлеров, которые в реальности упали бы.
- **Сложность**: **L**.
- **План**:
  1. Переименовать в `security_authed_client_factory`, поместить в `tests/security/conftest.py`.
  2. Запретить использование из `tests/unit/` (grep-gate в CI).
  3. Бизнес-сценарии перевести на testcontainers (см. п.2.1).

---

## 2. Архитектурные проблемы

### 2.1. Перекос пирамиды — 2610 `MagicMock/AsyncMock` в unit-тестах
- **Где**: `./backend/tests/unit/`.
- **Эффект**: тесты ломаются при рефакторинге сигнатур, не ловят SQL-ошибки/констрейнты/relationships.
- **Сложность**: **XL**.
- **План**:
  1. Shared testcontainers-фикстура (PG + Redis на сессию, SAVEPOINT на тест) — каркас уже есть в `./backend/tests/integration/conftest.py`.
  2. Прометить `@pytest.mark.unit_with_db` файлы `test_kb_*`, `test_news_*`, `test_photos_*`, `test_files_*` и перенести.
  3. Цель: unit ≤ 600 чистой логики, integration ≥ 1500.

### 2.2. `concurrent_tasks` не воспроизводит multi-worker race
- **Где**: `./backend/tests/conftest.py:425-449` — `asyncio.gather` в одном loop'е.
- **Сложность**: **L**.
- **План**: `concurrent_db_tasks(factory, count)` в `integration/conftest.py` с N отдельных подключений; перевести `test_bookmarks_race.py`, `test_meetings_savepoint.py`.

### 2.4. Низкие coverage-пороги на frontend
- **Где**: `./frontend/vite.config.ts:80-85` — lines 50, branches 35.
- **Сложность**: **M**.
- **План**: поднять до 60/40 сразу, далее поэтапно 70/50, 80/60. ESLint-rule на запрет `it('renders', () => mount(...))` без assert.

### 2.5. Smoke-тесты-плагины (`components-smoke-extra*.spec.ts`)
- **Где**: 5 файлов `./frontend/tests/unit/components-smoke-extra*.spec.ts`, ~50 КБ.
- **Сложность**: **M**.
- **План**: гайдлайн `tests/unit/<feature>/<Component>.spec.ts`; постепенно расселить и удалить.

---

## 3. Стабильность и качество прогона

### 3.2. Playwright `fullyParallel: false`
- **Где**: `./frontend/playwright.config.ts:7`.
- **Сложность**: **M** (зависит от 1.3).
- **План**: после фикстур-cleanup → `fullyParallel: true`, `workers: 4` в CI.

---

## 4. Безопасность и нефункциональные тесты

### 4.1. ZAP-сканер не подключён к CI
- **Где**: `./security/zap-scan.sh`, `./security/zap-baseline.conf` существуют; в `ci.yml` не вызываются.
- **Сложность**: **M**.
- **План**: nightly job `security-zap` + артефакт-отчёт.

### 4.2. Нагрузочные тесты `./load/*.js` не интегрированы
- **Где**: `./load/baseline.js`, `./load/portal-load.js`, `./load/search.js`, `./load/smoke.js`.
- **Сложность**: **L**.
- **План**: weekly k6 smoke в CI (на staging), gate `p95 < 2s` для search.

### 4.3. Нет accessibility-тестов
- **Где**: только esLint `eslint-plugin-vuejs-accessibility`.
- **Сложность**: **M**.
- **План**: `@axe-core/playwright` + e2e-grep `@a11y`.

### 4.4. Нет визуальной регрессии
- **Сложность**: **M–L**.
- **План**: pilot для login, главной, темизации (light/dark/высокий контраст) через `toHaveScreenshot()`.

### 4.5. Нет мутационного тестирования
- **Сложность**: **L**.
- **План**: `mutmut`/`cosmic-ray` для backend (`./backend/app/services/meetings/`, `./backend/app/api/files/`, `./backend/app/core/security.py`); `stryker` для frontend. Цель: mutation score ≥ 60%, только nightly.

---

## 5. Тестовые фикстуры и анти-паттерны

### 5.1. `SimpleNamespace` вместо реальных моделей
- **Где**: `./backend/tests/conftest.py:179-274` — `user_factory`, `news_factory`, `kb_article_factory`.
- **Сложность**: **M**.
- **План**: `polyfactory.SQLAlchemyFactory`, синхронизация с моделями автоматически.

### 5.2. `tests/*` имеет очень широкие per-file-ignores
- **Где**: `./backend/pyproject.toml:115` — `["E501","F401","F811","E402","B017","B018","F841","E741","N806","SIM105","SIM108","SIM117","RUF059"]`.
- **Сложность**: **M**.
- **План**: PR-серия `tests-cleanup-<rule>` — снимать по одному, начиная с `F401`, `F811`, `F841`.

### 5.4. Дубли unit↔integration
- **Где**: `./backend/tests/unit/test_files_bulk.py` + `./backend/tests/integration/test_files_bulk.py`, и т.п.
- **Сложность**: **M**.
- **План**: ревизия — unit только pure-logic; integration — endpoint+DB.

---

## 6. CI и инфраструктура отчётности

### 6.1. Нет PR-комментария с coverage / нет Codecov
- **Где**: `./.github/workflows/ci.yml:52-58, 103-108` — coverage грузится артефактом, но не виден в PR.
- **Сложность**: **S**.
- **План**: `codecov/codecov-action` (требует токен) или `irongut/CodeCoverageSummary` (без токена).

### 6.4. Нет тестов миграций «вниз»
- **Где**: `./backend/tests/integration/test_migrations.py` — только `upgrade head`.
- **Сложность**: **M**.
- **План**: параметризовать по каждой ревизии — upgrade → downgrade → upgrade.

### 6.5. Отсутствие smoke-теста полного стека (compose-up)
- **Сложность**: **M**.
- **План**: `docker compose up -d` + healthchecks + 2-3 curl/playwright-сценария.

---

## 7. Документация и процесс

### 7.1. `./docs/testing.md` и `./docs/tests.generated.md` могут расходиться
- **Где**: `./scripts/list_tests.sh` запускается вручную.
- **Сложность**: **S**.
- **План**: CI-job, регенерирующий `tests.generated.md` и `git diff --quiet` (требует стабильности порядка `pytest --collect-only` / `vitest list`).

---

## 8. Сводная таблица «эффект → сложность → приоритет»

| # | Дефект | Эффект | Сложн. | Приоритет |
|---|---|---|---|---|
| 1.1 | E2E не в CI | КРИТИЧЕСКИЙ | M | **P0** |
| 1.3 | E2E без фикстур/teardown | ВЫСОКИЙ | M | **P1** |
| 1.4 | RateLimiter no-op | ВЫСОКИЙ | M | **P1** |
| 1.5 | `_fake_db` молча отдаёт пустоту | ВЫСОКИЙ | L | **P1** |
| 2.1 | 2610 моков → хрупкость | ВЫСОКИЙ | XL | **P2** (постепенно) |
| 2.2 | concurrent_tasks не multi-process | СРЕДНИЙ | L | **P2** |
| 2.4 | Низкие пороги покрытия frontend | СРЕДНИЙ | M | **P2** |
| 2.5 | Smoke-тесты-плагины | НИЗКИЙ | M | **P3** |
| 3.2 | Playwright не параллельный | СРЕДНИЙ | M | **P2** |
| 4.1 | ZAP не в CI | ВЫСОКИЙ | M | **P1** |
| 4.2 | k6 не в CI | СРЕДНИЙ | L | **P2** |
| 4.3 | Нет a11y-тестов | СРЕДНИЙ | M | **P2** |
| 4.4 | Нет визуальной регрессии | НИЗКИЙ | M-L | **P3** |
| 4.5 | Нет мутационного тестирования | НИЗКИЙ | L | **P3** |
| 5.1 | SimpleNamespace вместо моделей | СРЕДНИЙ | M | **P2** |
| 5.2 | Широкие ruff-ignores в tests | НИЗКИЙ | M | **P3** |
| 5.4 | Дубли unit↔integration | СРЕДНИЙ | M | **P2** |
| 6.1 | Coverage не виден в PR | НИЗКИЙ | S | **P2** |
| 6.4 | Нет тестов downgrade миграций | СРЕДНИЙ | M | **P2** |
| 6.5 | Нет compose-up smoke | СРЕДНИЙ | M | **P2** |
| 7.1 | tests.generated drift | НИЗКИЙ | S | **P3** |

---

## 9. Предлагаемая последовательность работ (3 спринта)

**Спринт 1 (оставшиеся быстрые победы):**
- 6.1 (PR-комментарий с coverage).
- 7.1 (drift `tests.generated.md`).
- 1.1 (e2e в CI, минимальный compose).

**Спринт 2 (укрепление):**
- 1.4 (real-rate-limit matrix integration).
- 1.5 (разделение `_fake_db`).
- 4.1 (ZAP nightly).
- 6.4 (down-миграции).
- 6.5 (compose-smoke).
- 1.3 (e2e-фикстуры + cleanup), затем 3.2 (parallel).

**Спринт 3 (стратегия):**
- 2.1 (поэтапный перенос service-layer в integration).
- 2.2 (multi-process race-фикстура).
- 2.4 + 2.5 (повышение порогов и чистка smoke-тестов).
- 4.2, 4.3 (k6 + a11y).
- 4.4, 4.5 (визуальная регрессия + мутационное).
- 5.1, 5.2, 5.4.
