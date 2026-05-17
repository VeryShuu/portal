# Глобальное комплексное ревью проекта Portal — план исправления

> **Дата:** 2026-05-17 (обновлено после четвёртой волны фиксов: 4.2 / 4.6)
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

### 3.1. Толстые файлы — кандидаты на декомпозицию

- **Описание для менеджера:** Самые крупные модули: `auth.py` (609 строк),
  `kb_acl.py` (556), `worker/tasks/photos.py` (524), `news.py` (521),
  `keycloak.py` (504). Эти файлы трудно сопровождать, в них смешана
  разная ответственность, тесты к ним длинные.
- **Файлы:** `./backend/app/api/auth.py`, `./backend/app/services/kb_acl.py`,
  `./backend/app/worker/tasks/photos.py`, `./backend/app/services/news.py`,
  `./backend/app/services/keycloak.py`.
- **Исправление:** разнести по аналогии с уже выполненной декомпозицией
  `kb/`, `files/`, `news/`, `users/` — на подпакеты. **L**.
- **Приоритет:** Средний.

### 3.3. Сервис `users_service.py` остался «толстым» после декомпозиции

- **Описание для менеджера:** При выносе пользователей в пакет `users/`
  сами роуты разделены (routes_me/admin/staff), но бизнес-логика осталась
  в одном файле `users_service.py` (~393 строк). Это сводит на нет
  половину пользы от декомпозиции.
- **Файлы:** `./backend/app/api/users/users_service.py`, `./backend/app/api/users/`.
- **Исправление:** разделить на `users_me_service.py`, `users_admin_service.py`,
  `staff_service.py`. **M**.
- **Приоритет:** Низкий.

### 3.5. Миграции содержат legacy-typing (`Union`, `Sequence`) — отключено в lint

- **Описание для менеджера:** Шаблон Alembic-миграций до сих пор импортирует
  `Union, Sequence` из `typing`, а в линтере для `migrations/*` отключены
  сразу UP007, UP035 и др. Шаблон следовало обновить на современный
  синтаксис (`X | None`).
- **Файлы:** `./backend/migrations/versions/*.py`, `./backend/pyproject.toml`
  (секция `[tool.ruff.lint.per-file-ignores]` → `migrations/*`).
- **Исправление:** обновить шаблон `alembic/script.py.mako` и постепенно
  «омолодить» уже существующие файлы. **M**.
- **Приоритет:** Низкий.

### 3.7. Mypy включён в нестрогом режиме

- **Описание для менеджера:** `strict = false`, `ignore_missing_imports = true`.
  Это снижает реальную пользу типизации. Современная практика —
  `strict = true` хотя бы для `app/services/` и `app/api/`.
- **Файлы:** `./backend/pyproject.toml` (секция `[tool.mypy]`).
- **Исправление:** поэтапно включать `strict_optional`,
  `disallow_untyped_defs` для подпакетов. **L**.
- **Приоритет:** Средний.

### 3.10. Отсутствие явных индексов на полях soft-delete (`deleted_at`)

- **Описание для менеджера:** Многие модели имеют `deleted_at`, и почти
  все запросы фильтруют `deleted_at IS NULL`. Без partial-индекса на
  `deleted_at IS NULL` (как сделано в миграции 044 для staff)
  фильтрация будет проходить full scan.
- **Файлы:** `./backend/app/models/`, `./backend/migrations/versions/`.
- **Исправление:** аудит частых запросов; добавить partial-индексы
  там, где сканируется много данных. **M**.
- **Приоритет:** Средний.

---

## 4. Frontend

### 4.1. Толстые Vue-компоненты

- **Описание для менеджера:** `StaffDirectoryPage.vue` (532),
  `GlobalSearch.vue` (494), `LightboxModal.vue` (470), `UsersTab.vue` (431),
  `WorldClockTab.vue` (424), `HomePage.vue` (422), `LoginPage.vue` (432),
  `RichEditor.vue` (391) — это «всё-в-одном» компоненты. Поддержка дорогая,
  любая правка рискует затронуть весь компонент.
- **Файлы:** `./frontend/src/pages/StaffDirectoryPage.vue`,
  `./frontend/src/components/GlobalSearch.vue`,
  `./frontend/src/components/photos/LightboxModal.vue`,
  `./frontend/src/pages/admin/tabs/UsersTab.vue`,
  `./frontend/src/pages/admin/tabs/WorldClockTab.vue`,
  `./frontend/src/pages/HomePage.vue`, `./frontend/src/pages/LoginPage.vue`,
  `./frontend/src/components/RichEditor.vue`.
- **Исправление:** выделить «представление + composable» (UI и логика);
  часть `useStaff*.ts` уже есть — продолжить. **L**.
- **Приоритет:** Средний.

*Пункты 4.2 и 4.6 закрыты — см. [«Закрытые пункты»](#закрытые-пункты).*

### 4.5. Стилизация: scoped CSS в крупных компонентах — много CSS-дублей

- **Описание для менеджера:** В крупных страничных компонентах (Staff,
  Photos, KB) часто повторяются одни и те же утилитарные стили
  (flex, spacing, цвета). Без общего слоя (utility classes / CSS-vars)
  поддержка темы дороже.
- **Файлы:** `./frontend/src/pages/*.vue`, `./frontend/src/components/*.vue`.
- **Исправление:** вынести общие CSS-vars в один файл; либо ввести
  компактный слой утилит (UnoCSS / собственный). **L**.
- **Приоритет:** Низкий.

### 4.8. Отсутствует bundle-budget / lazy-loading проверка

- **Описание для менеджера:** Vite билдит chunks, но не контролируется
  размер главного bundle. Толстые редкоиспользуемые компоненты
  (RichEditor, LightboxModal, GlobalSearch) могут попасть в основной
  чанк и замедлить первую загрузку.
- **Файлы:** `./frontend/vite.config.ts`.
- **Исправление:** ввести `rollup-plugin-visualizer` или
  `vite-bundle-analyzer`; код-сплитить tab-компоненты. **M**.
- **Приоритет:** Низкий.

---

## 5. Инфраструктура / DevOps

### 5.3. Сложная схема nginx-config (sidecar + inotify)

- **Описание для менеджера:** Nginx-конфиг рендерится отдельным
  контейнером `nginx-config`, основной `nginx` следит за файлом
  `/data/nginx/reload-trigger` через inotify. Эта схема нестандартна,
  не задокументирована (только косвенно в `AGENTS.md`), при отладке
  сложно понять, кто кому пишет файл.
- **Файлы:** `./docker-compose.yml` (сервисы `nginx` / `nginx-config`),
  `./nginx/Dockerfile.config`, `./nginx/templates/`.
- **Исправление:** написать архитектурную заметку (диаграмма ADR),
  либо упростить (например, заменить inotify на webhook). **M**.
- **Приоритет:** Средний.

### 5.5. `internal` сеть `internal: true` — postgres недоступен снаружи

- **Описание для менеджера:** Это правильно для prod (БД не торчит
  наружу), но в staging-override постгрес открывается на 5432.
  Нужно убедиться, что в production-`.env` нет случайной утечки.
  Замечание о согласованности.
- **Файлы:** `./docker-compose.yml` (секция `networks`),
  `./docker-compose.staging.yml`.
- **Исправление:** ADR на тему сетевой топологии. **S**.
- **Приоритет:** Низкий.

### 5.6. Логирование `json-file` с `max-size: 50m`, `max-file: 5` — итого 250 МБ на сервис

- **Описание для менеджера:** При 7 сервисах = ~1.75 ГБ места только
  на логи. Без ротации в централизованный сборщик логи будут жить на
  диске стенда и могут переполнить его.
- **Файлы:** `./docker-compose.yml` (x-logging anchor).
- **Исправление:** подключить vector / fluentbit / promtail; либо
  снизить лимит. **S**.
- **Приоритет:** Низкий.

### 5.7. `setup.sh` — нет линта

- **Описание для менеджера:** Файл `setup.sh` — критический (создаёт
  `.env`, спрашивает пароли). Не покрыт shellcheck'ом, не в CI.
- **Файлы:** `./setup.sh`.
- **Исправление:** запустить `shellcheck`, починить замечания;
  добавить в pre-commit. **S**.
- **Приоритет:** Низкий.

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

---

## Топ оставшихся

| # | Раздел | Пункт | Приоритет |
|---|---|---|---|
| 1 | Backend 3.1 | Декомпозиция толстых файлов (auth/kb_acl/photos/news/keycloak) | Средний |
| 2 | Backend 3.7 | Постепенный `mypy --strict` для подпакетов | Средний |
| 3 | Backend 3.10 | Partial-индексы на `deleted_at IS NULL` | Средний |
| 4 | Frontend 4.1 | Декомпозиция толстых Vue-компонентов | Средний |
| 5 | Infra 5.3 | ADR / упрощение nginx-config (sidecar + inotify) | Средний |
| 6 | Backend 3.3 | Декомпозиция `users_service.py` | Низкий |
| 7 | Backend 3.5 | Шаблон alembic + миграции на современный typing | Низкий |
| 8 | Infra 5.5 / 5.6 / 5.7 | ADR сетевой топологии, ротация логов, `shellcheck` `setup.sh` | Низкий |

---

## Общая оценка состояния проекта

**Зрелость: высокая (после четвёртой волны фиксов).** Документация
выровнена с кодом (перегенерированы OpenAPI и `*.generated.md`,
обновлены диапазоны ADR/миграций, добавлен индекс `./docs/README.md`).
CI-pipeline реально существует (`./.github/workflows/ci.yml`) и закрывает
lint + unit для backend и frontend, integration с кастомным postgres+hunspell,
а также drift-check `openapi.json`. Coverage gates подтверждены
(backend 70%, frontend thresholds в `vite.config.ts`). Stepwise
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

### Главные оставшиеся риски

1. **Толстые файлы / компоненты** (backend `auth.py`, `kb_acl.py`,
   `worker/tasks/photos.py`; frontend `StaffDirectoryPage.vue`,
   `GlobalSearch.vue`, `LightboxModal.vue`) — техдолг сопровождения,
   фоновая работа на спринт (3.1, 4.1).
2. **Mypy в нестрогом режиме** — типизация не даёт максимума пользы
   (3.7); partial-индексы на `deleted_at` тоже частично отсутствуют (3.10).

### Рекомендуемая стратегия закрытия

Фоном по 1–2 декомпозиции в спринт (backend 3.1, frontend 4.1) и
поэтапное ужесточение типизации (3.7). Отдельный мини-спринт
на гигиену миграций и шаблон alembic (3.5, 3.10).
