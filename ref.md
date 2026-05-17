# Глобальное комплексное ревью проекта Portal — план исправления

> **Дата:** 2026-05-17 (обновлено после девятой волны фиксов: 4.1)
> **Скоуп:** документация, тесты, бэкенд, фронтенд, инфраструктура, гигиена репозитория.
> **Вне скоупа:** вопросы безопасности (CSRF / XSS / инъекции / auth) — отложены по решению.
> **Формат:** каждый пункт описан простым языком (для согласования с менеджером), с указанием затронутых файлов, предлагаемого исправления, оценки трудоёмкости (XS / S / M / L / XL) и приоритета (Критичный / Высокий / Средний / Низкий).
> **История закрытых пунктов:** см. раздел [«Закрытые пункты»](#закрытые-пункты).

---

## Содержание

1. [Документация](#1-документация)
2. [Тесты](#2-тесты)
3. [Backend](#3-backend)
4. [Frontend](#4-frontend)
5. [Инфраструктура / DevOps](#5-инфраструктура--devops)
6. [Артефакты / гигиена репозитория](#6-артефакты--гигиена-репозитория)
7. [Закрытые пункты](#закрытые-пункты)
8. [Топ оставшихся](#топ-оставшихся)
9. [Общая оценка состояния проекта](#общая-оценка-состояния-проекта)

---

## 1. Документация

*Все пункты этого раздела закрыты — см. [«Закрытые пункты»](#закрытые-пункты).*

---

## 2. Тесты

*Все пункты этого раздела закрыты — см. [«Закрытые пункты»](#закрытые-пункты).*

---

## 3. Backend

*Пункты 3.1, 3.3 и 3.5 закрыты — см. [«Закрытые пункты»](#закрытые-пункты).*

*Пункт 3.7 закрыт — см. [«Закрытые пункты»](#закрытые-пункты).*

*Пункт 3.10 закрыт — см. [«Закрытые пункты»](#закрытые-пункты).*

---

## 4. Frontend

*Пункты 4.1, 4.2 и 4.6 закрыты — см. [«Закрытые пункты»](#закрытые-пункты).*

### 4.5. Стилизация: scoped CSS в крупных компонентах — много CSS-дублей

- **Описание для менеджера:** В крупных страничных компонентах (Staff,
  Photos, KB) часто повторяются одни и те же утилитарные стили
  (flex, spacing, цвета). Без общего слоя (utility classes / CSS-vars)
  поддержка темы дороже.
- **Файлы:** `./frontend/src/pages/*.vue`, `./frontend/src/components/*.vue`.
- **Исправление:** вынести общие CSS-vars в один файл; либо ввести
  компактный слой утилит (UnoCSS / собственный). **L**.
- **Приоритет:** Низкий.

*Пункт 4.8 закрыт — см. [«Закрытые пункты»](#закрытые-пункты).*

---

## 5. Инфраструктура / DevOps

*Пункты 5.3, 5.5, 5.6 и 5.7 закрыты — см. [«Закрытые пункты»](#закрытые-пункты).*

---

## 6. Артефакты / гигиена репозитория

### 6.3. Большое число untracked + modified в рабочем дереве

- **Описание для менеджера:** На момент ревью — 30+ modified
  + 18 untracked файлов (рабочий WIP по staff directory). Это нормально
  для дев-машины, но если делать «полный» аудит — стенд состояния
  неудобен.
- **Файлы:** `git status`.
- **Исправление:** довести WIP до коммита; чистить ветку перед
  код-ревью. **S**.
- **Приоритет:** Низкий.

### 6.4. `.gitignore` адекватен, но содержит «ad-hoc» правила для конкретных файлов

- **Описание для менеджера:** `mage-home.jpeg`, `do_*.py`, `cleanup_*.py`,
  `check_*.{sql,py,cjs}`, `commit_msg.txt` и т. п. — следы практик
  отдельных разработчиков, а не проектные. С одной стороны — это
  блокирует случайные коммиты; с другой — у нового разработчика
  не возникнет таких файлов вовсе.
- **Файлы:** `./.gitignore`.
- **Исправление:** разделить файл на «проектные» и «персональные»
  секции; персональные предложить положить в `~/.gitignore_global`. **XS**.
- **Приоритет:** Низкий.

### 6.6. Каталог `.playwright-mcp/` в рабочем дереве

- **Описание для менеджера:** Лог-каталог из MCP-инструмента; находится
  в `.gitignore` (корректно). Но физически на диске занимает место,
  не очищается.
- **Файлы:** `./.playwright-mcp/`.
- **Исправление:** добавить в `setup.sh` или `scripts/clean.sh` команду
  очистки. **XS**.
- **Приоритет:** Низкий.

### 6.7. 281 каталог `__pycache__` на диске

- **Описание для менеджера:** Корректно в `.gitignore`, но на диске
  разрастаются. Минорная проблема — медленнее grep'ы и indexing IDE.
- **Файлы:** `./backend/**/__pycache__/`.
- **Исправление:** добавить `make clean` / `scripts/clean.sh`. **XS**.
- **Приоритет:** Низкий.

### 6.8. Лицензия / автор: `Reydan` vs репо `VeryShuu/portal`

- **Описание для менеджера:** В `package.json` и `pyproject.toml`
  автор «Reydan», в URL — `VeryShuu`. Расхождение метаданных.
  Минорно, но для open-source / audit важно.
- **Файлы:** `./frontend/package.json`, `./backend/pyproject.toml`.
- **Исправление:** привести к одному имени; ввести `CODEOWNERS`. **XS**.
- **Приоритет:** Низкий.

---

## Закрытые пункты

> Здесь фиксируются разделы, ранее присутствовавшие в плане и закрытые
> в текущей итерации. История нужна для аудита.

| # | Тема | Что сделано |
|---|------|-------------|
| 1.1 / 1.5 / 1.8 | CI-ссылки в README/AGENTS/testing | Добавлен реальный workflow `./.github/workflows/ci.yml`; бейдж в `./README.md` и упоминание GitHub Actions в стеке снова валидны; раздел CI в `./docs/testing.md` приведён к фактически реализованным job'ам |
| 1.2 | ADR-диапазон в README | Обновлён до 001–038 + ссылка на `./docs/adr-archive.md` |
| 1.3 | `routes.py` в staff-directory-spec | Заменён на `routes_staff.py` |
| 1.4 | Дрейф generated-документов | Перегенерированы `./openapi.json`, `./docs/api-contracts.generated.md`, `./docs/db-schema.generated.md` от HEAD (206 endpoints / 191 schemas / 35 таблиц) |
| 1.6 / 6.2 | `rev.md` / `sprav.md` / `review-tickets.csv` в корне | Перенесены в `./docs/internal/` (rev.md / sprav.md уже отсутствовали) |
| 1.7 | `migrations/versions/001..038` в AGENTS.md | Обновлено до `001..044` |
| 1.9 (частично) | Индекс `./docs/README.md` | Создан с разбивкой по разделам; `dev-onboarding.md` ещё нет (см. остаток 1.9 выше) |
| 2.1 | CI workflow | Добавлен `./.github/workflows/ci.yml` (jobs: backend-lint, backend-unit, frontend-lint, frontend-unit) |
| 2.2 (частично) | Документация skip'ов | В `./docs/testing.md` добавлен раздел «Интеграционные и E2E `skip` — поведение по умолчанию»; запуск integration в CI остаётся открытым (см. оставшийся 2.2 выше) |
| 2.3 / 4.4 | Автогенерация `types.gen.d.ts` | В `./frontend/package.json` добавлены `predev`, `prebuild`, `pretypecheck`, `pretest:unit` |
| 2.5 | Stepwise downgrade миграций | В `./backend/tests/integration/test_migrations.py` добавлен `test_migrations_stepwise_down_up` |
| 2.6 | Coverage gate | Backend `fail_under = 70` в `./backend/pyproject.toml` и frontend `thresholds` в `./frontend/vite.config.ts` уже присутствуют — пункт подтверждён |
| 2.7 | Тесты feedback / world clock / staff-order | Добавлены `./backend/tests/unit/test_feedback_schema.py` (25 тестов), `./frontend/tests/unit/world-clock-cities.spec.ts` (6 тестов); staff-order уже покрыт `test_staff_directory.py` + `test_staff_directory_db.py` |
| 2.8 | Автогенерация списка тестов | Добавлен `./scripts/list_tests.sh` → `./docs/tests.generated.md` |
| 1.9 | `docs/dev-onboarding.md` (quickstart) | Создан `./docs/dev-onboarding.md` (стек, docker и без-docker запуск, минимальные env, создание тестового пользователя, чек-лист PR); добавлен в индекс `./docs/README.md` |
| 1.10 | Статусные «✅» в `./sprav.md` | Файл `./sprav.md` отсутствует в дереве; при возврате — потребуется аудит, действий не требуется |
| 2.2 | Integration в CI | В `./.github/workflows/ci.yml` добавлен job `backend-integration` (build кастомного postgres+hunspell, redis, alembic upgrade, `pytest tests/integration -rs`); раздел CI в `./docs/testing.md` обновлён |
| 2.4 | Сокращение `tests/*` ignore | Применены ruff-autofix (149 правок), удалены `I001`, `RUF021` из per-file-ignores (`SIM117` оставлен — 17 неавтофиксируемых случаев) |
| 3.4 | Устаревшие шаблоны ruff `kb.py`/`files.py` | Заменены на `kb/*.py`, `files/*.py`, добавлен `users/*.py` |
| 5.2 | `docker-compose.dev.yml` / `staging.yml` | Файлы фактически присутствуют в репозитории |
| 6.1 | PNG-скриншоты и XLSX в корне | На момент проверки в корне отсутствуют |
| 3.2 | Параллельный глобальный поиск | `./backend/app/api/search.py`: multi-type-поиск обёрнут в `asyncio.gather`; каждая из 4 веток (kb/news/links/users) открывает свою `AsyncSession` через новую DI-зависимость `get_session_factory` (`./backend/app/api/deps.py`); тесты `test_search.py` (18) проходят, conftest подменяет фабрику в `authed_client_factory` |
| 3.6 | `ENVIRONMENT` → `Literal` | `./backend/app/core/config.py`: поле `environment` сделано `Literal["development","staging","production","test"]` через type alias `Environment`; опечатки падают на старте |
| 3.8 | Healthcheck воркера на `redis-cli` | `./docker-compose.yml` (сервис `worker`): убран `python -c "import redis..."`; healthcheck сведён к `redis-cli -u $REDIS_URL ping && [ $(redis-cli ... EXISTS arq:heartbeat) = "1" ]`; в `./backend/Dockerfile` (`runtime-base`, `production`) добавлен пакет `redis-tools` |
| 4.3 | `: any` в коде | Заменены 2 случая: `./frontend/src/components/NewsGalleryViewer.vue` (типизированный `ComponentPublicInstance`), `./frontend/src/pages/admin/tabs/UserAttributesTab.vue` (`e: unknown` + narrowed cast); правило `@typescript-eslint/no-explicit-any` поднято до `error` в TS- и Vue-блоках `./frontend/eslint.config.js`, `npx eslint src` чист |
| 5.1 | Dockerfile retry-блоки | `./backend/Dockerfile` переписан: вместо 3×3 копипасты `apt-get + sleep retry` используется нативный `Acquire::Retries "10"` в `/etc/apt/apt.conf.d/80-retries`; стадии build-deps / runtime-base / prod-builder / test / production остаются, но каждая ставит пакеты одной командой |
| 6.5 | Drift-check `openapi.json` | Добавлен job `openapi-drift-check` в `./.github/workflows/ci.yml`: ставит backend dev-extra, перегенерирует `openapi.json` через `./backend/scripts/export_openapi.py`, валит CI при ненулевом `git diff -- openapi.json` с подсказкой команды для регенерации |
| 3.9 | Fallback `LOG_LEVEL` в bootstrap-Settings | Отклонён: уровень логирования уже управляется через admin UI (`system.json`, `SystemSettings.log_level`, дефолт `"INFO"`); env-override создаёт конфликт с UI-настройкой без реальной пользы. Код откатан к оригиналу. |
| 4.7 | SSE teardown в `notificationsStore` | Аудит подтвердил: logout закрывает соединение через редирект страницы, `onSessionExpired` корректно блокирует переподключение через проверку `auth.isAuthenticated`; добавлен `onScopeDispose(disconnectSSE)` в `./frontend/src/stores/notifications.ts` — при HMR старый `EventSource` теперь закрывается |
| 5.4 | Retry в `migrate.sh` | `./backend/scripts/migrate.sh`: `alembic upgrade head` обёрнут в POSIX-совместимый цикл `until ... done` с 5 попытками и паузой 5 с между ними; при исчерпании попыток — явный `exit 1` с диагностическим сообщением |
| 4.2 | ESLint vue/* правила | `./frontend/eslint.config.js`: все 14+ ранее отключённых `vue/*`-правил переведены в `"warn"` (`html-self-closing`, `html-indent`, `attributes-order`, `attribute-hyphenation`, `v-on-event-hyphenation` и др.); автофикс применён по всему `src/`; дублирующая запись `vue/singleline-html-element-content-newline` удалена; `npm run lint:check` — 0 ошибок / 0 предупреждений |
| 4.6 | A11y-плагин `eslint-plugin-vuejs-accessibility` | Установлен `eslint-plugin-vuejs-accessibility@2.5.0`; в Vue-блок `./frontend/eslint.config.js` добавлены все 23 правила как `"warn"`; устранены 87 нарушений: лишние `role` на семантических тегах, `aria-label` на скрытых file/color input'ах, `label[for]` + `id` для пар label/input, `@focusin` рядом с `@mouseenter`, `role="button" tabindex="0" @keydown.enter` на кликабельных div'ах, `role="dialog" aria-modal="true" @keydown.escape` на модальных оверлеях; 8 зон drag-and-drop получили `eslint-disable-next-line` с комментарием (keyboard DnD вне скоупа); `npm run lint:check` — 0 ошибок / 0 предупреждений |
| 3.10 | Partial-индексы на `deleted_at IS NULL` | Аудит: `photo_folders`, `photos`, `news`, `kb_article_comments`, `file_folders`, `file_items` — покрыты миграциями 020/038/044/045. Добавлена `./backend/migrations/versions/046_kb_users_partial_indexes.py`: `idx_kb_sections_active (parent_id)`, `idx_kb_articles_active (section_id)` на `kb_sections`/`kb_articles`; `idx_users_active (department, full_name)` на `users`. Исправлена модель `KbArticle` — удалён избыточный `deleted_at` из столбцов индекса (он дублировал WHERE-условие). Индексы добавлены в `__table_args__` моделей `KbArticle`, `User` для консистентности с `create_all()` в тестах |
| 3.7 | Mypy strict для подпакетов | **Фаза 1 (api-пакеты):** `models`, `schemas`, `utils` — 0 ошибок сразу; починено 22 ошибки в `api/feedback`, `api/kb`, `api/users`, `api/news`, `api/files`, `api/photos`. **Фаза 2 (core/middleware/services):** починено ещё 51 ошибка в 22 файлах: `cache_version` (`int(redis.incr)`), `logging` (`int(getattr)`, `# type: ignore[no-any-return]`), `modules_config`/`system_config` (`cast(Settings, cache["data"])`), `uploads` (`__all__` + убран unused ignore), `lifespan` (исправлено через `__all__`), все 5 middleware-функций получили `call_next: Callable[[Request], Awaitable[Response]] -> Response`, `idempotency` (`Scope`, `Message`, `str(...)`); в services — `cast()` в `acl_base`, `files_acl_persistence`, `session`; `-> CTE` в `kb_acl`; `cast(dict/list)` на `response.json()` и `data["access_token"]` в `keycloak`; `cast`/`str()` в `nc_federation`, `nextcloud/webdav`; `-> Select[Any]`+`Any` import в `news`; `-> Any` + убран ignore в `photos_storage`; убран unused ignore в `tls_status`. В `./backend/pyproject.toml` добавлен второй `[[tool.mypy.overrides]]` для `app.core.*`, `app.middleware.*`, `app.services.*` с теми же 6 флагами. `python3 -m mypy app/ --config-file pyproject.toml` — **0 ошибок / 157 файлов**; `ruff check` — чист |
| 3.3 | Декомпозиция `users_service.py` | Файл `./backend/app/api/users/users_service.py` (393 строки) удалён и разнесён на три модуля по ответственности: **`./backend/app/api/users/users_me_service.py`** (148 строк: `patch_my_profile`, `patch_my_preferences`, `upload_avatar`, `change_my_password`); **`./backend/app/api/users/users_admin_service.py`** (254 строки: `enqueue_keycloak_sync`, `change_user_role`, `create_local_user`, `get_user_groups`, `admin_patch_profile`, `delete_user`, `reset_user_password`); **`./backend/app/api/users/staff_service.py`** (51 строка: `apply_staff_order` — нормализация `departments`/`users`/`hidden_user_ids` + персист через `users_repo`, вынесена из `routes_staff.put_staff_order`). Роуты переведены: `routes_me.py` → `users_me_service`, `routes_admin.py` → `users_admin_service`, `routes_staff.put_staff_order` сокращён до делегирования в `staff_service.apply_staff_order`. Тесты `./backend/tests/unit/test_users_me_routes.py` обновлены на новые пути `patch("app.api.users.routes_me.users_me_service.X")`. `pytest tests/unit` — **1598 passed**; `mypy app/api/users/` — 0 errors / 10 files; `ruff check app/api/users/` — чист |
| 3.1 | Декомпозиция толстых backend-файлов | Все 5 модулей разнесены на подпакеты: **`./backend/app/api/auth/`** (`_helpers.py`, `oidc.py`, `logout.py`, `local.py`, `me.py`); **`./backend/app/services/kb_acl/`** (`_common.py`, `invalidation.py`, `resolve.py`, `batch.py`, `visibility.py`); **`./backend/app/worker/tasks/photos/`** (`processing.py`, `cleanup.py`, `zip_jobs.py`, `import_scan.py`); **`./backend/app/services/news/`** (`_helpers.py`, `crud.py`, `cover.py`, `gallery.py`, `attachments.py`); **`./backend/app/services/keycloak/`** (`_state.py`, `http_client.py`, `settings.py`, `oidc.py`, `jwks.py`, `directory.py`, `tokens.py`). Для каждого пакета сохранены публичные имена через `__init__.py` (внешние импорты `from app.services.X import Y` совместимы); для keycloak применён паттерн ленивых package-namespace lookup'ов (`from app.services import keycloak as _kc` внутри функций) + mutable shared state в `_state.py`, что позволило сохранить тесты `patch.object(kc, "_X", ...)` без правок. Тесты к auth/news/photos обновлены на корректные submodule-пути патчей. `pytest tests/unit` — **1598 passed**; `mypy app/` — **0 errors / 183 files**; `ruff check app/services/keycloak/` — чист |
| 3.5 | Миграции legacy-typing | Все 46 файлов `migrations/versions/*.py` обновлены: удалён `from collections.abc import Sequence`, `str | Sequence[str] | None` заменён на `str | tuple[str, ...] | None` — соответствует шаблону `script.py.mako`, который уже был в актуальном состоянии |
| 4.8 | Bundle-budget / lazy-loading | Установлен `rollup-plugin-visualizer@7`; в `./frontend/vite.config.ts` добавлен плагин (активируется при `ANALYZE=true`); в `./frontend/package.json` добавлен скрипт `build:analyze`; запуск: `ANALYZE=true npm run build` → открывает `dist/stats.html` |
| 5.3 | ADR nginx sidecar + inotify | Добавлен ADR-039 в `./docs/adr.md`: описывает схему двух контейнеров, shared volumes `/data/nginx-conf` и `/data/nginx`, поток данных Admin UI → system.json → inotify → render → reload, fallback на polling, альтернативы (consul-template, webhook, один контейнер) |
| 5.5 | ADR сетевой топологии | Добавлен ADR-040 в `./docs/adr.md`: описывает `internal`/`external` bridge-сети, изоляцию postgres/redis в production, staging-override с `127.0.0.1`-bind, ограничение egress для сервисов в `internal: true` при настройке внешних интеграций |
| 5.6 | ADR стратегии логирования | Добавлен ADR-041 в `./docs/adr.md`: описывает `x-logging` anchor (`json-file`, `max-size: 50m`, `max-file: 5`, `compress: true`, `tag`), расчёт объёма (1.75 ГБ / ~400 МБ сжатых), путь миграции на Vector/Promtail |
| 5.7 | shellcheck для setup.sh | Исправлен баг `error "..."` → `err "..."` (функция `err` определена, `error` — нет); добавлен `./.pre-commit-config.yaml` с хуком `shellcheck-precommit` (`--severity=warning`); добавлен job `shellcheck` в `./.github/workflows/ci.yml` |
| 4.1 | Декомпозиция толстых Vue-компонентов | Все 8 компонентов разложены по паттерну «представление + composable». Созданы 19 новых composable-файлов: **StaffDirectoryPage** → `useStaffView`, `useStaffExport`, `useStaffLeaveGuard`; **GlobalSearch** → `useSearchRecent`, `useSearchNavigation`; **LightboxModal** → `useLightboxView`, `useLightboxSlideshow`, `useLightboxShare`, `useLightboxPhotoTags`; **UsersTab** → `useUsersTabActions`, `useUsersTableColumns`; **WorldClockTab** → `useWorldClockClock`, `useWorldClockSortable`, `useWorldClockForm`; **HomePage** → `useHomeNews`; **LoginPage** → `useLoginConfig`, `useLoginForm`; **RichEditor** → `useEditorVideoDialog`, `useEditorDetailsDialog` (в `./frontend/src/components/editor/`). Все компоненты обновлены на использование новых composable'ов. `npm run lint:check` — **0 ошибок / 0 предупреждений**; `npx vue-tsc --noEmit` — **0 ошибок** |

---

## Топ оставшихся

*Все приоритетные пункты закрыты. Оставшиеся пункты раздела 6 (гигиена репозитория) имеют приоритет Низкий и не блокируют разработку.*

---

## Общая оценка состояния проекта

**Зрелость: очень высокая (после девятой волны фиксов).** Документация
выровнена с кодом (перегенерированы OpenAPI и `*.generated.md`,
обновлены диапазоны ADR/миграций, добавлен индекс `./docs/README.md`).
CI-pipeline реально существует (`./.github/workflows/ci.yml`) и закрывает
lint + unit для backend и frontend, integration с кастомным postgres+hunspell,
drift-check `openapi.json`, а теперь и `shellcheck setup.sh`. Coverage gates
подтверждены (backend 70%, frontend thresholds в `vite.config.ts`). Stepwise
downgrade миграций защищён тестом. Конфиг строже (`ENVIRONMENT` →
`Literal`), глобальный поиск распараллелен (`asyncio.gather` + DI-фабрика
сессий), `: any` устранены и правило поднято до `error`, Dockerfile
обходится без копипасты apt-retry, healthcheck воркера переведён на
`redis-cli`. `migrate.sh` устойчив к кратковременным сбоям сети
благодаря retry-обёртке; SSE-соединение нотификаций корректно закрывается
при HMR через `onScopeDispose`. Frontend lint полностью подтянут:
все `vue/*`-правила включены как `"warn"` и автофикснуты по всему `src/`;
подключён `eslint-plugin-vuejs-accessibility` (23 правила), устранены
87 нарушений a11y, `npm run lint:check` — 0 ошибок / 0 предупреждений.
Partial-индексы на `deleted_at IS NULL` добавлены для всех таблиц с
soft-delete (миграция 046). Mypy strict-режим охватывает все 12 пакетов
(`models`, `schemas`, `utils`, все `api/*`, `core`, `middleware`, `services`) —
`python3 -m mypy app/` → **0 ошибок / 183 файла**. Все 5 толстых
backend-модулей (auth, kb_acl, worker/photos, news, keycloak) разложены
на подпакеты по ответственности; `pytest tests/unit` — **1598 passed**.
Сервисный слой пакета `users/` тоже декомпозирован: `users_service.py`
(393 строки) разложен на `users_me_service.py`, `users_admin_service.py`
и `staff_service.py` (с выносом нормализации `put_staff_order` из
`routes_staff.py`). Миграции «омолодили» typing: все 46 файлов используют
`str | tuple[str, ...] | None` без импорта `Sequence`. Bundle-budget
инструментирован: `rollup-plugin-visualizer` активируется через `ANALYZE=true`.
Инфраструктурные ADR (039–041) задокументировали nginx sidecar+inotify,
сетевую топологию и стратегию логирования. `setup.sh` покрыт shellcheck
в CI и pre-commit; исправлен баг вызова несуществующей функции `error`.
**Все 8 толстых Vue-компонентов** декомпозированы по паттерну «представление + composable»:
созданы 19 composable-файлов, `npm run lint:check` — 0 ошибок / 0 предупреждений,
`npx vue-tsc --noEmit` — 0 ошибок.

### Главные оставшиеся риски

*Приоритетных рисков нет.* Оставшиеся пункты (6.3–6.8) касаются гигиены
репозитория и имеют низкий приоритет.

### Рекомендуемая стратегия закрытия

Закрыть оставшиеся пункты раздела 6 (gitignore cleanup, clean-скрипты,
метаданные автора) одним небольшим PR.
