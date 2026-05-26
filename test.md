# План устранения недочётов системы тестирования

> Ревью от мая 2026. База: backend (~1700 unit+security, ~250 integration), frontend (~982 vitest, 10 e2e), CI: `./.github/workflows/ci.yml`.
> Шкала сложности: **S** — часы, **M** — 1–3 дня, **L** — неделя, **XL** — спринт+.

---

## 1. Критичные дефекты (пропускают регрессии в прод)

### 1.1. E2E-тесты не запускаются в CI
- **Где**: `./.github/workflows/ci.yml` содержит только `backend-lint/unit/integration`, `frontend-lint/unit` и `openapi-drift`. Job `frontend-e2e` отсутствует.
- **Эффект**: 10 Playwright-спеков в `./frontend/tests/e2e/` (auth, kb-acl, kb-media, photos, files-bulk и т.д.) не выполняются ни разу при PR/push → они уже могут быть «битые», и никто не узнает.
- **Сложность**: **M**. Нужен compose-стек (PG + Redis + backend + Keycloak-mock + frontend dev/build). Сложность — поднять и удержать в разумном бюджете времени (≤10 мин/прогон). Часть тестов требует реальной авторизации (см. п.1.3).
- **План**:
  1. Добавить job `frontend-e2e`, поднимающий backend через docker compose (минимальный стек: pg, redis, backend, frontend build → nginx).
  2. Запускать только chromium-проект в PR, mobile — в nightly.
  3. Артефакт: `playwright-report/` на 14 дней.

### 1.2. E2E-тесты с «зелёными при любом исходе» проверками
- **Где**:
  - `./frontend/tests/e2e/smoke.spec.ts:14` — `expect(url).toBeTruthy()` (всегда true для любой строки).
  - `./frontend/tests/e2e/smoke.spec.ts:21` — `expect(await skipLink.count()).toBeGreaterThanOrEqual(0)` (всегда true).
  - `./frontend/tests/e2e/auth.spec.ts:5-9` — `response` от `page.goto('/')` не проверяется, а условие на URL допускает любой login-редирект.
- **Эффект**: иллюзия покрытия. Тест может «зеленеть» даже если страница вернула 500.
- **Сложность**: **S**. Переписать ассерты на конкретные тексты/URL/код ответа.
- **План**: ввести правило ESLint/playwright `no-conditional-or-pass-through-asserts`, привести smoke к виду `expect(response?.status()).toBeLessThan(400)`, проверить наличие конкретного элемента (заголовок логина, skip-link visible и т.п.).

### 1.3. E2E реальные данные через продовый API, без фикстур и без teardown
- **Где**: `./frontend/tests/e2e/kb-acl.spec.ts`, `./frontend/tests/e2e/photos.spec.ts`, `./frontend/tests/e2e/kb-media.spec.ts` создают разделы/статьи/папки/share-токены через API и не чистят их.
- **Эффект**: при повторном запуске накапливаются сущности → конфликты по уникальным ключам, шум в БД, нестабильность.
- **Сложность**: **M**. Нужны helper-фикстуры (создать → yield → удалить), либо одноразовая БД на job.
- **План**:
  1. Ввести `tests/e2e/fixtures/` (создание admin/editor/reader через API + удаление в afterEach).
  2. Стандартизировать префиксы имён (`e2e-${runId}-…`) и nightly cleanup-job.

### 1.4. RateLimiter no-op в 100% unit-тестов
- **Где**: `./backend/tests/conftest.py:99-119`. `fakeredis` не поддерживает Lua, поэтому `RateLimiter.__call__` подменяется на `async return None`. Реальный rate-limit покрывает один файл `./backend/tests/integration/test_rate_limit.py`.
- **Эффект**: ошибки в декораторах `Depends(RateLimiter(...))` (неверные параметры, отключение лимита на endpoint) не ловятся.
- **Сложность**: **M**. Решения: (a) использовать настоящий Redis в unit-тестах через testcontainers (медленнее), либо (b) написать pure-Python адаптер `RateLimiter` для тестов, либо (c) автоматически прогонять матрицу «эндпоинт ↔ ожидаемый лимит» в integration.
- **План**: (c) — добавить параметризированный integration-тест, который для каждого ratelimit-эндпоинта проверяет, что 429 действительно возникает.

### 1.5. `_fake_db` в `authed_client_factory` возвращает пустые результаты
- **Где**: `./backend/tests/conftest.py:346-367`. Любой `.execute()` отдаёт `scalar_one=0`, `all=[]`, `first=None`.
- **Эффект**: security-тесты и часть unit-тестов «видят» 200/204 от хендлеров, которые в реальности упали бы на NotFound/ValidationError. Покрытие достигается, корректность — нет.
- **Сложность**: **L**. Разнести: для security-тестов оставить заглушку (проверяем только authz/HTTP), для остальных запретить (`pytest.fail("use real DB or testcontainers")`).
- **План**:
  1. Переименовать в `security_authed_client_factory`, поместить в `tests/security/conftest.py`.
  2. Запретить использование из `tests/unit/` (lint-правило / grep-gate в CI).
  3. Бизнес-сценарии перевести на testcontainers (см. п.2.1).

---

## 2. Архитектурные проблемы

### 2.1. Перекос пирамиды — 2610 `MagicMock/AsyncMock` в unit-тестах
- **Где**: `./backend/tests/unit/` — почти каждый сервис вызывается с моканной `AsyncSession`, моканным Redis, моканным httpx.
- **Эффект**: тесты ломаются при любом рефакторинге сигнатур (хрупкость), но не ловят SQL-ошибки, ошибки констрейнтов, неверные ORM-relationships.
- **Сложность**: **XL**. Радикально — перевести «service-layer» в integration (testcontainers, ~15–30 мин CI). Постепенно — выделить «pure-logic» (валидаторы, парсеры, рендереры) в `tests/unit/`, всё с БД — в `tests/integration/`.
- **План**:
  1. Подготовить shared testcontainers-фикстуру (один PG + Redis на сессию, SAVEPOINT на тест) — уже частично готово в `./backend/tests/integration/conftest.py:62`.
  2. Прометить (`@pytest.mark.unit_with_db`) ~20 самых хрупких тестовых файлов (`test_kb_*`, `test_news_*`, `test_photos_*`, `test_files_*`) и перенести.
  3. Цель: unit ≤ 600 тестов чистой логики, integration ≥ 1500.

### 2.2. `concurrent_tasks` не воспроизводит multi-worker race
- **Где**: `./backend/tests/conftest.py:425-449` — `asyncio.gather` в одном event-loop.
- **Эффект**: реальная race-condition между uvicorn/arq-воркерами (разные процессы → разные транзакции, реальный SELECT FOR UPDATE и т.п.) не воспроизводится. Тесты на идемпотентность и race в bookmarks/bookings могут пропускать настоящие баги.
- **Сложность**: **L**. Нужны интеграционные тесты с реальной БД и параллельными подключениями (через `asyncpg` напрямую или multiprocess).
- **План**: добавить `concurrent_db_tasks(factory, count)` в `integration/conftest.py`, который открывает N отдельных соединений и atomically запускает корутины; перенести race-сценарии (`test_bookmarks_race.py`, `test_meetings_savepoint.py`) на него.

### 2.3. Покрытие `--no-cov` для integration
- **Где**: `./.github/workflows/ci.yml:175` — `pytest tests/integration -rs --no-cov`.
- **Эффект**: код, покрытый только integration-тестами (миграции, реальные сервисы), не учитывается в coverage-gate 70% → стимул писать «псевдо-unit» с моками.
- **Сложность**: **S**. Включить `--cov-append`, мерджить coverage.xml.
- **План**: `coverage combine` между unit/security и integration; единый отчёт; gate поднять до 80% после стабилизации.

### 2.4. Низкие coverage-пороги на frontend
- **Где**: `./frontend/vite.config.ts:80-85` — lines 50, branches 35.
- **Эффект**: половина кода может быть не покрыта. Многие компоненты покрыты «smoke»-тестами (`components-smoke-extra*.spec.ts`), которые рендерят и не проверяют поведение.
- **Сложность**: **M**. Поднять пороги поэтапно (60/40 → 70/50 → 80/60), параллельно усилить spec'и (взаимодействия, эмиты).
- **План**: поднять до 60/40 сразу (текущее реальное покрытие ~70/50), добавить ESLint-rule запрет на `it('renders', () => mount(...))` без последующих assert.

### 2.5. Smoke-тесты-плагины (`components-smoke-extra*.spec.ts`) растут как снежный ком
- **Где**: 5 файлов `./frontend/tests/unit/components-smoke-extra*.spec.ts`, суммарно ~50 КБ. Тесты в основном `mount(...)` + `wrapper.exists()`.
- **Эффект**: дают цифры покрытия, не дают защиты от регрессий; ломаются на любом изменении DOM-структуры.
- **Сложность**: **M**. Заменить на целевые тесты по компонентам (минимум: пропсы, события, slot-ы).
- **План**: ввести гайдлайн `tests/unit/<feature>/<Component>.spec.ts`, постепенно расселить тесты из «extra*» по доменам и удалить мусор.

---

## 3. Стабильность и качество прогона

### 3.1. Predicted deprecation-долг `event_loop` fixture
- **Где**: `./backend/tests/conftest.py:48-53` (session-scoped) и `./backend/tests/integration/conftest.py:18-27` (function-scoped override). В `pyproject.toml` `filterwarnings = ["error::DeprecationWarning", "ignore:.*event_loop fixture.*:DeprecationWarning"]`.
- **Эффект**: pytest-asyncio 0.24+ удаляет кастомные `event_loop`; обновление зависимостей упадёт.
- **Сложность**: **S**. Перейти на `asyncio_default_fixture_loop_scope = "session"` (pytest-asyncio ≥ 0.23) и убрать оба override'а.
- **План**: одноразовый PR; параллельно — поднять минимальную версию pytest-asyncio в `pyproject.toml`.

### 3.2. Playwright `fullyParallel: false`
- **Где**: `./frontend/playwright.config.ts:7`.
- **Эффект**: e2e идут последовательно → медленнее, плохо масштабируется.
- **Сложность**: **M**. Зависит от устранения 1.3 (изоляция данных).
- **План**: после фикстур-cleanup включить `fullyParallel: true`, `workers: 4` в CI.

### 3.3. `webServer` в Playwright поднимает `npm run dev`
- **Где**: `./frontend/playwright.config.ts:38-44` — `command: 'npm run dev'`.
- **Эффект**: тест против dev-сборки (HMR, source-maps, ленивые ошибки) ≠ продовая сборка; плюс медленный cold start.
- **Сложность**: **S–M**. Использовать `npm run build && vite preview` (или nginx-контейнер) в CI; dev оставить локально.
- **План**: env-переключатель `E2E_MODE=preview|dev`.

### 3.4. Нет retry/flake-детектора на backend
- **Где**: `./backend/pyproject.toml` — установлен `pytest-randomly`, но не `pytest-rerunfailures`. У integration в CI нет `--reruns`.
- **Эффект**: интермиттентные сетевые/контейнерные сбои валят job целиком; нет статистики flakes.
- **Сложность**: **S**. Добавить `pytest-rerunfailures` и `--reruns 2 --reruns-delay 1` только для integration; либо публиковать flake-отчёт через GitHub Annotations.
- **План**: лучше — отдельный nightly job, который запускает test-suite 5 раз и репортит нестабильные.

### 3.5. Браузерная матрица Playwright — только Chromium + iPhone-mobile
- **Где**: `./frontend/playwright.config.ts:26-36`. Нет firefox/webkit.
- **Эффект**: Safari/Firefox-специфичные баги (CSP, IndexedDB, focus, форматирование дат) проскальзывают.
- **Сложность**: **S** (добавить проекты) + **M** (стабилизировать). 
- **План**: добавить projects `webkit` и `firefox`, гонять nightly-only; PR — только chromium.

---

## 4. Безопасность и нефункциональные тесты

### 4.1. ZAP-сканер не подключён к CI
- **Где**: `./security/zap-scan.sh` и `./security/zap-baseline.conf` существуют, но в `ci.yml` не вызываются.
- **Эффект**: security headers, CSP, mixed content, CORS не верифицируются автоматически.
- **Сложность**: **M**. Поднять backend+frontend, запустить ZAP baseline; обработать false-positives через baseline-конфиг.
- **План**: nightly job `security-zap` + загрузка отчёта в артефакты.

### 4.2. Нагрузочные тесты `./load/*.js` не интегрированы
- **Где**: `./load/baseline.js`, `./load/portal-load.js`, `./load/search.js`, `./load/smoke.js`. CI их не запускает.
- **Эффект**: нет порога производительности; деградации p95 не ловятся.
- **Сложность**: **L**. Нужно стабильное окружение (preview-env / dedicated VM) и хранилище метрик (Grafana Cloud / k6 Cloud / artifact CSV).
- **План**: weekly k6 smoke в CI (на staging), gate `p95 < 2s` для search.

### 4.3. Нет accessibility-тестов
- **Где**: только esLint `eslint-plugin-vuejs-accessibility`. Runtime-проверок через `axe-playwright`/`axe-core` нет.
- **Эффект**: WCAG-регрессии незаметны.
- **Сложность**: **M**. Добавить `@axe-core/playwright`, прогнать на ключевых страницах (login, dashboard, KB, photos, meetings).
- **План**: e2e-проект `a11y` с `npx playwright test --grep @a11y`.

### 4.4. Нет визуальной регрессии
- **Где**: отсутствует. У Playwright есть `toHaveScreenshot()`.
- **Сложность**: **M–L**. Хранение baseline'ов, толерантность к шрифтам/анти-алиасингу.
- **План**: pilot для login, главной, темизации (light/dark/высокий контраст).

### 4.5. Нет мутационного тестирования
- **Где**: отсутствует.
- **Эффект**: 70% line-coverage ≠ защита от регрессий.
- **Сложность**: **L**. `mutmut`/`cosmic-ray` для backend, `stryker` для frontend; долгие прогоны → только nightly + только для критичных модулей (`./backend/app/services/meetings/`, `./backend/app/api/files/`, `./backend/app/core/security.py`).
- **План**: PoC на одном модуле, цель — mutation score ≥ 60%.

---

## 5. Тестовые фикстуры и анти-паттерны

### 5.1. `SimpleNamespace` вместо реальных моделей
- **Где**: `./backend/tests/conftest.py:179-274` — фабрики `user_factory`, `news_factory`, `kb_article_factory` возвращают `SimpleNamespace`.
- **Эффект**: поля могут расходиться с SQLAlchemy-моделью (хранилище ничего не валидирует). Например, `created_at` тип, отсутствие relationship-полей.
- **Сложность**: **M**. Перевести на реальные ORM-классы с `transient=True` + `factory_boy`/`polyfactory`.
- **План**: внедрить `polyfactory.SQLAlchemyFactory`, синхронизировать с моделями автоматически.

### 5.2. `tests/*` имеет очень широкие per-file-ignores
- **Где**: `./backend/pyproject.toml:115` — `["E501","F401","F811","E402","B017","B018","F841","E741","N806","SIM105","SIM108","SIM117","RUF059"]`. TODO REVIEW-2.4 висит давно.
- **Эффект**: «мёртвый код» в тестах (`F401/F841`), скрытые баги через `except: pass` (`B017`), путаница имён.
- **Сложность**: **M**. Постепенно убирать по одному правилу: сначала `F401`, `F811`, `F841` — самое простое.
- **План**: PR-серия `tests-cleanup-<rule>`, в каждом снимать одно правило.

### 5.3. `pytest.importorskip` как «работа в обход»
- **Где**: интеграционные файлы `test_account_linking.py`, `test_files_bulk.py`, `test_api_smoke.py` начинают с `pytest.importorskip("fastapi")`/`httpx`.
- **Эффект**: тест может «потеряться» на машине без зависимостей и казаться зелёным.
- **Сложность**: **S**. Зависимости и так в `[project.optional-dependencies].dev` → `importorskip` бессмысленен. Убрать.

### 5.4. Дубль файлов unit↔integration
- **Где**: `./backend/tests/unit/test_files_bulk.py` + `./backend/tests/integration/test_files_bulk.py`, `./backend/tests/unit/test_news_routes.py` + `./backend/tests/integration/test_news_api.py` и т.п.
- **Эффект**: непонятно, что должно покрываться где; риск дрейфа поведения.
- **Сложность**: **M**. Ревизия: unit — только pure-logic; интеграция — endpoint+DB.

---

## 6. CI и инфраструктура отчётности

### 6.1. Нет PR-комментария с coverage / нет Codecov
- **Где**: `./.github/workflows/ci.yml:52-58, 103-108` — артефакт грузится, но в PR не виден.
- **Сложность**: **S**. Добавить `codecov/codecov-action` или `irongut/CodeCoverageSummary`.

### 6.2. shellcheck только для `setup.sh`
- **Где**: `./.github/workflows/ci.yml:219-227`. `./scripts/*.sh`, `./security/zap-scan.sh`, `./nginx/entrypoint-config.sh`, `./nginx/render-config.sh` не проверяются.
- **Сложность**: **S**. Расширить glob: `shellcheck $(git ls-files '*.sh')`.

### 6.3. OpenAPI drift только для backend
- **Где**: `./.github/workflows/ci.yml:186-217`. Проверка совпадения `openapi.json`. Но frontend `src/api/types.gen.d.ts` генерируется из неё в `pretest:unit`/`prebuild` — drift в коммите остаётся незамеченным.
- **Сложность**: **S**. Добавить job, регенерирующий `types.gen.d.ts` и проверяющий `git diff --quiet`.

### 6.4. Нет тестов миграций «вниз»
- **Где**: `./backend/tests/integration/test_migrations.py` тестирует `upgrade head`. Реверсивность (`downgrade`) не проверяется.
- **Сложность**: **M**. Параметризовать по каждой ревизии: upgrade → downgrade → upgrade.

### 6.5. Отсутствие smoke-теста полного стека (compose-up)
- **Сложность**: **M**. Поднять `docker compose up -d`, дождаться healthchecks, прогнать 2-3 curl/playwright-сценария.

---

## 7. Документация и процесс

### 7.1. `./docs/testing.md` и `./docs/tests.generated.md` могут расходиться
- **Где**: `./scripts/list_tests.sh` генерирует список, но запускается вручную; нет CI-гейта.
- **Сложность**: **S**. Добавить job, регенерирующий `tests.generated.md` и `git diff --quiet`.

### 7.2. Нет «test ownership» (CODEOWNERS для `tests/`)
- **Где**: `./.github/CODEOWNERS` (12 байт) почти пустой.
- **Сложность**: **S**.

---

## 8. Сводная таблица «эффект → сложность → приоритет»

| # | Дефект | Эффект | Сложн. | Приоритет |
|---|---|---|---|---|
| 1.1 | E2E не в CI | КРИТИЧЕСКИЙ | M | **P0** |
| 1.2 | Тесты-«всегда зелёные» | ВЫСОКИЙ | S | **P0** |
| 1.4 | RateLimiter no-op | ВЫСОКИЙ | M | **P1** |
| 1.5 | `_fake_db` молча отдаёт пустоту | ВЫСОКИЙ | L | **P1** |
| 2.1 | 2610 моков → хрупкость | ВЫСОКИЙ | XL | **P2** (постепенно) |
| 2.3 | integration без cov-merge | СРЕДНИЙ | S | **P1** |
| 2.4 | Низкие пороги покрытия frontend | СРЕДНИЙ | M | **P2** |
| 3.1 | `event_loop` deprecation | СРЕДНИЙ | S | **P1** |
| 3.3 | Playwright против dev-сборки | СРЕДНИЙ | S | **P1** |
| 3.5 | Только chromium | СРЕДНИЙ | S | **P2** |
| 4.1 | ZAP не в CI | ВЫСОКИЙ | M | **P1** |
| 4.2 | k6 не в CI | СРЕДНИЙ | L | **P2** |
| 4.3 | Нет a11y-тестов | СРЕДНИЙ | M | **P2** |
| 4.5 | Нет мутационного тестирования | НИЗКИЙ (long-term) | L | **P3** |
| 5.2 | Широкие ruff-ignores в tests | НИЗКИЙ | M | **P3** |
| 6.1 | Coverage не виден в PR | НИЗКИЙ | S | **P2** |
| 6.3 | Нет drift-проверки types.gen | СРЕДНИЙ | S | **P1** |
| 6.4 | Нет тестов downgrade миграций | СРЕДНИЙ | M | **P2** |

---

## 9. Предлагаемая последовательность работ (3 спринта)

**Спринт 1 (быстрые победы, P0/P1-S):**
- 1.2, 3.1, 3.3, 6.1, 6.2, 6.3, 7.1 — все «S».
- 1.1 (e2e в CI, минимальный compose).
- 2.3 (объединение coverage).

**Спринт 2 (укрепление):**
- 1.4 (real-rate-limit matrix integration).
- 1.5 (разделение `_fake_db`).
- 4.1 (ZAP nightly).
- 6.4 (down-миграции).
- 3.5 (webkit/firefox nightly).
- 1.3 (e2e-фикстуры + cleanup).

**Спринт 3 (стратегия):**
- 2.1 (поэтапный перенос service-layer в integration).
- 2.2 (multi-process race-фикстура).
- 2.4 + 2.5 (повышение порогов и чистка smoke-тестов).
- 4.2, 4.3 (k6 + a11y).
- 5.1 (polyfactory).
