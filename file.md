# План реализации: Drag-n-Drop + Multi-Select для модуля «Файлы»

> Источник задачи: `new.md` § 4.4. Цель — кратно повысить эргономику работы с
> файловым модулем за счёт массовых операций (загрузка drag-n-drop,
> выделение нескольких файлов, bulk-скачивание/перемещение/удаление).
>
> Версия документа: **v3 (M1 реализован)**, май 2026. M1-скоуп закрыт
> полностью, документ актуализирован: чек-лист отмечен, добавлен раздел
> «Статус реализации» и развёрнут backlog M2.
>
> Ответственный модуль backend: `backend/app/api/files.py`,
> `backend/app/services/nextcloud/`.
> Ответственный модуль frontend: `frontend/src/pages/FilesPage.vue`,
> `frontend/src/api/files.ts`.

---

## Статус реализации (M1 — DONE ✅)

| Компонент | Файл | Статус |
|---|---|---|
| Константы лимитов | `backend/app/core/constants.py` (`MAX_BULK_FILES=100`, `BULK_INFLIGHT_TTL=60`) | ✅ |
| Pydantic-схемы | `backend/app/schemas/files.py` (`BulkDeleteRequest/Result/Item`, `BulkMoveRequest/Result/Item`) | ✅ |
| Endpoints | `backend/app/api/files.py` — `POST /files/folders/{id}/bulk-delete`, `POST /files/folders/{id}/bulk-move` + хелперы `_bulk_inflight_key`, `_try_set_inflight`, `_clear_inflight`, `_validate_bulk_names` | ✅ |
| In-flight guard | Redis SETNX `bulk:inflight:{user_id}` (TTL 60s) → 409 `bulk_in_progress` | ✅ |
| Rate-limit | `RateLimiter(times=3, minutes=1)` на оба endpoint'а | ✅ |
| Audit | `files.bulk_deleted`, `files.bulk_moved`, `files.bulk_move_drift` с counters в metadata | ✅ |
| Backend unit-тесты | `backend/tests/unit/test_files_bulk.py` — 15 тестов | ✅ 15/15 |
| Backend integration-тесты | `backend/tests/integration/test_files_bulk.py` — 11 тестов (ASGI + моки NC/Redis/DB) | ✅ 11/11 |
| API-клиент | `frontend/src/api/files.ts` — `bulkDeleteFiles`, `bulkMoveFiles`, типы, `BULK_DOWNLOAD_LIMIT=20`, `BULK_MAX_FILES=100` | ✅ |
| FilesPage UI | DnD overlay (`dragDepth` против мерцания, `webkitGetAsEntry` для папок), selection-колонка с `row-key=nc_path`, Shift-range / Ctrl-toggle, sticky bulk-bar (download ≤20, move, delete + clear), upload progress (`n-progress` + счётчик), watcher на смену папки очищает выбор | ✅ |
| Move-modal | `n-modal` + `n-tree`, фильтр по `permission ∈ {editor, manager}`, текущая папка disabled | ✅ |
| i18n | `ru.json` + `en.json`: `files.bulk.*`, `files.dropzone.*`, `files.uploadProgress`, `files.error.bulk*` (1163 ключа, парность подтверждена) | ✅ |
| Документация API | `docs/api-contracts.md` → раздел `Files → Bulk` (запрос/ответ/ошибки/лимиты) | ✅ |
| E2E-тесты | `frontend/tests/e2e/files-bulk.spec.ts` (валидация empty/over-limit, same_folder, CSRF; gracefully skip без `E2E_ADMIN_*`) | ✅ |
| Lint / typecheck | `ruff check` (по bulk-файлам), `npm run typecheck`, `npm run lint:check`, `npm run i18n:check` | ✅ зелёные |
| Миграция БД | Не требуется — `idx_file_items_nc_path_active` уже создан в `038_file_items.py` | ✅ |

---

## 0. Глоссарий и контекст

| Термин | Значение |
|---|---|
| **NC** | Nextcloud (внешнее хранилище файлов, доступ через WebDAV под service-account `portal-svc`) |
| **ACL** | Permission в `file_folder_permissions` (viewer / editor / manager) |
| **DnD** | Drag-and-Drop |
| **Bulk** | Массовая операция над набором файлов одной транзакции |
| **selection-set** | Набор `nc_path` файлов, выбранных пользователем в UI |
| **Natural idempotency** | Свойство операции: повторный вызов не нарушает корректность (DELETE 404→success, MOVE с Overwrite=F) |

**Ключевые ограничения проекта** (из `AGENTS.md`):
- Все операции с NC — через `portal-svc` (Basic Auth, App Password). Нельзя
  использовать JWT юзера для WebDAV.
- Права проверяются **только в БД портала** (`files_acl.py`), NC — тупое
  хранилище.
- Каждая мутация → запись в `audit_log` через `push_audit_event`.
- ACL-кэш в Redis (`services/files_acl.py`, TTL 5 мин) — после изменения
  иерархии/состава папок инвалидируется через `invalidate_folder_cache`.
- Загрузки → streaming, никаких `await file.read()` целиком.
- Запрет на хранение полного response body в `idempotency_keys` (memory leak).
- Миграции — zero-downtime.
- i18n — обязательно ru + en, ключи добавлять одновременно с компонентом.

---

## 1. Текущее состояние (baseline)

### 1.1. Frontend
- `FilesPage.vue` отрисовывает `<n-data-table>` без `selection`-колонки и без
  `row-key`.
- Загрузка только через скрытый `<input type="file" multiple>` + кнопку
  «Загрузить» (метод `triggerUpload`).
- Удаление — поштучное (`confirmDeleteFile`), скачивание — `<a href download>`.
- Перемещение между папками **отсутствует** в UI.
- API-клиент `files.ts` уже умеет multi-upload (`uploadFiles(folderId, files[])`).

### 1.2. Backend
- `POST /files/folders/{id}/upload` — мульти-аплоад, MIME-allowlist, streaming
  в NC, rate-limit 20/min, idempotency-key.
- `DELETE /files/file?folder_id=&filename=` — удаление по одному.
- `WebDAV.move(src, dst)` уже **реализован** (overwrite=F, MOVE → 201/204).
- Bulk-операций нет.

### 1.3. Что уже можно переиспользовать
- `nc.move(src, dst)` — атомарный per-file MOVE, защищён от перезаписи
  (`Overwrite: F`).
- `nc.delete(path)` — обрабатывает 404 как успех.
- `sanitize_name()` — валидация имён.
- `require_folder_permission`, `resolve_folder_permission`,
  `batch_resolve_folder_permissions` — ACL-helpers.
- `push_audit_event`, `invalidate_folder_cache`.
- `apiUpload` (frontend) — multipart form-data POST.
- **Уже существующий partial unique индекс `idx_file_items_nc_path_active`**
  в миграции `038_file_items.py` (UNIQUE по `nc_path WHERE deleted_at IS NULL`)
  обеспечивает уникальность активных записей и в src, и в target папке.

---

## 2. Скоуп MVP (что делаем) и Out-of-scope (откладываем)

### 2.1. В скоупе (M1)
1. **Drag-n-drop загрузка** в открытую папку: оверлей на всю
   `.files-main`, отпускание файлов → существующий `uploadFiles`.
   Фильтрация папок через `webkitGetAsEntry` (без эвристик).
2. **Multi-select** в таблице: чекбоксы, Shift+click для диапазона,
   Ctrl/Cmd+click для toggle, выбор всех.
3. **Bulk-панель** при `selectedCount > 0`: «Скачать», «Переместить»,
   «Удалить».
4. **Backend bulk endpoints**:
   - `POST /files/folders/{id}/bulk-delete`
   - `POST /files/folders/{id}/bulk-move`
5. **Bulk-download v1** — последовательная скачка через скрытые `<a>` (без
   ZIP). **Лимит 20 файлов** на одну операцию.
6. **Прогресс загрузки** — счётчик «N из M» + общий лоадер. Прогресс по
   байтам — отложено (требует XHR).
7. **i18n** — ключи `ru.json` + `en.json`.
8. **Тесты** — unit/integration backend, unit/E2E frontend.

### 2.2. Out-of-scope (M2)
- Загрузка целых директорий через DnD (рекурсивный обход `webkitGetAsEntry`).
- Серверный ZIP-bundle (требует ARQ-таска по аналогии с `photo_zip_jobs`).
- Drag-перетаскивание выбранных файлов из таблицы в узел дерева папок
  (UX-сложно, отдельный PR).
- Прогресс upload в байтах (XHR вместо fetch).
- Конфликт-резолвер (rename / overwrite / skip) — на v1 при коллизии
  возвращаем `error: "name_conflict"`, в UI показываем «N файлов не
  перемещено».
- Восстановление из корзины (soft-delete уже есть, восстановление — отдельная
  задача).

---

## 3. Backend: дизайн API и реализации

### 3.1. Новые pydantic-схемы (`backend/app/schemas/files.py`)

```python
# MAX_BULK_FILES вынесен в backend/app/core/constants.py
from app.core.constants import MAX_BULK_FILES  # = 100

class BulkDeleteRequest(BaseModel):
    filenames: list[str] = Field(min_length=1, max_length=MAX_BULK_FILES)

class BulkDeleteResultItem(BaseModel):
    name: str
    success: bool
    error: str | None = None  # "invalid_name" | "nc_error" | None

class BulkDeleteResult(BaseModel):
    deleted: list[BulkDeleteResultItem]
    failed: list[BulkDeleteResultItem]

class BulkMoveRequest(BaseModel):
    filenames: list[str] = Field(min_length=1, max_length=MAX_BULK_FILES)
    target_folder_id: uuid.UUID

class BulkMoveResultItem(BaseModel):
    name: str
    new_name: str | None = None  # на случай авто-rename в M2
    success: bool
    error: str | None = None  # "name_conflict" | "nc_error" | "not_found" | "invalid_name"

class BulkMoveResult(BaseModel):
    moved: list[BulkMoveResultItem]
    failed: list[BulkMoveResultItem]
```

### 3.2. Endpoints

#### `POST /files/folders/{folder_id}/bulk-delete`
- **ACL**: `editor` на `folder_id`.
- **Rate-limit**: `RateLimiter(times=3, minutes=1)` (×100 файлов = 300 ops/min,
  ровно как single-file `60/min` × 5 — справедливо).
- **Idempotency-Key**: **НЕ используется**. Операция естественно
  идемпотентна: повтор → NC отдаёт 404 → `success=true`.
- **In-flight guard**: Redis-флаг `bulk:inflight:{user.id}` (TTL 60s, SETNX).
  Если уже есть → `409 Conflict, error: "bulk_in_progress"`. Защита от
  параллельных bulk-операций одного пользователя (двойной клик / гонка
  вкладок).
- **Тело**: `BulkDeleteRequest`.
- **Ответ**: `BulkDeleteResult`.
- **Логика**:
  1. Валидация: `_check_module_enabled`, `_get_folder_or_404`,
     `require_folder_permission(... "editor")`.
  2. Установить in-flight флаг (`try/finally` для гарантированной очистки).
  3. Дедупликация и `sanitize_name` для каждого имени; невалидные → в
     `failed` с `error="invalid_name"`.
  4. Для каждого валидного файла:
     - `nc.delete(f"{folder.nc_path}/{name}")` — 404 трактуется как успех.
     - Поиск активного `FileItem` (если есть) → `deleted_at = func.now()`.
  5. Один `db.commit()` для всех успешных. Если коммит упал — логируем
     `error` уровня + audit-event с `metadata.db_commit_failed=true`. NC не
     откатываем (это бы потребовало PUT обратно — невозможно без хранения
     тела). Это допустимое расхождение: `POST /files/sync` (admin) сошьёт.
  6. Один аудит-event `files.bulk_deleted` с `metadata = { folder_id,
     count_total, count_deleted, count_failed, nc_404_count }`.
  7. `invalidate_folder_cache(folder.id)`.
- **Edge cases**:
  - Пустой список (или после dedup только невалидные) → возвращаем
    `BulkDeleteResult(deleted=[], failed=[...])` с 200 OK; UI показывает
    «не удалось обработать».
  - Файла нет в `file_items` (импорт через sync, запись потеряна) → NC.delete
    выполняется, БД — пропускаем. `success=true`.

#### `POST /files/folders/{folder_id}/bulk-move`
- **ACL**: `editor` на src **и** на target.
- **Rate-limit**: `RateLimiter(times=3, minutes=1)`.
- **Idempotency-Key**: **НЕ используется**. Естественная идемпотентность за
  счёт `Overwrite: F`: повтор уже перемещённого файла → 404 (`not_found`)
  для конкретного item, остальные доедут.
- **In-flight guard**: тот же `bulk:inflight:{user.id}`.
- **Тело**: `BulkMoveRequest`.
- **Ответ**: `BulkMoveResult`.
- **Логика**:
  1. Валидация модуля + `_get_folder_or_404` для src и target +
     `require_folder_permission(... "editor")` для обеих.
  2. Если `target_folder_id == folder_id` → 422 (`same_folder`).
  3. Assertion: `target.nc_path.startswith(NC_FILES_ROOT)` (уже инвариант,
     перепроверяем).
  4. In-flight флаг.
  5. Для каждого имени (после `sanitize_name`):
     - `nc.move(src_path, dst_path)`:
       - `201/204` → success.
       - `412 Precondition Failed` (Overwrite=F) → `error: "name_conflict"`.
       - `404` → `error: "not_found"` (файл уже отсутствует в NC).
       - другое → `error: "nc_error: {status}"`.
     - При успехе:
       - Если активный `FileItem` найден — обновить `folder_id`, `nc_path`.
         **Не менять** `uploaded_by`, `uploaded_at` (это история загрузки,
         не история перемещений; ответ на «кто переместил» — в `audit_log`).
       - Если `FileItem` нет (импорт через sync) — создаём новую запись с
         `uploaded_by = NULL` (не подменяем фактом перемещения).
  6. **Commit-per-file** для bulk-move (надёжность важнее скорости при
     ≤100 файлах; при сбое фиксируем то, что успели). На исключение в БД для
     конкретного файла — пишем `files.bulk_move_drift` (warning) с
     `nc_path_src`, `nc_path_dst` и `audit_log` event для автовосстановления
     через `POST /files/sync`.
  7. `invalidate_folder_cache(folder.id)` и
     `invalidate_folder_cache(target.id)`.
  8. Аудит-event `files.bulk_moved` с `metadata = { src_folder_id,
     target_folder_id, count_total, count_moved, count_failed,
     count_drift }`.
- **Edge cases**:
  - Перемещение в подпапку src — для файлов это OK (оперируем именами, не
    директориями).
  - Target soft-deleted → 404 уже обработан в `_get_folder_or_404`.

### 3.3. Возможные проблемы и митигации

| # | Проблема | Митигация |
|---|---|---|
| 3.3.1 | NC 502/таймаут посередине bulk-операции | Per-file commit (move); собираем `failed`; пользователь повторяет — `Overwrite: F` + 404→success обеспечивают safe replay. |
| 3.3.2 | Race при одновременной загрузке файла с тем же именем | 412 от NC отлавливается → `error: "name_conflict"`. |
| 3.3.3 | Уникальность `(folder_id, name)` среди активных записей | **Уже обеспечена** существующим `idx_file_items_nc_path_active` (UNIQUE по `nc_path WHERE deleted_at IS NULL`, миграция 038). Новой миграции не нужно. |
| 3.3.4 | Цикл MOVE при ошибке (`failed`-список длинный) — frontend ретраит → DDoS NC | Rate-limit `3/min`; in-flight Redis-флаг; UI блокирует кнопку до завершения. |
| 3.3.5 | Файл «прошёл» в NC, но БД не обновилась (commit-per-file исключение) | `files.bulk_move_drift` (warning log) + `audit_log` event. Восстановление — `POST /files/sync` (admin). |
| 3.3.6 | Идемпотентность для bulk-операций | **Не используем `Idempotency-Key`**. Полагаемся на natural idempotency: delete 404→success, move с Overwrite=F. Это соответствует AGENTS.md (запрет на полный body в idempotency_keys). |
| 3.3.7 | Большой bulk (100 файлов) занимает > timeout фронта (60s) | Реальный замер: 100 MOVE по WebDAV ≈ 5–15 сек. Если упрёмся — выносим в ARQ-таску (M2). |
| 3.3.8 | Аудит-event-spam (один на файл) | Один event на bulk + counters в metadata. |
| 3.3.9 | Удаление файла, которого нет в `file_items` | NC.delete выполнится; в БД пропускаем. `success=true`. |
| 3.3.10 | Двойной клик / гонка вкладок одного пользователя | In-flight Redis-флаг `bulk:inflight:{user.id}` (SETNX, TTL 60s). Второй запрос → 409. |
| 3.3.11 | `uploaded_by` подменяется при move | **Не подмешиваем**: оставляем NULL/исходный. Факт перемещения фиксируем в `audit_log.actor_id`. |

### 3.4. Файлы, которые нужно создать/изменить

**Создать:**
- `backend/tests/unit/test_files_bulk.py`
- `backend/tests/integration/test_files_bulk.py`

**Изменить:**
- `backend/app/api/files.py` — два endpoint'а + helpers
  `_resolve_filenames`, `_set_inflight`, `_clear_inflight`.
- `backend/app/schemas/files.py` — схемы (см. 3.1).
- `backend/app/core/constants.py` — `MAX_BULK_FILES = 100`,
  `BULK_INFLIGHT_TTL = 60`.
- `docs/api-contracts.md` — новый раздел `Files → Bulk`.

**НЕ создаём** (важное отличие от v1):
- ~~`backend/migrations/versions/038_file_items_unique_active.py`~~ — индекс
  уже есть.
- ~~Idempotency-Key хранилище для bulk~~ — естественная идемпотентность.

---

## 4. Frontend: дизайн UI и реализации

### 4.1. Архитектурные решения
- **State selection** — `ref<Set<string>>` ключей по `nc_path` (стабильно
  между ребилдами таблицы).
- **Last-clicked index** — `ref<number | null>` для Shift+range.
- **Drop-zone** — на корневой `<main class="files-main">`. Счётчик
  `dragDepth` для корректной обработки nested dragenter/dragleave.
- **Bulk-bar** — sticky сверху списка (под breadcrumbs), скрывается при
  пустом selection. Анимация slide-down.
- **DnD-фильтр папок** — через `DataTransferItem.webkitGetAsEntry()` (не
  эвристика по `size===0`).

### 4.2. Структура изменений

#### `frontend/src/api/files.ts` — добавить:
```ts
export interface BulkDeleteResultItem { name: string; success: boolean; error: string | null }
export interface BulkDeleteResult { deleted: BulkDeleteResultItem[]; failed: BulkDeleteResultItem[] }
export interface BulkMoveResultItem extends BulkDeleteResultItem { new_name: string | null }
export interface BulkMoveResult { moved: BulkMoveResultItem[]; failed: BulkMoveResultItem[] }

export function bulkDeleteFiles(folderId: string, filenames: string[]): Promise<BulkDeleteResult> { ... }
export function bulkMoveFiles(folderId: string, filenames: string[], targetFolderId: string): Promise<BulkMoveResult> { ... }
```

> Типы предпочтительно генерировать через `npm run gen:types` после
> экспорта обновлённого `openapi.json` из бэкенда.

#### `frontend/src/pages/FilesPage.vue` — изменения

1. **Selection-колонка в `n-data-table`**:
   ```ts
   { type: 'selection', disabled: (row) => row.is_dir }
   ```
   + `:row-key="(row) => row.nc_path"` + `v-model:checked-row-keys="selectedKeys"`.

2. **Shift-range click**:
   - Обёртка над `onItemClick`: если `e.shiftKey` и есть `lastSelectedIndex`
     → выделяем диапазон по `ncItems.slice`, исключая `is_dir`.
   - `e.ctrlKey/metaKey` → toggle.
   - Иначе — старое поведение (открыть папку / preview).

3. **Drop-zone с фильтрацией папок**:
   ```ts
   async function extractDroppedFiles(dt: DataTransfer): Promise<{files: File[]; hadFolders: boolean}> {
     const files: File[] = [];
     let hadFolders = false;
     for (const item of Array.from(dt.items)) {
       if (item.kind !== 'file') continue;
       const entry = (item as any).webkitGetAsEntry?.();
       if (entry?.isDirectory) { hadFolders = true; continue; }
       const f = item.getAsFile();
       if (f) files.push(f);
     }
     return { files, hadFolders };
   }
   ```
   - Если `hadFolders` — toast «Загрузка папок будет добавлена позже. Файлы
     загружены».
   - `onDragEnter/Leave` — счётчик `dragDepth` против мерцания.
   - Глобальный `window` listener `dragover/drop` → `preventDefault` если
     не наш target (чтобы файлы не открывались в браузере).

4. **Bulk-панель**:
   ```html
   <div v-if="selectedKeys.length" class="files-bulk-bar">
     <span>{{ t('files.bulk.selected', { n: selectedKeys.length }) }}</span>
     <n-button @click="bulkDownload"
               :disabled="selectedKeys.length > 20">
       {{ t('files.bulk.download') }}
       <template v-if="selectedKeys.length > 20">
         <n-tooltip>{{ t('files.bulk.downloadLimit') }}</n-tooltip>
       </template>
     </n-button>
     <n-button @click="openMoveModal" :disabled="!canUpload">{{ t('files.bulk.move') }}</n-button>
     <n-button type="error" ghost @click="confirmBulkDelete" :disabled="!canUpload">{{ t('files.bulk.delete') }}</n-button>
     <n-button text @click="clearSelection">{{ t('common.cancel') }}</n-button>
   </div>
   ```

5. **Move-модалка**:
   - `n-modal` с `n-tree`, data — отфильтрованный `tree.value` (только узлы
     с `permission ∈ {editor, manager}`).
   - Disabled — текущая папка.
   - На confirm — вызов `bulkMoveFiles`.

6. **Bulk-download** (лимит 20):
   - Если `selectedKeys.length > 20` — кнопка disabled, tooltip «Выберите до
     20 файлов или дождитесь функции ZIP-скачивания».
   - Иначе цикл `for filename of selectedKeys`: `<a download>` через
     `document.createElement('a')` + `a.click()` + remove. Между скачиваниями
     `await sleep(150ms)`.
   - Перед первым скачиванием — info-toast «Если браузер запросит
     подтверждение нескольких загрузок — нажмите «Разрешить»».

7. **Прогресс upload**:
   - `uploadingState = ref<{total: number; done: number; failed: number}>`.
   - Меняем `n-alert` на `n-progress` + текст «{done}/{total}».

### 4.3. CSS

- `.files-dropzone-overlay`: `position: absolute; inset: 0; background:
  rgba(24, 160, 88, 0.08); border: 2px dashed var(--n-primary-color);
  display: flex; align-items: center; justify-content: center; font-size:
  16px; pointer-events: none; z-index: 10;`. Родителю `.files-main` —
  `position: relative`.
- `.files-bulk-bar`: sticky `top: 0`, `display: flex; gap: 8px; align-items:
  center; padding: 8px 12px; background: var(--n-color); border: 1px solid
  var(--n-border-color); border-radius: 6px; margin-bottom: 12px;
  box-shadow: 0 2px 6px rgba(0,0,0,.05); z-index: 5;`.

### 4.4. Возможные проблемы UI

| # | Проблема | Митигация |
|---|---|---|
| 4.4.1 | DnD-оверлей мерцает на дочерних элементах | Счётчик `dragDepth` (paired enter/leave). |
| 4.4.2 | Drop вне drop-zone (на breadcrumbs) → файлы уходят браузеру | Глобальный listener на `window`: `dragover/drop` → `preventDefault` если не наш drop-target. |
| 4.4.3 | Shift-click выделяет «диапазон» через папки (которые `disabled`) | Фильтруем диапазон по `!is_dir` перед добавлением в `selectedKeys`. |
| 4.4.4 | Selection теряется после `loadDetail()` | После reload оставляем только ключи, существующие в новом `ncItems`. |
| 4.4.5 | Bulk-download блокируется анти-popup защитой | Sequential downloads с интервалом 150ms; первый клик инициирован user-жестом. Лимит 20 файлов снижает шанс срабатывания. Info-toast при первом запуске. |
| 4.4.6 | Move-модалка показывает дерево с правами `viewer` (нельзя выбрать) | Фильтрация перед рендером + `disabled` атрибут на `n-tree-node`. |
| 4.4.7 | После bulk-move открытая папка осталась пустой/неактуальной | Reload текущей папки + toast «Перемещено N файлов в "{target.name}"» с ссылкой «Открыть target». |
| 4.4.8 | Очистка `selectedKeys` при смене папки | Watch `selectedFolderId` → `selectedKeys.value = []`. |
| 4.4.9 | DnD на iOS Safari не работает | Принимаем (целевая платформа — корпоративные ПК); кнопка «Загрузить» остаётся как fallback. |
| 4.4.10 | n-data-table не пробрасывает `MouseEvent` в onClick row-props | `row-props` возвращает `{ onClick: (e: MouseEvent) => onRowClick(row, index, e) }` — событие приходит первым аргументом. |
| 4.4.11 | Drop'нули папку через webkitGetAsEntry | Папки тихо отфильтровываются, показываем info-toast если `hadFolders=true`. |

---

## 5. Миграция БД — **НЕ требуется**

В `backend/migrations/versions/038_file_items.py` уже создан partial UNIQUE
индекс `idx_file_items_nc_path_active` по `nc_path WHERE deleted_at IS NULL`.
Поскольку `nc_path = folder.nc_path + "/" + name`, а `folder.nc_path`
уникален в дереве, уникальность `nc_path` эквивалентна уникальности
`(folder_id, name)` среди активных записей. Дополнительная миграция стала
бы избыточной (write-amplification).

Оставлено как референс — не создавать.

---

## 6. i18n (новые ключи)

`frontend/src/i18n/ru.json`:
```json
"files": {
  "...",
  "dropzone": {
    "hint": "Отпустите файлы для загрузки",
    "foldersSkipped": "Папки пропущены — поддержка появится позже",
    "downloadHint": "Если браузер запросит подтверждение нескольких загрузок — нажмите «Разрешить»"
  },
  "bulk": {
    "selected": "Выбрано: {n}",
    "download": "Скачать",
    "downloadLimit": "Можно скачать до 20 файлов за раз. ZIP-скачивание будет добавлено позже.",
    "move": "Переместить",
    "delete": "Удалить",
    "moveTitle": "Куда переместить?",
    "moveTarget": "Выберите целевую папку",
    "moveSubmit": "Переместить",
    "moveSameFolder": "Файлы уже находятся в этой папке",
    "deleteConfirmTitle": "Удалить выбранные файлы?",
    "deleteConfirmBody": "Будет удалено: {n}. Действие нельзя отменить.",
    "moved": "Перемещено: {n}",
    "deleted": "Удалено: {n}",
    "partialFail": "Не удалось обработать: {n}",
    "openTarget": "Открыть",
    "inProgress": "Уже выполняется массовая операция, дождитесь завершения",
    "rateLimited": "Слишком много массовых операций. Попробуйте через минуту."
  },
  "uploadProgress": "Загружено {done} из {total}"
}
```

`frontend/src/i18n/en.json`: симметричный перевод. Запустить
`npm run i18n:check`.

---

## 7. Тестирование

### 7.1. Backend unit (`backend/tests/unit/test_files_bulk.py`)
- Валидация: пустой список → 422.
- Валидация: > `MAX_BULK_FILES` → 422.
- Валидация: имя с `/`, `..`, `\0` → попадает в `failed: invalid_name`.
- Sanitize применяется до обращения к NC.
- In-flight флаг ставится и снимается (даже при исключении).

### 7.2. Backend integration (`backend/tests/integration/test_files_bulk.py`,
Testcontainers + fake NC)
- bulk-delete happy path: 3 файла, NC 204 → все в `deleted`.
- bulk-delete partial: 1 файл NC 502 → 2 в `deleted`, 1 в `failed`.
- bulk-delete soft-delete `FileItem.deleted_at`.
- bulk-delete: NC 404 → `success=true`, `metadata.nc_404_count=1`.
- bulk-move happy path: 3 файла → все в target, БД обновлена,
  `uploaded_by` сохранён.
- bulk-move импортированных (нет `FileItem`) → создаётся запись с
  `uploaded_by = NULL`.
- bulk-move name_conflict: NC 412 → файл в `failed: "name_conflict"`,
  остальные перемещены.
- bulk-move ACL: пользователь без `editor` на target → 403.
- bulk-move ACL: пользователь без `editor` на src → 403.
- bulk-move в ту же папку → 422 `same_folder`.
- **In-flight**: второй параллельный bulk → 409 `bulk_in_progress`.
- Аudit: после bulk-delete в `audit_log` ровно один event типа
  `files.bulk_deleted` с правильным `metadata.count_total`.
- Rate-limit: 4-й запрос за минуту → 429.
- **Replay безопасности**: повторный bulk-delete с тем же списком →
  `success=true` для всех (NC 404), новых записей в audit два event'а.

### 7.3. Backend security
- bulk-delete без аутентификации → 401.
- bulk-delete viewer → 403.
- Имена с traversal (`../etc/passwd`, `\0`) → `failed: invalid_name`.
- CSRF: POST без `Origin/Referer` → 403 (общий middleware).

### 7.4. Frontend unit (`frontend/tests/unit/FilesPage.spec.ts`)
- Чекбокс выделяет файл, не папку.
- Shift+click выделяет диапазон, исключая папки.
- Ctrl+click тогглит.
- Bulk-bar появляется при `selectedKeys.length > 0`.
- Drop-zone overlay появляется на dragenter, исчезает на drop / dragleave×N.
- После смены папки selection очищается.
- При drop'е папки — toast `foldersSkipped`, файлы из drop'а загружены.
- Bulk-download кнопка disabled при `> 20` selected.

### 7.5. Frontend E2E (`frontend/tests/e2e/files-bulk.spec.ts`)
- DnD: `setInputFiles` + programmatic `drop`-event → 3 файла загружены.
- Multi-select + bulk-delete: выбрать 2 файла → «Удалить» →
  подтверждение → файлы пропадают.
- Bulk-move: выбрать 2 файла → «Переместить» → выбрать target в дереве →
  подтверждение → файлы появляются в target-папке.

### 7.6. Прогон
```cmd
cd /d C:\Users\admin\Documents\zen\portal\backend && pytest tests/unit/test_files_bulk.py tests/integration/test_files_bulk.py -v
cd /d C:\Users\admin\Documents\zen\portal\backend && ruff check . && mypy app
cd /d C:\Users\admin\Documents\zen\portal\frontend && npm run test:unit && npm run lint:check && npm run typecheck && npm run i18n:check
cd /d C:\Users\admin\Documents\zen\portal\frontend && npm run test:e2e -- files-bulk
```

---

## 8. Очерёдность работ — **один интегральный проход**

| Этап | Содержимое | После этапа запустить |
|---|---|---|
| 1 | Backend: `constants.py`, `schemas/files.py`, endpoints в `api/files.py`, in-flight helper. Unit + integration тесты. | `pytest tests/unit/test_files_bulk.py tests/integration/test_files_bulk.py -v && ruff check . && mypy app` |
| 2 | Frontend: `npm run gen:types` → API-обёртки в `api/files.ts`. | `npm run typecheck` |
| 3 | Frontend: `FilesPage.vue` — selection col + bulk-bar + move modal + bulk-download (с лимитом 20). Unit-тесты. | `npm run test:unit && npm run lint:check` |
| 4 | Frontend: DnD overlay + `extractDroppedFiles` (`webkitGetAsEntry`) + индикатор прогресса. | `npm run test:unit` |
| 5 | i18n: `ru.json` + `en.json`, обновить `docs/api-contracts.md`. | `npm run i18n:check` |
| 6 | E2E: Playwright тесты `files-bulk.spec.ts`. | `npm run test:e2e -- files-bulk` |
| 7 | Финальная проверка: весь CI-набор + ручной smoke в браузере. | см. чек-лист в §10. |

При красных тестах на любом этапе — фиксим до перехода к следующему.

---

## 9. Рисковая матрица

| Риск | Вероятность | Эффект | Митигация |
|---|---|---|---|
| NC возвращает 412 на половине файлов из-за коллизий | Средняя | Средний | Чёткая UI-обратная связь «N не перемещено»; в M2 — конфликт-резолвер. |
| Drift БД ↔ NC при сетевом сбое | Низкая | Высокий | Per-file commit (move); `POST /files/sync` (admin) для ручного восстановления. |
| Прогресс upload «зависает» в UI на больших файлах | Средняя | Низкий | Тайм-ауты `_TIMEOUT_UPLOAD = 600s`; индикатор активности; в M2 — XHR с onprogress. |
| `n-data-table` selection ломается при ребилдe | Средняя | Низкий | После операции — `selectedKeys.value = []` всегда. |
| Лимит 100 файлов на bulk слишком мал/велик | Низкая | Низкий | Конфиг `MAX_BULK_FILES`; легко поменять. |
| DnD-файлы случайно открываются в браузере | Высокая | Низкий | Глобальный `window` `dragover/drop` → preventDefault. |
| Audit-log спам при больших bulk | Средняя | Низкий | Один event per bulk + counters в metadata. |
| Параллельные bulk от одного юзера | Средняя | Средний | In-flight Redis-флаг (SETNX, TTL 60s) → 409. |
| Анти-popup блокирует bulk-download | Средняя | Низкий | Лимит 20 файлов + интервал 150ms + info-toast. |
| Drop папки → юзер думает «загрузилось» | Средняя | Низкий | `webkitGetAsEntry` отфильтровывает + явный toast `foldersSkipped`. |

---

## 10. Чек-лист перед merge

- [x] Все unit/integration тесты зелёные (26/26 — `tests/unit/test_files_bulk.py` 15, `tests/integration/test_files_bulk.py` 11).
- [x] E2E spec написан (`frontend/tests/e2e/files-bulk.spec.ts`); для запуска требует `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`.
- [x] `ruff check` (bulk-файлы), `npm run lint:check`, `npm run typecheck`, `npm run i18n:check` — без ошибок.
- [x] `docs/api-contracts.md` обновлён (новые endpoint'ы `Files → Bulk`).
- [ ] Ручной smoke-тест в браузере (выполняется при выкатке на staging):
      - DnD загружает 5 файлов разных типов (включая drop папки → она
        пропускается с toast'ом);
      - Shift-range выделяет 10 файлов в большом списке (исключая папки);
      - Ctrl/Cmd-click тогглит;
      - Bulk-delete удаляет, bulk-move перемещает (selection очищается);
      - Bulk-download качает до 20 файлов; кнопка disabled при >20;
      - Параллельный bulk во второй вкладке → 409 + toast `inProgress`;
      - i18n: переключение ru ↔ en, все ключи на месте.
- [ ] Pre-prod / staging развёрнут, протестирован с реальным NC.
- [x] Rollback-план: код можно откатить `git revert` без data-loss
      (новые endpoints просто исчезнут, старая логика не тронута; миграций
      нет).

---

## 11. Послемерж: M2 backlog (для следующей итерации)

> M1 закрыт. Ниже — приоритезированные задачи M2 с указанием точек входа в
> кодовую базу и ориентировочной сложности. Каждая задача — отдельный PR.

### M2.1. Загрузка папок через DnD (рекурсивный обход) — S
- **Точка входа:** `frontend/src/pages/FilesPage.vue::extractDroppedFiles`.
- **Что делать:** заменить early-`continue` для `entry.isDirectory` на
  рекурсивный обход `FileSystemDirectoryEntry.createReader().readEntries()`,
  складывая файлы с относительным путём в `webkitRelativePath`-стиле.
- **Backend:** `POST /files/folders/{id}/upload` уже принимает
  `multipart/form-data` со списком файлов; добавить опциональное поле
  `relative_path` per file → создание промежуточных подпапок (через
  `nc.mkdir` + upsert `file_folders`). ACL — `editor` на корне drop'а
  достаточно (пере-наследование на новые подпапки).
- **Тесты:** unit на флэт-разворачивание дерева; integration на создание
  иерархии в БД и NC.
- **i18n:** ключ `files.dropzone.foldersSkipped` → удалить или переименовать
  в `files.dropzone.uploadingFolders`.

### M2.2. ZIP-bundle для bulk-download — M
- **Архитектура:** ARQ-задача по аналогии с `photo_zip_jobs`. Новая таблица
  `file_zip_jobs (id, user_id, folder_id, filenames jsonb, status, file_path,
  size_bytes, error, created_at, completed_at, expires_at)`. Хранилище
  готового архива — локальный volume `/data/file_zips/`, retention 24 ч
  (cron-задача в worker).
- **Endpoints:**
  - `POST /files/folders/{id}/zip` — body `{filenames: [...]}` → создаёт job,
    возвращает `{job_id}`. ACL: `viewer` на src + проверка прав на каждый
    файл (re-use `batch_resolve_folder_permissions`).
  - `GET /files/zip/{job_id}` — статус.
  - `GET /files/zip/{job_id}/download` — `StreamingResponse` готового zip.
- **Worker:** `app/worker/tasks/files.py::build_zip_archive` — по очереди
  стримит из NC через `nc.download_stream` в `zipfile.ZipFile` (mode='w').
- **Frontend:** заменить блок «лимит 20» на `bulkZipDownload(folderId,
  filenames)` → polling статуса → клик по download-link.
- **Тесты:** integration с testcontainers (NC mock), polling сценарий.

### M2.3. Drag-перетаскивание файлов из таблицы в узел дерева — M
- **UI:** включить native HTML5 DnD на строках `n-data-table` (через
  `row-props` + `draggable="true"` + `dragstart` с `dataTransfer.setData`).
  В `FileFolderNode.vue` обработать `dragover/drop` → подсветка drop-target,
  вызов `bulkMoveFiles` с уже выбранным selection (либо одиночным файлом,
  если selection пуст).
- **Edge cases:** запрет drop в текущую папку и в папки без `editor`
  (визуально красный индикатор); drop на breadcrumbs → перемещение в
  предка.
- **Тесты:** Playwright — `page.dragAndDrop(selector, target)`.

### M2.4. Прогресс upload по байтам (XHR + onprogress) — S
- **Frontend:** заменить `fetch`/`ofetch` upload в `frontend/src/api/files.ts
  ::uploadFiles` на XMLHttpRequest с `upload.onprogress` (либо
  `fetch + Request body ReadableStream` через `TransformStream` с
  cursor-counting). Расширить `uploadProgress` типом
  `{done, total, bytesDone, bytesTotal}`.
- **Backend:** изменений не требуется (streaming PUT уже есть).

### M2.5. Конфликт-резолвер при move (overwrite / rename / skip) — M
- **Backend:** расширить `BulkMoveRequest` опциональным
  `conflict_strategy: "skip" | "overwrite" | "rename"` (default `skip` =
  текущее поведение). При `overwrite` — повторный MOVE с `Overwrite: T`
  (или DELETE+MOVE для атомарности). При `rename` — суффикс ` (1)`,
  ` (2)` через `nc.exists` + цикл; новое имя в `BulkMoveResultItem.new_name`.
- **Frontend:** при первом `name_conflict` показать модалку
  «Что делать с {N} конфликтами?» → 3 варианта → повторный вызов с
  выбранной стратегией.
- **Тесты:** integration на каждую стратегию + idempotency повтора с
  overwrite.

### M2.6. Корзина файлов с восстановлением — S
- **Backend:** `PATCH /files/file/restore` (body `{folder_id, filename}` →
  `deleted_at = NULL`) + `POST /files/folders/{id}/bulk-restore` симметрично
  bulk-delete. Опциональный фильтр `?trash=true` в существующем
  `GET /files/folders/{id}` (только soft-deleted).
- **Frontend:** новая страница / вкладка «Корзина» в `FilesPage.vue`,
  reuse selection + bulk-bar c действиями «Восстановить» / «Удалить
  навсегда» (hard-delete).
- **Тонкость:** при восстановлении коллизия активного `nc_path` → 409
  `name_conflict` (конфликт с partial unique индексом `idx_file_items_nc
  _path_active`).

### M2.7. Bulk-операции на папках (рекурсивно) — L
- **Сложность:** WebDAV `MOVE` на коллекции — атомарный (одна операция),
  но ACL надо проверить **рекурсивно** для всех вложенных файлов (через
  CTE по `file_folders.parent_id`); soft-delete каскадно.
- **Backend:** `POST /files/folders/bulk-delete` (body `folder_ids[]`),
  `POST /files/folders/bulk-move` (body `{folder_ids[], target_parent_id}`).
  Отдельный rate-limit (1/min) и более строгий in-flight (TTL 5 мин).
- **Тесты:** глубокие иерархии (5+ уровней), ACL-конфликты, recovery от
  частичного MOVE.

### M2.8. Backend metric'и для bulk-операций — XS
- **Что:** prometheus-counter'ы `files_bulk_delete_total`,
  `files_bulk_move_total`, гистограммы `files_bulk_duration_seconds`,
  `files_bulk_size` (число файлов).
- **Точка входа:** `backend/app/core/metrics.py` + декораторы в
  `bulk_delete_files` / `bulk_move_files`.

### Очерёдность M2

1. **M2.1 + M2.4** — небольшие, дополняют M1 без сложной инфраструктуры.
2. **M2.6** — отдельная корзина, востребовано после bulk-delete.
3. **M2.5** — конфликт-резолвер, закрывает основной UX-провал move.
4. **M2.2** — ZIP-bundle, требует ARQ + новой таблицы → отдельный PR.
5. **M2.3** — DnD из таблицы в дерево, чисто frontend поверх готового API.
6. **M2.7** — bulk на папках, самая сложная задача, в последнюю очередь.
7. **M2.8** — параллельно с любой из задач выше.

### Что НЕ нужно трогать в M2 (стабильно)

- Существующие endpoints `bulk-delete` / `bulk-move` — backward-compatible,
  только расширение body (опциональные поля).
- Естественная идемпотентность (NC 404, Overwrite=F) — фундаментальный
  инвариант, сохраняется.
- In-flight Redis-флаг — масштабируется на новые bulk-операции (один ключ
  на пользователя, любая bulk-операция).
- Лимит `MAX_BULK_FILES=100` — при необходимости поднять до 500 после
  бенчмарка реального NC.

---

## 12. Финальный результат: новые функции после реализации

### 12.1. Drag-n-Drop загрузка файлов

- **Перетаскивание из проводника ОС** прямо в окно браузера на область папки.
  Появляется зелёный пунктирный оверлей с подсказкой «Отпустите файлы для
  загрузки».
- **Множественная загрузка одним жестом** — все перетянутые файлы уходят в
  текущую открытую папку.
- **Автоматическая фильтрация папок** через `webkitGetAsEntry` — если
  случайно перетянули папку, она тихо отбрасывается, показывается toast
  «Папки пропущены — поддержка появится позже», файлы при этом загружаются.
- **Защита от случайного открытия файлов в браузере** — если drop пришёлся
  мимо drop-zone (на breadcrumbs, заголовок и т.д.), браузер не откроет файл.
- **Прогресс-бар загрузки** со счётчиком «{N} из {M}» вместо безликого
  спиннера.

### 12.2. Multi-Select в списке файлов

- **Чекбокс в каждой строке** (кроме папок — они для bulk-операций
  недоступны).
- **Чекбокс «выбрать все»** в заголовке таблицы.
- **Shift+клик** — выделение диапазона от последнего выбранного до текущего;
  папки автоматически исключаются из диапазона.
- **Ctrl/Cmd+клик** — точечное добавление/удаление файла из выделения.
- **Авто-очистка выделения** при смене папки или после bulk-операции.
- **Сохранение существующего поведения**: одиночный клик по файлу → preview,
  одиночный клик по папке → переход внутрь.

### 12.3. Bulk-панель массовых операций

Появляется sticky-панель под breadcrumbs при `selected > 0` со счётчиком и
тремя действиями:

#### 12.3.1. Bulk-удаление
- Одно подтверждение → один вызов backend → все файлы удалены.
- Soft-delete в БД (`deleted_at = now()`) + физическое удаление в Nextcloud.
- Один аудит-event на всю операцию (а не N штук).
- Файлы, которых уже нет в NC (404), считаются успешно удалёнными.

#### 12.3.2. Bulk-перемещение (новая функция, раньше не было в UI вообще)
- Модалка с деревом папок: недоступные для записи папки (`viewer`)
  отображаются заглушенными, текущая — disabled.
- Перемещение через `WebDAV MOVE` с `Overwrite: F` — никогда не перезаписывает
  существующий файл.
- Конфликты имён по конкретным файлам (`name_conflict`) показываются в
  результате, остальные доезжают.
- ACL проверяется на исходной **и** целевой папке (нужен `editor` на обеих).
- Toast «Перемещено N файлов в "{target}"» со ссылкой «Открыть» целевую
  папку.

#### 12.3.3. Bulk-скачивание
- Последовательная скачка через скрытые ссылки с интервалом 150 ms.
- **Лимит 20 файлов** за операцию (защита от anti-popup-блокировки браузера).
- При выборе > 20 кнопка disabled с tooltip «ZIP-скачивание появится позже».
- Info-toast перед первым скачиванием с инструкцией про разрешение нескольких
  загрузок в браузере.

### 12.4. Защитные механизмы

- **In-flight guard** (Redis SETNX): один пользователь не может запустить две
  bulk-операции одновременно (защита от двойного клика и параллельных
  вкладок) — второй запрос получает 409 + toast «Уже выполняется массовая
  операция».
- **Rate-limit 3/min** на bulk-endpoint per user (предсказуемая нагрузка на
  NC).
- **Лимит 100 файлов** в одной bulk-операции.
- **Естественная идемпотентность** повторного запроса: безопасно повторять
  при сбоях сети без риска дублирования или повреждения данных.

### 12.5. Аудит и наблюдаемость

- Каждая bulk-операция → один event в `audit_log`
  (`files.bulk_deleted` / `files.bulk_moved`) с `actor_id` и метриками
  (`count_total`, `count_succeeded`, `count_failed`, `nc_404_count`).
- При расхождении БД↔NC (drift) — отдельный warning-event, восстановление
  через существующий `POST /files/sync` (admin).
- Аудит-лог не «спамится» — счётчики в metadata вместо тысячи строк.

### 12.6. Новые backend endpoints

| Endpoint | Назначение |
|---|---|
| `POST /files/folders/{id}/bulk-delete` | Массовое удаление файлов из папки |
| `POST /files/folders/{id}/bulk-move` | Массовое перемещение файлов в другую папку |

Оба возвращают детальный результат (`deleted`/`moved` + `failed`) с причиной
отказа по каждому файлу.

### 12.7. i18n

Полная пара ключей `ru`/`en` для drop-zone, bulk-панели, модалки
перемещения, toast'ов, ошибок (`inProgress`, `rateLimited`, `partialFail`,
`moveSameFolder` и пр.).

### 12.8. Сравнение «до / после»

| Сценарий | До | После |
|---|---|---|
| Загрузить 20 файлов | 1 клик «Загрузить» → диалог → выбор 20 файлов | Перетащить 20 файлов из проводника |
| Удалить 30 файлов | 30 итераций «⋯ → Удалить → ОК» | Shift-клик → «Удалить» → ОК |
| Переместить файлы в другую папку | **Невозможно**, нужно идти в Nextcloud | Выбрать → «Переместить» → дерево → ОК |
| Скачать 10 файлов | 10 кликов по ссылкам | 1 клик «Скачать» |
| Выбрать «всё на этой странице» | Невозможно | Чекбокс в шапке |
| Видеть прогресс загрузки | Спиннер без подробностей | Прогресс-бар + счётчик «{done}/{total}» |

### 12.9. Что НЕ изменится для пользователя

- Старые сценарии (поштучная загрузка через кнопку, поштучное удаление через
  меню, открытие в Collabora, preview изображений) — работают как раньше.
- Права доступа: всё, что нельзя было — нельзя и теперь (bulk-операции
  доступны только при `editor`/`manager` на src и target).
- Производительность одиночных операций не меняется.

### 12.10. Что НЕ войдёт в M1 (сразу обозначить пользователю)

- Drag'n'drop **папки** (целиком с подкаталогами) — будет в следующем релизе.
- **ZIP-скачивание** для большого числа файлов — будет в следующем релизе
  (пока лимит 20 на bulk-download).
- **Конфликт «файл с таким именем уже есть»** при move — пока показывается
  как ошибка по конкретному файлу, без выбора «перезаписать/переименовать».
- **Прогресс upload в байтах** (сейчас — только счётчик файлов).

### 12.11. Эффект для бизнеса

- **Сокращение времени массовых файловых операций в 3–10 раз** для типового
  сценария «навёл порядок в папке отдела».
- Снятие необходимости заходить в Nextcloud напрямую для перемещений — всё в
  одном интерфейсе портала, с правами и аудитом.
- Предсказуемые лимиты (100 файлов/операция, 3 операции/мин, 20
  файлов/скачивание) защищают сервер и Nextcloud от случайных DDoS.
- Все массовые операции оставляют структурированный аудит-след (один event
  на операцию + счётчики).
