# Refactoring Plan / План рефакторинга

> Живой документ. Обновляется по ходу анализа: отмечаем выполненное, дописываем находки,
> корректируем приоритеты. Это план **анализа**, по которому выбираем что и как рефакторить.
> Сам рефакторинг — отдельными коммитами `refactor(<module>): ...` после завершения анализа цели.

**Статус:** ПЛАН ГОТОВ. Этап 4 завершён для всех 13 целей матрицы (photos_storage, RichEditor, NewsFormPage,
search, export_import, links, notifications, branding, KbListPage, FilesPage, HomePage, folders, files_acl).
Backlog PS/RE/NF/SE/EI/LI/NO/BR/KL/FP/HP/FO/AC сформирован. Есть roadmap (раздел 7) и DoD шага (раздел 8).
Реализация НАЧАТА: волна 0 эпик `PS` **завершён** (PS-1..PS-4: `photos_storage.py` → пакет; helper'ы
`_cascade_resize`/`_encode_thumb`; централизован lazy-import PIL `_import_pil`; комментарий `THUMB_SIZES` +
тип `extract_exif → dict[str, Any]`). PS-5 (env→Settings) отложен как рискованный. Волна 1 **закрыта**:
**SE-0** (`search` 53%→**98%**) и **FO-0** (`folders` 22%→**100%**) — характеризующие тесты добавлены,
структурные шаги SE-1..3/FO-1 разблокированы. **Волна 2 (тест-блокеры) закрыта параллельно суб-агентами:**
**EI-0** (export_import +15 тестов), **LI-0** (`links` 81%→**100%**), **NO-0** (`notifications` 75%→**100%**),
**BR-0** (`branding` 76%→**97%**) — разблокированы структурные EI-1..3/LI-1..4/NO-1..3/BR-1..4.
**Структурные эпики (Волна 2):** **EI-1..3** завершён (export_import → services kb_export/kb_import/kb_markdown);
**LI-1..4** завершён (`links` → services links_query/links_crud/links_sso/link_icon; хендлеры тонкие, модули 100%).
Baseline зелёный: 2514 тестов, cov **78.46%**, `mypy app` PASS (268), ruff check/format PASS.
**Последнее обновление:** 2026-06-02

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

### 4.2 `frontend/src/components/RichEditor.vue` (830 строк) — frontend-лидер по score

**Контекст:** часть декомпозиции уже сделана — логика диалогов вынесена в `src/components/editor/`
(`useEditorLinkDialog.ts`, `useEditorDetailsDialog.ts`, `useEditorImageUpload.ts`). Остаётся «толстый» SFC:
editor-shell + bubble-menu + 4 модалки + большой `<style scoped>` (строки 535-830).

**Контракт (не ломать):** props `modelValue: string`, `placeholder?`, `uploadEndpoint?`; emit только
`update:modelValue`. Потребители: `pages/NewsFormPage.vue`, `components/KbArticleSuggestTab.vue`,
`components/kb/article-form/ArticleContentSection.vue`. Критично: двусторонний `v-model`-sync без update-loop
(onUpdate + watch), image upload/paste/drop, link-dialog (URL/KB-табы), fullscreen/focus + Escape.

**Запахи:** смешение представления и оркестрации в одном SFC; большой template (link+KB UI); magic-значения
(`duration:100`, `max-width:480/900px`, `z-index:9000`, hex-цвета); тяжёлый style-блок; дублирование
form-полей в image/link диалогах.

**Декомпозиция (по нарастанию риска):** вынести fullscreen/focus state и `shouldShowBubbleMenu`/`handleDblClick`
в composables → под-компонент `RichEditorBubbleMenu` → по одной модалке (video/details → image → link+kb) →
последним трогать CSS (сначала перенос без смены селекторов).

> ⚠ **Риск высокий из-за метрики покрытия:** строки 93%, но **функции 11%** — line-coverage набран
> mount/smoke-тестами, ветви/хендлеры не проверены. **Перед дроблением обязательны характеризующие тесты:**
> v-model sync в обе стороны (без loop), открытие/закрытие+submit/cancel каждой модалки, ветки link-dialog
> (internal/external, newTab/nofollow, KB keyboard-nav), media-входы (file/drop/paste, поведение без
> `uploadEndpoint`), fullscreen/focus/Escape, smoke у трёх потребителей.

---

### 4.3 `frontend/src/pages/NewsFormPage.vue` (427 строк) — max churn (21)

**Ответственности:** режимы create/edit (по `route.params.id`), модель формы новости, валидация+сабмит
(`saveAsDraft`/`publish` с мутациями и навигацией), автосейв черновика (interval 30с), оркестрация медиа-блоков
(обложка/галерея/вложения/опрос).

**Контракт (не ломать):** после create нужен `created.id` (иначе ломаются edit-route и медиа-панели);
`newsId` — источник правды для дочерних панелей; navigation: draft→`router.replace('/news/:id/edit')`,
publish→`router.push('/news')`.

**Запахи:** длинный `<script setup>` (orchestration + домен + форматирование дат + сеть); дублирование
submit-путей (`saveAsDraft`/`publish` почти идентичны); magic-константы (`30_000`, локали `ru-RU/en-US`,
fallback `50`); непоследовательная обработка ошибок (где `parseApiError`, где silent `catch {}`).

**Декомпозиция (паттерн проекта — `pages/composables/useArticleFormState.ts`):** вынести `useNewsFormState`
(модель+мапперы+edit-init+date-адаптеры+validate+submit+autosave) и `useNewsFormOptions` (status/category
options); под-компоненты `NewsFormMainFields`, `NewsFormSettingsCard`. В странице — только wiring.

> Покрытие 72% строк / 9% функций → **до дробления** характеризующие тесты: create/edit init, три submit-пути
> (draft-create→replace, draft-edit→update, publish→push), fail-валидации (мутации не зовутся), autosave-контракт
> (только edit+draft, шлёт только `{title,body}`, не падает на исключении), передача `newsId` в панели.

---

### 4.4 `backend/app/api/search.py` (448 строк) — ⚠ покрытие 53%

**Ответственности:** `GET /search` по 4 сущностям (article/news/link/user) через FTS (`plainto_tsquery`,
`ts_rank`, `ts_headline`) и `pg_trgm`/`ILIKE`; multi-type (asyncio.gather→merge→sort by created_at→slice) и
single-type ветки; `GET /search/suggest` (KB+News, дедуп).

**Контракт (не ломать):** пути `GET /api/v1/search`, `/search/suggest`; формат ответа (`items[]`,`total`,`query`;
`suggestions[]`); параметры (`q`,`type`,`limit`,`offset`, фильтры дат/author/department); ACL KB
(`apply_article_visibility`, `filter_accessible_articles`) и role-targeting новостей; URL-шаблоны результатов.

**Запахи:** толстый хендлер `global_search` (~360 строк: orchestration+SQL+ACL+правила); дублирование логики
article/news/link/user между multi и single ветками; magic (`_HL_OPTIONS`, role tuple, limit 10/5, rate 60/120);
невалидный `type` молча → поиск по всем типам.

> 🐛 **Флаг (не для рефактора, зафиксировать):** в single-type для `link`/`user` нет `order_by`, в multi-type
> есть `created_at desc` → возможна недетерминированная выдача. Решать отдельно как баг, не в рамках переноса.

**Декомпозиция:** вынести в `services/` per-entity query-сервисы (conditions+count+items+маппинг), общие
filter-builders (from/to/author/department), policy сортировки/лимитов, suggest-use-case. Хендлер → тонкий.

> ⚠ **53% — рефакторинг ТОЛЬКО после характеризующих тестов:** single-type каждого типа (total/items/URL),
> multi-type merge-order+slice, фильтры дат/author/department, role-targeting (reader vs editor/admin),
> вызов ACL-функций, suggest (дедуп, max 10, порядок KB→News), `type=invalid`→fallback.

---

### 4.5 `backend/app/api/kb/export_import.py` (492 строк) — макс. score backend

**Ответственности:** экспорт KB (MD/ZIP-секция/vault.zip/PDF/DOCX) + импорт (article/vault), форматная логика
(frontmatter, ZIP, HTML→PDF, MD→DOCX), бизнес-логика импорта (conflict-strategy `skip|overwrite|create_new`),
ACL+аудит, валидация ввода (лимиты, zip-bomb/filename, UTF-8).

**Контракт (не ломать):** пути роутов; `ImportReport`; заголовки `Content-Disposition`/RFC5987; строки audit
event_type (`kb.article_exported_pdf/docx` читаются в `api/analytics.py:234-235` — **менять нельзя**).

**Запахи:** толстые хендлеры (`import_vault_zip`, `export_article_docx/pdf`); дублирование safe-filename
(4 места) и ACL+403; смешение HTTP+парсинг+DB-write+домен; magic (`64*1024`, `1000` файлов, `*5` ratio,
`tags[:20]`, срезы заголовков).

**Декомпозиция в `services/`:** `kb_export.py` (MD/ZIP/PDF/DOCX payload + policy), `kb_import.py` (единый
ingestion pipeline .md/.zip, conflict-resolution, сбор `ImportReport`), `kb_filenames.py`/`kb_limits.py`
(safe-name, лимиты, zip-guards). Хендлер = ACL + вызов сервиса + `Response`.

> Покрытие 75%, но **DOCX-endpoint фактически не тестируется**. До рефактора добавить: DOCX success/404/403/draft,
> проверки `Content-Disposition`, пограничные ZIP (1000 vs 1001 файл, порог ratio), транзакционность vault
> (ошибка одного md не рушит батч; счётчики created/updated/skipped/errors), overwrite/create_new side-effects.

---

### 4.6 `backend/app/api/links.py` (428 строк) — покрытие 81%

**Ответственности:** `ServiceLink` (URL/SSO/активность/категория/порядок/иконка). Роуты `/links`: list (фильтры
category/include_inactive/orphaned + hidden_link_ids из preferences), `PATCH /reorder`, get-by-id, SSO-redirect +
legacy `sso-url`, CRUD admin, иконки (upload/delete). По факту: HTTP+SQL+SSO+файлы иконок+аудит в одном слое.

**Контракт (не ломать):** пути под `prefix="/links"`; response-модели `ServiceLinkList`/`ServiceLinkPublic`;
legacy payload `{"url":..,"sso":True}`; SSO — `id_token_hint`, cookie `SESSION_COOKIE_NAME`, редирект ровно `302`;
URL иконок `/media/link_icons/{id}.{ext}`; audit `links.created/updated/deleted/reordered`.

**Запахи:** толстые хендлеры (`list_links`, `upload_link_icon`, `reorder_links`); дубли «load by id + 404» и
`push_audit_event+logger.info`; смешение слоёв (Path/unlink/MIME/оптимизация иконок в API); magic (event-types,
`_LINK_ICON_TARGET_PX`, MIME map).

**Декомпозиция в `services/`:** links_query (условия+hidden+count), links_crud (get/create/update/delete/reorder),
links_sso (URL builder для redirect+legacy), link_icon (MIME/size/optimize/save/url), audit-helper.

> 81% → до рефактора тесты: фильтры (битый hidden_link_ids не падает; admin/non-admin), SSO-ветки
> (supports_sso F/T, есть/нет session/token, `id_token_hint` при `?` в URL), reorder mismatch→404,
> иконки (MIME allow/deny, лимит, смена ext, удаление старых, DELETE идемпотентность), точные event_type/metadata.

---

### 4.7 `backend/app/api/notifications.py` (374 строк) — покрытие 75%

**Ответственности:** CRUD/чтение (list, unread-count, mark-read, mark-all, delete) + **realtime SSE**
(`_sse_generator`: 3 Redis Streams notification/meeting_changed/photo_processed, лимиты соединений, keepalive,
TTL коннекта, продление session TTL, backoff).

**Контракт (не ломать):** маршруты `/notifications`, `/unread-count`, `/{id}/read`, `/read-all`, `/{id}`,
`/stream`; семантика лимитов SSE (per-user+global, коды 429/503); формат SSE-событий и `id` как composite
triple `personal|meetings|photos`; поддержка `Last-Event-ID` и replay; Lua-коды `-1/-2`.

**Запахи:** API содержит инфраструктуру (Redis Streams, Lua, backoff, session-sliding) вместо service-уровня;
**god-функция** `_sse_generator` (парсинг+чтение 3 потоков+сериализация+keepalive+TTL+cleanup); дубли сборки
composite id/SSE-кадров в 3 ветках; скрытые контракты-magic (формат Last-Event-ID, коды Lua, интервалы).

**Декомпозиция в `services/notifications.py`:** SSE-orchestration (чтение потоков+payload), connection
lifecycle (add/remove/refresh TTL+Lua+cleanup), session keepalive policy, parser/formatter (Last-Event-ID+frame).
Роуты → тонкая HTTP-граница.

> 75% → до рефактора тесты: SSE-ошибки (xread→backoff+jitter, RedisError→503, TTL/session warn-paths), лимиты Lua
> (-1/-2), варианты Last-Event-ID (пустые/неполный triple/нет header), list (unread_only/limit/offset, total),
> идемпотентность mark-read/all + 404/204.

---

### 4.8 `backend/app/api/branding.py` (465 строк) — покрытие 76% (в ruff E501-ignore)

**Ответственности:** **branding + email settings в одном модуле** — настройки портала, CRUD logo/favicon/login-bg,
SMTP settings, тестовое письмо; файловое хранилище (`settings.json`, `email-settings.json`); cache headers на
image-endpoints. (Рендера nginx/css здесь нет.)

**Контракт (не ломать):** роутер на `/api/v1`; публичные `load_branding_settings`, `find_branding_file`,
`BRANDING_*` — **импортируются напрямую в `bootstrap.py`** (связанность); файл
`/data/branding/email-settings.json` читается также воркером (`worker/tasks/email_utils.py`) и
`services/meetings/notifications.py`; mask-политика пароля (`null`/`***` сохранить, `""` очистить); URL upload-ответов;
cache headers.

**Запахи:** смешение HTTP+FS+SMTP+audit; повтор «действие+push_audit_event» во всех admin-роутах; бизнес-логика
в API (password mask, SMTP kwargs, HTML письма); дубли GET/HEAD/reset/upload для 3 ассетов; magic
(`/data/branding`, max-size, cache TTL); E501-ignore коррелирует с перегруженностью.

**Декомпозиция в `services/`:** branding_assets (find/delete/upload+MIME), branding_settings (load/save+has_*),
email_settings (load/save+mask), email_test (build+SMTP send+TLS/STARTTLS), audit-helper. **Отдельно:** развязать
`bootstrap` от `api.branding` → импорт из schemas/services.

> 76% → до рефактора тесты: upload-endpoints (нет фактических тестов!), HEAD-ветки, `_send_test_email`
> (TLS/STARTTLS/auth/исключения), `logo_updated_at`+cache headers, fallback при битом JSON + `chmod(0o600)`,
> кросс-модульная согласованность SMTP (api vs worker vs meetings).

---

### 4.9 `frontend/src/pages/KbListPage.vue` (426 строк) — churn 17, func-cov ~5%

**Ответственности:** оркестрация экрана KB (layout/header/sidebar/список+пагинация); дерево секций
(создание/перемещение/права/удаление через модалки); листинг (поиск/фильтры/grid-list/empty); права
(`auth.isAdmin/isEditor` + `section.user_permission`); навигация + импорт/экспорт.

**Контракт (не ломать):** props/events дочерних (`KbListToolbar`, `KbSectionTree`, `Kb*Modal`, `KbArticleCard/Row`);
матрица прав на кнопки; синхронность секция↔листинг; `viewMode` в localStorage (`VIEW_MODE_KEY`); маршруты
(`/kb/create`, `/kb/articles/:id`, `kb-trash`) с параметрами.

**Запахи:** толстый `script setup` (UI+policy+persistence); бизнес-логика в странице (`canCreateArticle`, export,
drawer-режимы); смешение state/UI; magic (`VIEW_MODE_KEY`, route-строки, inline-стили пагинации).

**Декомпозиция:** `pages/composables/` — useKbListPagePermissions, useKbListViewMode, useKbListNavigation;
`composables/` — useKbSectionExport, useKbAdminDrawer; под-компоненты PageActions, SectionsSidebar, ArticlesContent.

> ⚠ func-cov ~5%: строки 80% не защищают логику. Перенос меняет границы реактивности → тихие регрессии.
> До дробления: матрица прав (admin/editor/обычный + permission), переходы всех action-кнопок, viewMode
> read/write+fallback, реакции выбор секции/фильтры/поиск/пагинация, модалки/drawer без смены side-effects.

---

### 4.10 `frontend/src/pages/FilesPage.vue` (334 строк) — churn 16, func-cov ~0%

**Ответственности:** оркестрация файлового менеджера (sidebar/breadcrumbs/toolbar/table/bulk/модалки/drawers);
state модалок/preview/share/view + проксирование из `useFiles*`/`useCollabora`; потоки действий (выбор папки,
upload+DnD, bulk, delete, preview image/pdf, share, NC-sync); init `sharesView` из query (`tab=`) в onMounted.

**Контракт (не ломать):** инварианты — `tab` query переключает shares-view; `selectFolder`→`sharesView='folders'`;
DnD/upload только при `canUpload` и в folders-режиме; bulk зависит от selection; admin drawers только при isAdmin;
preview PDF через `noopener,noreferrer`; after-mutation refresh/clear selection.

**Запахи:** перегруженный `script setup` (orchestration+flow+UI-state); confirm/message/error+side-effects
(`window.open`, delete) на page-level; неоднородные `onX`-хендлеры; magic (строки view-режимов/query-табов).

**Декомпозиция (поверх существующих `useFiles*`):** useFilesPageController (sharesView+modal-state+route-init+
handlers), composable destructive-actions (confirm+message+try/catch), preview/share-flow; template-контейнеры
main-content switch + modal-host.

> ⚠ func-cov ~0%: до дробления тесты: init sharesView из query; выбор папки→load detail (watcher); create/delete
> folder (ок/ошибка+confirm); delete file (guard без folderId); sync ок/ошибка; переключение shares/folders;
> preview image index + PDF window.open; admin-drawer gating по isAdmin.

---

### 4.11 `frontend/src/pages/HomePage.vue` (474 строк) — churn 13, func-cov ~0%

**Ответственности:** композиция главной (баннер, hero, featured/latest новости, виджеты Photos/WorldClock/Meetings,
блок сервисов, последние KB-статьи); dismiss баннера через `sessionStorage`; условные skeleton/empty/content;
данные через `useKbArticlesQuery`, `useHomeNews()`, links/branding/auth stores.

**Контракт (не ломать):** child-route `name:'home'`; навигация `/news/create`, `/news`, `/links`, `/kb`,
`/kb/articles/:id`; `NewsCard` emit `click(id)`; баннер от `branding.isBannerActive`/`banner_*`.

**Запахи:** god-page (новости+links+KB+branding+3 виджета+hero); смешение view+persistence+orchestration; длинный
`script setup`+большой style; magic (лимиты 5/4/6, ключ `home_banner_dismissed`, брейкпоинты); дубли
«section header + action button». **Скрытая связность:** `useHomeNews` грузит ещё и `linksStore.loadLinks()`.

**Декомпозиция:** composables — useHomeBannerDismiss, useHomeLinksPreview, useRecentKbArticles (+ развязать
`useHomeNews` от links); виджеты в `components/widgets/` — HomeFeaturedNewsSection, HomeLatestNewsSection,
QuickServicesWidget, RecentArticlesWidget, PortalBanner.

> ⚠ func-cov ~0%: до дробления тесты: banner show/hide+sessionStorage (повторно не показывать при том же bannerKey);
> news loading→skeleton, pinned/regular split, клик→`/news/:id`; quick-services loading/empty/content+openLink;
> recent KB ≤5+переход; кнопка create только при isEditor; smoke главной.

---

### 4.12 `backend/app/api/photos/folders.py` (288 строк) — ⚠ покрытие 22%, но структура уже тонкая

**Важно:** вопреки высокому риск-флагу из матрицы (score 3157, 22%), модуль **уже декомпозирован** —
это тонкий HTTP-слой, делегирующий бизнес-логику в `folder_service` и доступ к данным в
`photos_folder_repo`. То есть **главная боль — не структура, а отсутствие тестов** на горячем (churn 11)
модуле. Рефакторинг-выгода здесь мала; ценность — в характеризующих тестах.

**Ответственности:** 8 роутов `/folders*` (tree, deleted, get, create, update, delete, restore, purge);
сборка дерева с правами (`filter_accessible_folders_with_perm`); ACL-гейтинг
(`require_folder_permission`/`resolve_folder_permission`/`perm_gte`); инвалидация кэша; аудит; mkdir на ФС.

**Контракт (не ломать):** пути и коды (`201` create, `204` delete/purge, `404/403/409/400`); фильтрация
дерева по правам; видимость удалённых (admin → все как `manager`, иначе только `manager` и не вложенные
в уже-удалённую); event_type `photos.folder_created/deleted/restored/purged`; `IntegrityError → 409`.

**Запахи (минорные):** повтор «`fetch_active_folder` + 404» (5 мест) и «`fetch_folder_any` + 404 + проверка
`deleted_at`» (restore/purge); повтор `push_audit_event(...)`-блоков; неиспользуемый `request` в части
сигнатур; ручная сборка `FolderTreeNode` в хендлере (можно в маппер).

**Стратегия:** структурный рефактор НЕ приоритетен. Сначала **FO-0 (тесты)**; косметика (общий
`_get_folder_or_404`, audit-helper, маппер дерева) — опционально и только после сетки тестов.

> ⚠ 22% — самый низкий показатель среди целей. FO-0 обязателен: дерево с правами (роли admin/обычный,
> вложенность), create (root admin/editor-gate, parent-perm, slug/fs-collision→409, mkdir-fail не валит запрос),
> update (move/rename/cover/description + fs-rename), delete/restore/purge (статусы, `deleted_at`-гейты,
> инвалидация кэша, audit metadata purge).

---

### 4.13 `backend/app/services/files_acl.py` (388 строк) — покрытие 95%, низкий приоритет

**Оценка:** хорошо факторизован (общие примитивы в `acl_base`), покрыт на 95%. Не «толстый» в смысле
запутанности — это насыщенный, но связный ACL-сервис. В матрице — низкий риск; **в scope итерации-1
включать не обязательно.**

**Что есть:** folder-ACL (`resolve_folder_permission`, `require_folder_permission`,
`batch_resolve_folder_permissions` с рекурсивным CTE + Redis-кэш) **и** per-file shares
(`resolve_file_share_permission`, `require_file_access` = max(folder, share)).

**Контракт (не ломать):** иерархия `viewer<editor<manager`; алгоритм резолва (admin/owner→manager,
кэш, CTE вверх по дереву до `inherit_permissions=FALSE`, лимит глубины `_MAX_FOLDER_DEPTH=20`);
формат ключей кэша (`files_acl:*`, `files_share:*`) и значение `"none"`; `require_*` → 403.

**Запахи (минорные):** в одном файле две темы (folder-ACL и file-shares) — кандидат на разделение;
5 alias-import'ов из `acl_base` (`X as _X`) — стилевой шум; `_PERM_RANK` дублируется с `photos_acl`
(общий ранжировщик можно поднять в `acl_base`); дублирующиеся CTE в `_resolve_via_cte` и
`batch_resolve_folder_permissions`.

**Стратегия:** только при свободном времени. AC-1: вынести общий `_PERM_RANK`/`perm_gte` в `acl_base`
(затрагивает и `photos_acl` — проверить). AC-2 (опц.): разнести folder-acl и file-share в два модуля
пакета. Покрытие 95% → безопасно, но выгода ограничена.

---

## 5. Backlog рефакторинга (формируется из этапа 4)

Каждая задача — атомарная, поведение-сохраняющая, с критерием готовности «baseline зелёный».

**Эпик: декомпозиция `photos_storage.py` (из 4.1)**
- [x] PS-1: превратить модуль в пакет `app/services/photos_storage/` (paths/originals/thumbnails/metadata),
  `__init__.py` ре-экспортирует все публичные символы + `_get_thumb_semaphore`. Перенос кода 1:1.
  *Критерий: 12 импортеров не меняются; ruff/mypy app/pytest зелёные.* → **DONE** 2026-06-02.
  Все cross-module/патчабельные имена (`ORIGINALS_ROOT`, `THUMBS_ROOT`, `GENERATE_AVIF`, `AVIF_MIN_SIZE`,
  `_ALLOWED_ROOTS`, `_open_image`, `generate_thumbnails`, `folder_fs_path`, ...) подмодули читают через lazy
  `from app.services import photos_storage as _ps; _ps.<name>` (паттерн из `api/photos/photo_service`), чтобы
  `patch("app.services.photos_storage.X")` из тестов действовал. Gates: ruff check/format `.` PASS, `mypy app`
  PASS (262 файла), `pytest tests/unit tests/security` 2365 PASS, cov 76.20%.
- [x] PS-2: извлечь helper'ы из `generate_thumbnails` (`_cascade_resize`, `_encode_thumb`) с сохранением
  логики close()/gc. *Отдельный коммит.* → **DONE** 2026-06-02. Цикл каскада теперь
  `scaled = _cascade_resize(current, size); result[size] = _encode_thumb(scaled, out_dir, size)`; трекинг
  `intermediates`/`current` и finally-блок (close() + gc.collect()) **не тронуты**. Helper'ы — приватные
  внутри `thumbnails.py` (не реэкспортируются). Gates: ruff/`mypy app` PASS (262), pytest 2365 PASS, cov 76.21%.
- [x] PS-3: централизовать lazy-import PIL внутри пакета thumbnails. → **DONE** 2026-06-02. Добавлен helper
  `_import_pil(*, register_heif=False) -> (Image, ImageOps)`; HEIF регистрируется только при `register_heif=True`
  (поведение 1:1: ранее `register_heif_opener()` звался только в `_open_image`). `_open_image`/`_cascade_resize`/
  `generate_thumbnails` используют helper; `DecompressionBombError` берётся как `Image.DecompressionBombError`.
  Локальные имена `Image`/`ImageOps` помечены `# noqa: N806` (PIL-конвенция; app не игнорит N806). Патчи тестов
  (`PIL.Image.open`, `PIL.ImageOps.exif_transpose`, `PIL.Image.Image.MAX_IMAGE_PIXELS`) продолжают действовать.
- [x] PS-4: поправить устаревший комментарий у `THUMB_SIZES`; уточнить тип `extract_exif → dict[str, Any]`.
  → **DONE** 2026-06-02. Комментарий приведён к 5 размерам (widget/grid 200–600, lightbox/preview 1000–1600);
  `extract_exif` → `dict[str, Any]` (возврат + локальный `exif`), добавлен `from typing import Any` в `metadata.py`.
- [ ] PS-5 (осторожно, потенциальное изменение поведения): env-флаги → `app.core.config` Settings. *(отложен)*

**Эпик: `RichEditor.vue` (из 4.2)** — *сначала тесты, риск высокий (func-cov 11%)*
- [ ] RE-0: характеризующие тесты (v-model sync, модалки, link-dialog ветки, media-входы, fullscreen/Escape).
- [ ] RE-1: вынести fullscreen/focus state + `shouldShowBubbleMenu`/`handleDblClick` в composables.
- [ ] RE-2: под-компонент `RichEditorBubbleMenu`.
- [ ] RE-3: модалки по одной (video/details → image → link+kb).
- [ ] RE-4: перенос/декомпозиция `<style scoped>` (последним, без смены селекторов).

**Эпик: `NewsFormPage.vue` (из 4.3)**
- [ ] NF-0: характеризующие тесты (create/edit init, 3 submit-пути, fail-валидации, autosave-контракт).
- [ ] NF-1: вынести чистые мапперы/константы (status/focal/date-адаптеры).
- [ ] NF-2: `useNewsFormState` (модель+init+validate+submit) + `useNewsFormOptions`.
- [ ] NF-3: под-компоненты `NewsFormSettingsCard`, `NewsFormMainFields`.

**Эпик: `api/search.py` (из 4.4)** — *⚠ блокер: покрытие 53%, без тестов не трогать*
- [x] SE-0: поднять покрытие характеризующими тестами (single/multi/фильтры/ACL/suggest/invalid-type).
  → **DONE** 2026-06-02. `tests/unit/test_search.py` (45 тестов); `app/api/search.py` **53%→98%**. SE-1..3 разблокированы.
- [ ] SE-1: вынести filter-builders (from/to/author/department) в `services/`.
- [ ] SE-2: per-entity query-сервисы по одному (link → user → news → article).
- [ ] SE-3: multi-type merge/sort/paginate policy + suggest-use-case в `services/`.
- [ ] (отдельно, как баг) SE-bug: детерминированный `order_by` для single-type link/user.

**Эпик: `api/kb/export_import.py` (из 4.5)**
- [x] EI-0: дописать тесты (DOCX-endpoint, Content-Disposition, ZIP-границы, транзакционность vault).
  → **DONE** 2026-06-02. `tests/unit/test_kb_export_import.py` +15 тестов (DOCX 404/403/draft/success/editor,
  audit `kb.article_exported_docx/pdf`, RFC5987 `Content-Disposition` для MD/PDF/ZIP/DOCX, vault: ошибка одного md
  не рушит батч, граница 1000 файлов, overwrite/create_new, счётчики `ImportReport`). EI-1..3 разблокированы.
- [x] EI-1: вынести pure-helpers (safe-filename, size-guard, zip-entry validation) + константы/лимиты.
  → **DONE** 2026-06-02. Stems (`article_md_stem`/`section_zip_stem`/`document_stem`) в `services/kb_export.py`;
  `validate_vault_archive`/`collect_vault_md_files` + `MAX_VAULT_FILES`/`VAULT_UNCOMPRESSED_RATIO` в `services/kb_import.py`.
- [x] EI-2: `services/kb_import.py` (ingestion pipeline + conflict-resolution + ImportReport).
  → **DONE** 2026-06-02. `import_single_article` (skip/overwrite/create_new) + vault-guards. ACL/sanitize-патчи
  тестов ретаргетированы на `app.services.kb_import.*` (поведение 1:1).
- [x] EI-3: `services/kb_export.py` (MD/ZIP/PDF/DOCX), хендлеры → тонкие.
  → **DONE** 2026-06-02. `render_article_pdf`/`render_article_docx`/`build_article_pdf_html` + stems; frontmatter/zip/
  section-path вынесены в `services/kb_markdown.py`; `_frontmatter.py` удалён. Хендлеры `export_import.py` тонкие
  (ACL+audit+Response). Gates: ruff check/format `.` PASS, `mypy app` PASS (264), pytest 2514 PASS, cov **78.44%**.

**Эпик: `api/links.py` (из 4.6)**
- [x] LI-0: тесты-страховка (фильтры+битый hidden_link_ids, SSO-ветки, reorder→404, иконки MIME/лимит/ext/delete, event_type).
  → **DONE** 2026-06-02. `tests/unit/test_links_api.py` +19 тестов; `app/api/links.py` **81%→100%**.
  (фильтры include_inactive/category/orphaned, битый hidden_link_id не падает; SSO token + `&` при `?` в URL;
  upload иконки success/404/ext-change/url-format; audit `links.created/updated/deleted/reordered`). LI-1..4 разблокированы.
- [x] LI-1: вынести `links_query` (условия+hidden+count) и audit-helper.
  → **DONE** 2026-06-02. `services/links_query.py` (`build_link_conditions`/`parse_hidden_uuids`/
  `list_service_links` — fetch+filter+count в 2 execute, порядок сохранён). Локальный `_emit_link_audit`
  в `api/links.py` (дедуп `resource_type="link"`); `push_audit_event` остаётся патчабельным через `app.api.links`.
- [x] LI-2: `links_crud` (get/create/update/delete/reorder) + единый «load by id + 404».
  → **DONE** 2026-06-02. `services/links_crud.py`: `get_link_or_404`, `create_link`, `update_link`
  (возвращает changed_fields), `delete_link`, `set_icon_url`, `reorder_links` (404 при mismatch). Хендлеры тонкие.
- [x] LI-3: `links_sso` (URL builder redirect+legacy `sso-url`) — сохранить 302 и cookie/token-семантику.
  → **DONE** 2026-06-02. `services/links_sso.py::build_sso_url` (cookie→session→`id_token_hint`, `&`/`?` separator).
  Патч `get_session` ретаргетирован на `app.services.links_sso.get_session`.
- [x] LI-4: `link_icon` (MIME/size/optimize/save/url) — сохранить формат `/media/link_icons/{id}.{ext}`.
  → **DONE** 2026-06-02. `services/link_icon.py`: `remove_icon_files`/`optimize_link_icon`/`save_link_icon`
  + константы (`LINK_ICONS_DIR`, MIME→ext, `MAX_ICON_SIZE`). Патчи иконок/`stream_upload_to_path`/`LINK_ICONS_DIR`
  ретаргетированы на `app.services.link_icon.*`. Gates: ruff/`mypy app` PASS (268), pytest 2514 PASS, cov **78.46%**;
  модули LI покрыты 100%.

**Эпик: `api/notifications.py` (из 4.7)**
- [x] NO-0: тесты SSE-веток (backoff/jitter, 503 на RedisError, лимиты Lua -1/-2, варианты Last-Event-ID, list/mark/idempotency).
  → **DONE** 2026-06-02. Новый `tests/unit/test_notifications_sse_generator.py` +19 тестов; `app/api/notifications.py`
  **75%→100%**. (Last-Event-ID: `$`/triple/empty-parts/2-part; 3 потока notification/meeting_changed/photo_processed;
  composite id; backoff при ошибке gather; keepalive+TTL-refresh+session-extend (включая swallow-исключений);
  cleanup zrem; stream 200 + cookie). NO-1..3 разблокированы.
- [ ] NO-1: вынести parser/formatter (Last-Event-ID triple + SSE-кадр) в `services/notifications.py`.
- [ ] NO-2: connection lifecycle (add/remove/refresh TTL + Lua + cleanup).
- [ ] NO-3: SSE-orchestration (чтение 3 потоков + payload) + session keepalive policy; роуты → тонкие.

**Эпик: `api/branding.py` (из 4.8)**
- [x] BR-0: тесты (upload-endpoints, HEAD, `_send_test_email` TLS/STARTTLS/ошибки, cache headers, битый JSON+chmod, кросс-SMTP).
  → **DONE** 2026-06-02. `tests/unit/test_branding.py` +27 тестов; `app/api/branding.py` **76%→97%**.
  (upload logo/favicon/login-bg success+MIME 422+403 non-editor; HEAD-ветки+cache headers; `logo_updated_at`;
  `_send_test_email` TLS/STARTTLS/creds/swallow-исключения; битый JSON→defaults; `chmod(0o600)`; кросс-SMTP:
  формат файла читается `email_utils.load_smtp_config`, пароль plaintext, `""` round-trip). Остаток: 4 строки
  `FileResponse(...)` (нужен реальный файл на диске). BR-1..4 разблокированы.
- [ ] BR-1: развязать `bootstrap.py` от `api.branding` (импорт из schemas/services) — снять архитектурную связанность.
- [ ] BR-2: `services/branding_settings` (load/save/has_*) + `branding_assets` (find/delete/upload+MIME).
- [ ] BR-3: `services/email_settings` (load/save+mask политика) + `email_test` (build+SMTP send) — синхронно с worker/meetings.
- [ ] BR-4: audit-helper; дубли GET/HEAD/reset/upload 3 ассетов → общий.

**Эпик: `KbListPage.vue` (из 4.9)** — *func-cov ~5%, сначала тесты*
- [ ] KL-0: характеризующие тесты (матрица прав, action-навигация, viewMode persistence, секция/фильтры/пагинация, модалки/drawer).
- [ ] KL-1: useKbListViewMode (localStorage) + useKbListPagePermissions.
- [ ] KL-2: useKbListNavigation + useKbSectionExport/useKbAdminDrawer.
- [ ] KL-3: под-компоненты PageActions, SectionsSidebar, ArticlesContent.

**Эпик: `FilesPage.vue` (из 4.10)** — *func-cov ~0%, сначала тесты*
- [ ] FP-0: характеризующие тесты (init `tab`→sharesView, выбор папки, create/delete folder±ошибка, delete-guard, sync, preview image/PDF, admin-drawer gating).
- [ ] FP-1: useFilesPageController (sharesView+modal-state+route-init+handlers) поверх существующих `useFiles*`.
- [ ] FP-2: composable destructive-actions (confirm+message+try/catch) + preview/share-flow.
- [ ] FP-3: template-контейнеры (main-content switch + modal-host).

**Эпик: `HomePage.vue` (из 4.11)** — *func-cov ~0%, сначала тесты*
- [ ] HP-0: характеризующие тесты (banner sessionStorage, news split/клик, quick-services, recent KB, create только editor, smoke).
- [ ] HP-1: useHomeBannerDismiss (sessionStorage) + развязать `useHomeNews` от `linksStore.loadLinks()`.
- [ ] HP-2: useHomeLinksPreview + useRecentKbArticles.
- [ ] HP-3: виджеты в `components/widgets/` (Featured/Latest news, QuickServices, RecentArticles, PortalBanner).

**Эпик: `api/photos/folders.py` (из 4.12)** — *структура уже тонкая; главное — тесты (22%)*
- [x] FO-0: характеризующие тесты (дерево+права, create-гейты/коллизии/mkdir-fail, update move/rename/cover, delete/restore/purge статусы+кэш+audit).
  → **DONE** 2026-06-02. Новый `tests/unit/test_photos_folders_api.py` (42 теста); `app/api/photos/folders.py` **22%→100%**.
- [ ] FO-1 (опц.): общий `_get_folder_or_404` + helper для restore/purge-проверок `deleted_at`.
- [ ] FO-2 (опц.): audit-helper; вынести сборку `FolderTreeNode` в маппер; убрать неиспользуемый `request`.

**Эпик: `services/files_acl.py` (из 4.13)** — *низкий приоритет, 95% покрытия, вне обязательного scope*
- [ ] AC-1: поднять общий `_PERM_RANK`/`perm_gte` в `acl_base` (проверить совместное использование с `photos_acl`).
- [ ] AC-2 (опц.): разнести folder-ACL и file-share на два модуля пакета `files_acl/`.

---

## 6. Сквозные (cross-cutting) задачи — кандидаты

- [ ] Расширять strict-зону `mypy` (добавлять модули в `disallow_untyped_defs`).
- [ ] Сокращать `ruff` `per-file-ignores` (закрыть `TODO(REVIEW-5.2)`: `F811`, `F841`).
- [ ] Типизация тестов backend: `mypy .` даёт 104 ошибки в `tests/*` (SimpleNamespace вместо моделей, conftest). Не гейт CI, но стоит постепенно чистить.
- [ ] Унифицировать обработку ошибок API (`utils/parseApiError.ts`, `mapMeetingsError.ts`).
- [ ] Выделять повторяющуюся логику из «толстых» `.vue` в `composables/`.
- [ ] **Развязать `bootstrap.py` от слоя API** (`api.branding`) — пример нарушения направления зависимостей
  (bootstrap → api). Перенести разделяемые функции/константы в `schemas`/`services`. См. BR-1.
- [ ] **Скрытая кросс-доменная связность во фронт-composables**: `useHomeNews` грузит и `linksStore.loadLinks()`
  — побочный эффект вне домена. Аудитировать остальные `composables/` на скрытые store-загрузки. См. HP-1.
- [ ] **Общий контракт SMTP-файла** `/data/branding/email-settings.json` читается из 3 мест (api/branding,
  worker/tasks/email_utils, services/meetings/notifications) — вынести единый загрузчик, чтобы формат не разъехался.
- [ ] **Повторяющийся паттерн «действие + push_audit_event + logger»** в API-модулях (links, branding, …) —
  кандидат на общий audit-helper/декоратор.
- [ ] **Характеризующие тесты для `.vue`-страниц** (func-cov 0–11% при line-cov ~80%): line-coverage обманчив,
  набран mount/smoke. Перед любой декомпозицией страницы — шаг `-0` с тестами на функции/ветки/хендлеры.

---

## 7. Порядок исполнения (roadmap итерации-1)

Принцип очередности: **(1)** обкатать процесс на самой безопасной цели → **(2)** закрыть тестовые
блокеры там, где покрытие низкое, до любых структурных правок → **(3)** идти по убыванию score,
чередуя backend/frontend, чтобы не копить риск в одном слое.

**Волна 0 — обкатка процесса (низкий риск):**
1. `PS` (`photos_storage`, 98%) — эталонный безопасный рефактор: модуль→пакет с ре-экспортом.
   На нём фиксируем рабочий цикл (DoD из раздела 8) и формат коммитов.

**Волна 1 — снять тестовые блокеры (низкое покрытие на горячих модулях):**
2. `SE-0` (`search`, 53%) и `FO-0` (`folders`, 22%) — только характеризующие тесты, без структурных
   изменений. После этого `SE-1..3` становятся безопасными.

**Волна 2 — backend по score (покрытие ≥75%):**
3. `EI` (`export_import`, score 4428) → `LI` (`links`, 3852) → `NO` (`notifications`, 3740) →
   `BR` (`branding`, 3720, **начать с BR-1** — развязать `bootstrap`).
4. `SE-1..3` (после SE-0).

**Волна 3 — frontend (каждый эпик начинается со своего `-0`: тесты обязательны, func-cov 0–11%):**
5. `RE` (`RichEditor`, score 9960) → `NF` (`NewsFormPage`, 8967) → `KL` (`KbListPage`, 7242) →
   `HP` (`HomePage`, 6162) → `FP` (`FilesPage`, 5344).

**Волна 4 — опциональное / по остаточному времени:**
6. `AC` (`files_acl`, 95%, низкая выгода) + сквозные задачи раздела 6 (mypy strict-зона, ruff
   per-file-ignores, единый SMTP-загрузчик, audit-helper).

> Правило: не запускать структурный шаг `-1..N` эпика, пока его шаг `-0` (тесты) не зелёный.
> Один эпик — одна ветка/серия PR; не смешивать эпики между собой.

---

## 8. Definition of Done одного refactor-шага

Чек-лист на **каждый** коммит из backlog (поведение-сохраняющий):

- [ ] Изменение соответствует ровно одному пункту backlog (один вид правки, без багфиксов/фич).
- [ ] Публичный контракт не тронут: пути/коды API, схемы (`openapi.json`), props/emits компонентов,
  строки `event_type`, форматы кэш-ключей, URL-шаблоны.
- [ ] **Backend локально зелёный:** `ruff check .`, `ruff format --check .`, `mypy app`,
  `pytest tests/unit tests/security --cov=app` (≥75%).
- [ ] **Frontend локально зелёный:** `npm run lint:check`, `npm run typecheck`, `npm run test:coverage`.
- [ ] Покрытие не упало относительно baseline (этап 2); для шагов `-0` — выросло на целевых функциях/ветках.
- [ ] Коммит оформлен как `refactor(<module>): <что>` (по `AGENTS.md`); коммитит **пользователь**.
- [ ] Для рискованных модулей (func-cov низкий) — соответствующий шаг `-0` уже влит.

> Примечание по baseline: `pytest tests/integration` (heavy, testcontainers) и `mypy .` (104 ошибки в
> `tests/*`, **не** CI-гейт) — **не блокируют** старт итерации-1. Integration гоняем точечно при правках,
> затрагивающих БД/Redis-поведение; типизацию тестов чистим отдельной сквозной задачей (раздел 6).

---

## Журнал решений

| Дата | Решение / изменение плана |
|------|---------------------------|
| 2026-06-01 | Создан план. Подход: непрерывный точечный рефакторинг, не переписывание. |
| 2026-06-01 | Этап 2: baseline зелёный по всем CI-гейтам (ruff/format/mypy app/pytest 76.17%/eslint/vue-tsc/vitest 70.15%). Найдено: `mypy .` → 104 ошибки в `tests/` (не гейт) — в backlog. Integration-тесты не гоняли (heavy). |
| 2026-06-01 | Этап 3: собрана матрица LOC×churn×coverage. Рекомендованные первые цели: backend — `photos_storage.py` (score 4005, cov 98%, низкий риск); frontend — `RichEditor.vue` (score 9960, но func-cov 11% — нужны тесты) либо `NewsFormPage.vue` (max churn 21). |
| 2026-06-01 | Этап 4: разобран `photos_storage.py`. Вывод — god-module (5 ответственностей). Безопасный путь: модуль→пакет с ре-экспортом в `__init__` (12 импортеров не трогаем; `_get_thumb_semaphore` де-факто публичный). Backlog PS-1..PS-5. Реализацию НЕ начинали. |
| 2026-06-01 | Этап 4 (расширен): добавлен анализ RichEditor.vue (4.2), NewsFormPage.vue (4.3), search.py (4.4), export_import.py (4.5). Ключевое: фронт-цели имеют func-cov 9-11% → тесты-первыми обязательны; search.py (53%) — блокер без тестов; найден флаг-баг недетерминированной выдачи в search single-type. Backlog RE/NF/SE/EI. |
| 2026-06-01 | Этап 4 (завершён, опция A): добиты оставшиеся цели матрицы — links.py (4.6), notifications.py (4.7), branding.py (4.8), KbListPage.vue (4.9), FilesPage.vue (4.10), HomePage.vue (4.11). Backlog LI/NO/BR/KL/FP/HP. Новые сквозные находки: bootstrap→api.branding (нарушение направления зависимостей), скрытая связность `useHomeNews`→links, общий SMTP-файл на 3 потребителя, повтор audit-паттерна. Подтверждено: все фронт-страницы func-cov 0–5% → обязательный шаг `-0` (характеризующие тесты). Реализацию НЕ начинали. |
| 2026-06-01 | План завершён: закрыты дырки матрицы — folders.py (4.12, вывод: уже тонкий слой, проблема не структура, а 22% покрытия → нужен только FO-0) и files_acl.py (4.13, 95%, низкий приоритет, вне обязательного scope; backlog AC). Добавлен раздел 7 (порядок исполнения волнами 0–4) и раздел 8 (DoD одного шага). Зафиксировано: integration-тесты и `mypy .` (tests) НЕ блокируют старт. Первый шаг — эпик `PS`. Реализацию НЕ начинали. |
| 2026-06-02 | **Волна 2 (тест-блокеры) закрыта параллельно суб-агентами:** EI-0 (`export_import` +15 тестов: DOCX-endpoint, RFC5987 `Content-Disposition`, vault-транзакционность/счётчики, граница 1000 файлов, audit `kb.article_exported_pdf/docx`), LI-0 (`links` 81%→100%, +19), NO-0 (`notifications` 75%→100%, +19, новый `test_notifications_sse_generator.py`: SSE backoff/keepalive/TTL/Last-Event-ID), BR-0 (`branding` 76%→97%, +27: upload/HEAD/cache, `_send_test_email` TLS/STARTTLS, битый JSON+chmod, кросс-SMTP). Только тесты, без правок `app/`. Baseline: 2514 тестов PASS, cov 78.42%, `mypy app` PASS, ruff PASS. Разблокированы структурные шаги EI-1..3/LI-1..4/NO-1..3/BR-1..4. Коммитит пользователь. |
| 2026-06-02 | **Структурный эпик `LI` (links) завершён (LI-1..4):** `api/links.py` (429 LOC) разбит на сервисы `links_query` (conditions/hidden/count), `links_crud` (get_or_404/create/update/delete/reorder/set_icon_url), `links_sso` (build_sso_url), `link_icon` (MIME/optimize/save/remove + константы). Хендлеры стали тонкими (ACL+audit+serialize); добавлен локальный `_emit_link_audit`. Контракт сохранён (пути/коды/event_type/`/media/link_icons/{id}.{ext}`/302+token). Патчи тестов ретаргетированы на `app.services.{links_sso,link_icon}.*` (паттерн EI). Gates: ruff check/format `.` PASS, `mypy app` PASS (268), pytest 2514 PASS, cov **78.46%**; модули LI покрыты 100%. Коммитит пользователь. Следующее по roadmap — `NO` (notifications NO-1..3). |
| 2026-06-02 | **Волна 0 (`PS`) завершена:** PS-1 (модуль→пакет paths/originals/thumbnails/metadata + ре-экспорт; lazy `_ps.<name>` для патчабельных имён), PS-2 (helper'ы `_cascade_resize`/`_encode_thumb`, OOM-логика не тронута), PS-3 (helper `_import_pil`, HEIF только при `register_heif=True`), PS-4 (комментарий `THUMB_SIZES`, тип `extract_exif → dict[str, Any]`). PS-5 (env→Settings) отложен как рискованный. **Волна 1 закрыта:** SE-0 (`search` 53%→98%, 45 тестов) и FO-0 (`folders` 22%→100%, 42 теста) — характеризующие тесты выполнены параллельно суб-агентами. Baseline зелёный: ruff/format/`mypy app`(262) PASS, pytest 2434 PASS, cov 77.44%. Разблокированы SE-1..3, FO-1. |
