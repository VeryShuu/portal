# Refactoring Plan / План рефакторинга

> Живой документ. Обновляется по ходу анализа: отмечаем выполненное, дописываем находки,
> корректируем приоритеты. Это план **анализа**, по которому выбираем что и как рефакторить.
> Сам рефакторинг — отдельными коммитами `refactor(<module>): ...` после завершения анализа цели.

**Статус:** этап 4 завершён для `photos_storage.py` (анализ + backlog PS-1..PS-5). Реализация ещё НЕ начата.
**Последнее обновление:** 2026-06-01

---

## 0. Принципы (не меняем)

- Рефакторинг **не меняет поведение**: контракт API (`openapi.json`), UI и тесты остаются прежними.
- Любой шаг начинается и заканчивается **зелёным baseline** (см. этап 2).
- Один вид изменения = один коммит/PR. Не смешивать с багфиксами и фичами.
- Трогаем то, что покрыто тестами. Нет покрытия — сначала характеризующий тест, потом правка.
- Приоритет целей = **размер × частота изменений** (где реальная боль).

---

## 1. Подготовка отправной точки

- [x] Закоммитить/застешить текущие незакоммиченные изменения (`docs/*`, `AGENTS.md`), чтобы дерево было чистым.
- [x] Создать ветку для рефакторинг-итерации. → `refactor/iteration-1`
- [x] Зафиксировать этот файл (`ref.md`) в репозитории. → коммит `bd7d9e6`

---

## 2. Baseline качества (заморозка «как есть зелёное»)

Прогнано 2026-06-01 на ветке `refactor/iteration-1`. **Эталон, к которому возвращаемся после каждого шага.**

> Важно: CI (`/.github/workflows/ci.yml`) гейтит **`mypy app`** (а не весь репозиторий) и
> `ruff format --check`. Ниже отмечено, что является CI-гейтом.

### Backend
- [x] `ruff check .` → **PASS** (All checks passed, 486 файлов).
- [x] `ruff format --check .` → **PASS** (486 файлов уже отформатированы). *(CI-гейт)*
- [x] `mypy app` → **PASS** (0 ошибок, 258 файлов). *(CI-гейт)*
- [x] `mypy .` → **FAIL: 104 ошибки в `tests/`** (app — чисто). **Не гейтится CI.** → кандидат в backlog (этап 6).
- [x] `pytest tests/unit tests/security --cov=app` → **PASS: 2365 тестов**, coverage **76.17%** (гейт 75%).
- [ ] `pytest tests/integration` (postgres+redis, testcontainers) → **не запускалось** (heavy; Docker доступен). Прогнать отдельно при необходимости.

### Frontend
- [x] `npm run lint:check` (eslint) → **PASS**.
- [x] `npm run typecheck` (vue-tsc) → **PASS**.
- [x] `npm run test:coverage` (vitest) → **PASS: 75 файлов / 1144 теста**, coverage **70.15%** (есть гейт в CI).

> Вывод: baseline **зелёный** по всем CI-гейтам. Единственная не-гейтовая трещина — типизация тестов backend
> (`mypy .`: 104 ошибки в `tests/*`), это управляемый техдолг, не блокер.

---

## 3. Сбор метрик для приоритизации

### 3.1 Размер (топ крупных файлов) — предварительно

Backend (по байтам, из `find`):
- `app/services/photos_storage.py` (~18KB)
- `app/api/search.py` (~17KB)
- `app/api/kb/export_import.py` (~17KB)
- `app/api/branding.py` (~17KB)
- `app/services/photos_trash.py` (~16KB)

Frontend:
- `components/RichEditor.vue` (~22KB) ← лидер
- `pages/admin/tabs/SystemTab.vue` (~14KB)
- `pages/admin/tabs/KeycloakTab.vue` (~14KB)
- `components/meetings/RoomGrid.vue` (~13KB)
- `pages/StaffDirectoryPage.vue` (~13KB)
- `components/GlobalSearch.vue` (~12KB)

### 3.2 Частота изменений (churn) — собрано 2026-06-01

История = 158 коммитов за ~1 месяц (02.05–01.06.2026), поэтому churn считаем по всей истории.
Команда (LOC×churn по существующим файлам) прогнана через python-скрипт.

> Замечание: ряд churn-лидеров в `git log` уже **не существует** (`api/auth.py`, `api/news.py`,
> `api/users.py`, `api/system_settings.py`, `core/system_config.py`) — их ранее разбили на пакеты.
> В матрицу берём только существующие файлы.

### 3.3 Матрица «LOC × churn × coverage»

Метрика приоритизации: **score = LOC × число коммитов**. Coverage — из baseline (этап 2).
Правило риска: высокий score + **высокое** покрытие = безопасная цель; высокий score + **низкое**
покрытие = ценно, но сначала характеризующие тесты.

**Backend (`app/*.py`), топ:**
| Файл | LOC | churn | score | coverage | риск рефакторинга |
|------|----:|------:|------:|---------:|-------------------|
| `app/api/kb/export_import.py` | 492 | 9 | 4428 | 75% | средний |
| `app/services/photos_storage.py` | 445 | 9 | 4005 | **98%** | **низкий** ✅ |
| `app/api/links.py` | 428 | 9 | 3852 | 81% | низкий |
| `app/api/notifications.py` | 374 | 10 | 3740 | 75% | средний |
| `app/api/branding.py` | 465 | 8 | 3720 | 76% | средний |
| `app/api/photos/folders.py` | 287 | 11 | 3157 | **22%** | **высокий** ⚠ нужны тесты |
| `app/api/search.py` | 448 | 7 | 3136 | **53%** | **высокий** ⚠ нужны тесты |
| `app/services/files_acl.py` | 387 | 7 | 2709 | 95% | низкий |

**Frontend (`src/*.vue|.ts`), топ:**
| Файл | LOC | churn | score | coverage (line/func) | риск |
|------|----:|------:|------:|---------------------:|------|
| `components/RichEditor.vue` | 830 | 12 | 9960 | 93% / **11%** | средний (функции слабо покрыты) |
| `pages/NewsFormPage.vue` | 427 | **21** | 8967 | 72% / 9% | средний |
| `pages/KbListPage.vue` | 426 | 17 | 7242 | 80% / 5% | средний |
| `pages/HomePage.vue` | 474 | 13 | 6162 | 80% / 0% | средний |
| `pages/NewsDetailPage.vue` | 436 | 13 | 5668 | — | средний |
| `pages/photos/PhotosIndexPage.vue` | 416 | 13 | 5408 | — | средний |
| `pages/FilesPage.vue` | 334 | 16 | 5344 | 80% / 0% | средний |
| `pages/admin/tabs/KeycloakTab.vue` | 419 | 11 | 4609 | — | средний |

### 3.4 Рекомендация по первой цели

- **Backend, безопасный старт:** `app/services/photos_storage.py` — 2-й по score и **98% покрытия**.
  Можно дробить уверенно, сетка ловит регрессии. (`export_import.py` выше по score, но 75% — чуть рискованнее.)
- **Frontend, главный кандидат:** `components/RichEditor.vue` — абсолютный лидер по score (830 LOC).
  Линий покрыто 93%, но **функций лишь 11%** → перед дроблением добавить тесты на функции/команды редактора.
  Альтернатива с максимальным churn — `pages/NewsFormPage.vue` (21 правка): извлечь логику формы в composable.

---

## 4. Качественный анализ кандидатов

Что ищем: длинные функции, дублирование, смешение слоёв/ответственностей, магические числа,
мёртвый код, mutable global state, нетипизированное API, конфиг мимо `app.core.config`.

---

### 4.1 `app/services/photos_storage.py` (446 строк) — ВЫБРАННАЯ ЦЕЛЬ

**Карта связей (важно для безопасного дробления):**
- Импортируется как namespace: `from app.services import photos_storage` → вызовы `photos_storage.X`
  в **12 модулях** (`api/photos/*`, `services/photos_trash_files.py`, `worker/tasks/photos/*`).
- Внешне используемые символы: `folder_fs_path`(×9), `IMPORT_ROOT`, `sanitize_filename`,
  `rename_folder_dir`, `is_allowed_ext`, `ZIPS_ROOT`, `THUMB_SIZES`, `THUMBS_ROOT`, `ORIGINALS_ROOT`,
  `thumb_path`, `thumb_avif_path`, `sanitize_folder_name`, `generate_thumbnails`, `extract_exif`,
  `delete_photo_files`, `compute_blurhash`.
- ⚠ Внешне используется **приватный** `_get_thumb_semaphore` — в `worker/tasks/photos/processing.py:98`.
  → при дроблении обязателен ре-экспорт (это де-факто публичный API).
- Покрытие 98% (этап 2), непокрыты лишь строки 78, 260-261, 403-404, 412-413 (edge-ветки).

**Смешение ответственностей (god-module, 5 разных причин для изменения):**
1. Санитизация и резолв путей/имён (чистые, без PIL): `sanitize_filename`, `is_allowed_ext`,
   `sanitize_folder_name`, `folder_fs_path`, `rename_folder_dir`, `thumb_path`, `thumb_avif_path`.
2. I/O оригиналов: `save_original`, `delete_photo_files`.
3. Генерация thumbnails (тяжёлый PIL + конкурентность): `generate_thumbnails`,
   `generate_thumbnails_safe`, `_open_image`, `_get_thumb_semaphore`.
4. Метаданные изображения: `compute_blurhash`, `extract_exif`.
5. Конфиг/константы: roots, `THUMB_SIZES`, env-driven флаги.

**Запахи:**
- **Module-level mutable global state**: `_THUMB_GEN_LOCKS: dict` + `_THUMB_GEN_SEMAPHORE` (lazy-singleton
  через `global`). Конкурентность намешана в один файл с чистыми функциями → тяжело тестировать изолированно.
- **Длинная функция** `generate_thumbnails` (~65 строк): ручной жизненный цикл bitmap'ов
  (img/transposed/converted/scaled/intermediates + `gc.collect()`). Сложно, но **намеренно** ради OOM-контроля
  (cgroup 2GB). Кандидаты на извлечение: `_cascade_resize`, `_encode_thumb` — **с сохранением** логики close()/gc.
- **Конфиг мимо `app.core.config`**: `GENERATE_AVIF`, `AVIF_MIN_SIZE`, `_THUMB_GEN_CONCURRENCY`,
  `_MAX_IMAGE_PIXELS` читаются из `os.environ` на уровне модуля — расходится с паттерном Settings проекта.
- **Разрозненные lazy-import'ы** PIL/heif/blurhash/avif в 4 функциях. Частично оправдано (опц. зависимости,
  cold-start воркера), но повторяющийся `from PIL import Image` можно централизовать.
- **Широкие `except Exception`** (extract_exif, compute_blurhash, _open_image/heif) — в основном намеренная
  устойчивость; не трогаем без нужды, только зафиксировать.
- **Устаревший комментарий**: `THUMB_SIZES = (200, 400, 600, 1000, 1600)  # widget, grid, lightbox` —
  3 названия на 5 размеров (мелочь, поправить заодно).
- **Слабая типизация**: `_open_image`/`generate_thumbnails` → `Any` (PIL не типизирован, приемлемо);
  `extract_exif` → голый `dict` вместо `dict[str, Any]`.

**Стратегия дробления (безопасная, поведение-сохраняющая):**
Превратить модуль в пакет `app/services/photos_storage/` с `__init__.py`, который **ре-экспортирует все
публичные символы** (включая `_get_thumb_semaphore`). Тогда все 12 импортеров `photos_storage.X` продолжают
работать **без единого изменения**. Предлагаемое разбиение:
- `paths.py` — roots/константы путей + sanitize_*/folder_fs_path/rename_folder_dir/thumb_path/thumb_avif_path.
- `originals.py` — save_original, delete_photo_files.
- `thumbnails.py` — generate_thumbnails(+safe), _open_image, locks/semaphore, thumb-константы.
- `metadata.py` — compute_blurhash, extract_exif.
- `config.py` (опционально) — env-driven настройки в одном месте.
- `__init__.py` — `from .paths import *` … + явный `__all__`, ре-экспорт `_get_thumb_semaphore`.

**Очерёдность (каждый пункт — отдельный коммит, baseline зелёный до/после):**
1. (опц.) дописать тесты на непокрытые edge-строки — покрытие уже 98%, скорее не нужно.
2. Механический перенос кода в пакет + ре-экспорт в `__init__` (поведение 1:1, диффы — только перемещение).
3. Внутренние улучшения по одному: извлечь helper'ы в generate_thumbnails; централизовать PIL-import;
   поправить устаревший комментарий; (отдельно, осторожно) env → `app.core.config`.

> Риск: низкий на шаге 2 (чистое перемещение под защитой 98% покрытия). Шаг 3 — точечный, по одному запаху.

---

## 5. Backlog рефакторинга (формируется из этапа 4)

Каждая задача — атомарная, поведение-сохраняющая, с критерием готовности «baseline зелёный».

**Эпик: декомпозиция `photos_storage.py` (из 4.1)**
- [ ] PS-1: превратить модуль в пакет `app/services/photos_storage/` (paths/originals/thumbnails/metadata),
  `__init__.py` ре-экспортирует все публичные символы + `_get_thumb_semaphore`. Перенос кода 1:1.
  *Критерий: 12 импортеров не меняются; ruff/mypy app/pytest зелёные.*
- [ ] PS-2: извлечь helper'ы из `generate_thumbnails` (`_cascade_resize`, `_encode_thumb`) с сохранением
  логики close()/gc. *Отдельный коммит.*
- [ ] PS-3: централизовать lazy-import PIL внутри пакета thumbnails.
- [ ] PS-4: поправить устаревший комментарий у `THUMB_SIZES`; уточнить тип `extract_exif → dict[str, Any]`.
- [ ] PS-5 (осторожно, потенциальное изменение поведения): env-флаги → `app.core.config` Settings.

---

## 6. Сквозные (cross-cutting) задачи — кандидаты

- [ ] Расширять strict-зону `mypy` (добавлять модули в `disallow_untyped_defs`).
- [ ] Сокращать `ruff` `per-file-ignores` (закрыть `TODO(REVIEW-5.2)`: `F811`, `F841`).
- [ ] Типизация тестов backend: `mypy .` даёт 104 ошибки в `tests/*` (SimpleNamespace вместо моделей, conftest). Не гейт CI, но стоит постепенно чистить.
- [ ] Унифицировать обработку ошибок API (`utils/parseApiError.ts`, `mapMeetingsError.ts`).
- [ ] Выделять повторяющуюся логику из «толстых» `.vue` в `composables/`.

---

## Журнал решений

| Дата | Решение / изменение плана |
|------|---------------------------|
| 2026-06-01 | Создан план. Подход: непрерывный точечный рефакторинг, не переписывание. |
| 2026-06-01 | Этап 2: baseline зелёный по всем CI-гейтам (ruff/format/mypy app/pytest 76.17%/eslint/vue-tsc/vitest 70.15%). Найдено: `mypy .` → 104 ошибки в `tests/` (не гейт) — в backlog. Integration-тесты не гоняли (heavy). |
| 2026-06-01 | Этап 3: собрана матрица LOC×churn×coverage. Рекомендованные первые цели: backend — `photos_storage.py` (score 4005, cov 98%, низкий риск); frontend — `RichEditor.vue` (score 9960, но func-cov 11% — нужны тесты) либо `NewsFormPage.vue` (max churn 21). |
| 2026-06-01 | Этап 4: разобран `photos_storage.py`. Вывод — god-module (5 ответственностей). Безопасный путь: модуль→пакет с ре-экспортом в `__init__` (12 импортеров не трогаем; `_get_thumb_semaphore` де-факто публичный). Backlog PS-1..PS-5. Реализацию НЕ начинали. |
