# ТЗ 2.1.a — Декомпозиция `pages/FilesPage.vue`

> **Источник:** `ref.md`, пункт 2.1.a (раздел 2.1 «Монстр-компоненты»).
> **Цель:** разбить `frontend/src/pages/FilesPage.vue` (1111 строк) на оркестратор + набор фокусированных компонентов и composables. Состояние, общее между несколькими частями, перенести в Pinia-store `useFilesStore`.
> **Сложность:** ●●● • **Риск:** высокий • **Оценка:** 16–24 ч.
> **Связки:** пересекается с задачей 2.3 (вынос API-вызовов из компонентов в store-actions/composables) и 2.8 (унификация data-fetching).

---

## 1. Текущее состояние

### 1.1 Файл `.\frontend\src\pages\FilesPage.vue` — 1111 строк

Содержит:

- **Шаблон (≈ 230 строк):** sidebar с деревом папок, main-зона с breadcrumbs, toolbar, прогресс-баром аплоада, bulk-bar, таблицей (`n-data-table` + 6 колонок с render-функциями), модалкой создания папки, bulk-move-модалкой, нативным `<input type="file">`, drop-overlay, image-preview.
- **Скрипт (≈ 660 строк):** все ниже-перечисленные ответственности в одном `<script setup>`.
- **Стили (≈ 200 строк):** scoped CSS для всех вышеперечисленных подзон.

### 1.2 Перечень ответственностей (текущие функции / реактивные источники)

| # | Ответственность | Реактивные источники | Функции |
|---|------------------|----------------------|---------|
| 1 | Дерево папок | `tree`, `loadingTree`, `selectedFolderId` | `loadTree`, `selectFolder`, `findNodeByNcPath`, `findNodeById` |
| 2 | Sync с Nextcloud | `syncing` | `syncFromNc` |
| 3 | Содержимое текущей папки (детали) | `currentFolder`, `ncItems`, `breadcrumbs`, `loadingDetail` | `loadDetail` |
| 4 | CRUD папок | `showCreateModal`, `createParentId`, `creating`, `createForm`, `permsForFolderId`, `showPermsModal` | `openCreateRoot`, `openCreateChild`, `submitCreate`, `confirmDeleteFolder`, `openManage` |
| 5 | Аплоад файлов (input + DnD) | `uploading`, `uploadProgress`, `fileInputRef`, `dragDepth`, `dndActive` | `triggerUpload`, `handleFileInput`, `runUpload`, `onMainDragEnter`, `onMainDragOver`, `onMainDragLeave`, `onMainDrop`, `extractDroppedFiles` |
| 6 | Selection (multi-click) | `selectedKeys`, `lastSelectedIndex`, `selectedFilenames` | `onRowClick`, `clearSelection` |
| 7 | Bulk-операции (download/move/delete) | `bulkBusy`, `showMoveModal`, `moveTargetKey`, `moveTreeData` | `bulkDownload`, `confirmBulkDelete`, `runBulkDelete`, `openMoveModal`, `onMoveTargetSelect`, `submitBulkMove`, `canMoveTo` |
| 8 | Per-file actions | `openingCollaboraFile` | `confirmDeleteFile`, `openCollabora`, `openImagePreview`, `openPdfPreview`, `getDownloadUrl`, `getFileIcon` |
| 9 | Image preview | `showImagePreview`, `previewInitialIndex`, `previewImages` | (через `openImagePreview`) |
| 10 | Permissions/access flags | `canUpload`, `canManage` | `permTagType` |
| 11 | Колонки таблицы (h-render) | `tableColumns` | `formatDateTime` (внутри) |

### 1.3 Используемое API (`.\frontend\src\api\files.ts`)

`fetchFolderTree`, `fetchFolderDetail`, `createFolder`, `deleteFolder`, `deleteFile`, `downloadFile`, `previewFile`, `uploadFiles`, `bulkDeleteFiles`, `bulkMoveFiles`, `syncFromNextcloud`, `openInCollabora`, `fileIcon`, `formatFileSize`, `isCollaboraFile`, `isPreviewableImage`, `isPreviewablePdf`, типы `FileFolderPublic`, `FileFolderTreeNode`, `NCItem`, константа `BULK_DOWNLOAD_LIMIT`.

### 1.4 Уже выделенные части (не трогать)

- `.\frontend\src\components\files\FilesImagePreview.vue` — оставить как есть.
- `.\frontend\src\components\files\FilesPermissionsModal.vue` — оставить как есть.
- `.\frontend\src\components\FileFolderNode.vue` — рекурсивный узел дерева, оставить как есть.
- `.\frontend\src\components\SkeletonCard.vue`, `.\frontend\src\components\EmptyState.vue` — общие, оставить.

---

## 2. Целевая структура

```
frontend/src/
├── pages/
│   └── FilesPage.vue                        # ~250 строк: оркестратор
├── components/files/
│   ├── FilesSidebar.vue                     # NEW
│   ├── FilesBreadcrumbs.vue                 # NEW
│   ├── FilesToolbar.vue                     # NEW
│   ├── FilesTable.vue                       # NEW
│   ├── FilesDropZone.vue                    # NEW
│   ├── FilesCreateFolderModal.vue           # NEW
│   ├── FilesMoveModal.vue                   # NEW
│   ├── FilesBulkBar.vue                     # NEW (выделить из FilesToolbar при необходимости)
│   ├── FilesImagePreview.vue                # уже существует
│   └── FilesPermissionsModal.vue            # уже существует
├── composables/
│   ├── useFilesTree.ts                      # NEW
│   ├── useFilesSelection.ts                 # NEW
│   ├── useFilesUpload.ts                    # NEW
│   ├── useFilesBulkOps.ts                   # NEW
│   └── useCollabora.ts                      # NEW (openCollabora)
├── stores/
│   └── files.ts                             # NEW: useFilesStore (общее состояние)
└── utils/
    └── extractDroppedFiles.ts               # NEW (вынести функцию + unit-тест)
```

**Бюджет строк:**

- `FilesPage.vue` ≤ 250 строк (template + setup + scoped layout-styles).
- Каждый child-компонент ≤ 200 строк (template + минимальная локальная логика).
- Каждый composable ≤ 150 строк.
- Pinia-store ≤ 200 строк.

---

## 3. Контракты модулей

### 3.1 Pinia-store `.\frontend\src\stores\files.ts` — `useFilesStore`

**Назначение:** единый источник истины для серверного состояния файлового модуля.

**State:**

```ts
tree: FileFolderTreeNode[]
loadingTree: boolean
selectedFolderId: string | null
currentFolder: FileFolderPublic | null
ncItems: NCItem[]
breadcrumbs: FileFolderPublic[]
loadingDetail: boolean
syncing: boolean
```

**Getters:**

- `canUpload: boolean` — `permission ∈ {editor, manager}` или `auth.isAdmin`.
- `canManage: boolean` — `permission === 'manager'` или `auth.isAdmin`.
- `findNodeById(id: string): FileFolderTreeNode | null`
- `findNodeByNcPath(path: string): FileFolderTreeNode | null`

**Actions:**

- `loadTree(): Promise<void>`
- `loadDetail(folderId: string): Promise<void>`
- `selectFolder(id: string | null): void` — выставляет `selectedFolderId`, триггерит `loadDetail` через watcher или явно.
- `createFolder(input: { name; parent_id; description }): Promise<void>` — после успеха `loadTree`.
- `deleteFolder(id: string): Promise<void>` — после успеха `loadTree`, сбрасывает `selectedFolderId` если он удалён.
- `syncFromNextcloud(): Promise<{ created: number; skipped: number }>`
- `refreshCurrent(): Promise<void>` — `loadDetail(selectedFolderId)` если выбрана.

**Не входит в store:** локальное UI-состояние модалок (`showCreateModal`, `showMoveModal`, `permsForFolderId`) — остаётся в оркестраторе или соответствующих компонентах.

**Тесты:** `frontend/tests/unit/files-store.spec.ts` — моки `api/files`, минимум кейсы:
- `loadTree` успех/ошибка (через `vi.mock`),
- `selectFolder` сбрасывает selection через event-bus или watch (см. 3.2),
- `deleteFolder` сбрасывает `selectedFolderId` если совпадает.

---

### 3.2 Composable `.\frontend\src\composables\useFilesTree.ts`

**Назначение:** вспомогательные операции над деревом, не зависящие от UI: рекурсивный поиск, маппинг для `n-tree`. Часть логики может остаться чистыми функциями в `utils/`. Прозрачно делегирует данные store.

**Экспорт:**

```ts
export function useFilesTree(): {
  tree: ComputedRef<FileFolderTreeNode[]>
  loadingTree: ComputedRef<boolean>
  selectedFolderId: ComputedRef<string | null>
  selectFolder(id: string | null): void
  findNodeById(id: string): FileFolderTreeNode | null
  findNodeByNcPath(path: string): FileFolderTreeNode | null
  loadTree(): Promise<void>
}
```

Внутри использует `useFilesStore()`. Никаких `ref`, локально создаваемых; только проксирование/computed.

---

### 3.3 Composable `.\frontend\src\composables\useFilesSelection.ts`

**Назначение:** выделение строк (single/multi-click, shift-range, ctrl-toggle), сброс при смене папки.

**Экспорт:**

```ts
export function useFilesSelection(items: Ref<NCItem[]>, folderId: Ref<string | null>): {
  selectedKeys: Ref<string[]>
  lastSelectedIndex: Ref<number | null>
  selectedFilenames: ComputedRef<string[]>
  onRowClick(row: NCItem, index: number, e: MouseEvent): void
  clearSelection(): void
}
```

`watch(folderId, () => clearSelection())` внутри composable.

**Поведение:** идентично текущему `onRowClick`/`clearSelection`/`selectedFilenames`. Открытие подпапки делегируется через callback-параметр (`onOpenDir?: (item: NCItem) => void`).

---

### 3.4 Composable `.\frontend\src\composables\useFilesUpload.ts`

**Назначение:** инкапсулировать загрузку файлов через input и DnD, прогресс, сообщения.

**Экспорт:**

```ts
export function useFilesUpload(folderId: Ref<string | null>, onUploaded: () => Promise<void> | void): {
  uploading: Ref<boolean>
  uploadProgress: Ref<{ done: number; total: number; failed: number }>
  fileInputRef: Ref<HTMLInputElement | null>
  triggerUpload(): void
  handleFileInput(e: Event): Promise<void>
  runUpload(files: File[]): Promise<void>
  // DnD:
  dragDepth: Ref<number>
  dndActive: ComputedRef<boolean>
  onMainDragEnter(e: DragEvent): void
  onMainDragOver(e: DragEvent): void
  onMainDragLeave(e: DragEvent): void
  onMainDrop(e: DragEvent): Promise<void>
}
```

Зависит от `useMessage`, `useI18n`, `api/files.uploadFiles`, и **utils/extractDroppedFiles**.

---

### 3.5 Utility `.\frontend\src\utils\extractDroppedFiles.ts`

**Назначение:** чистая функция, обрабатывающая `DataTransfer` (поддержка `webkitGetAsEntry` для пропуска папок). Выделяется отдельно для **unit-теста**.

```ts
export interface ExtractDroppedResult { files: File[]; hadFolders: boolean }
export async function extractDroppedFiles(dt: DataTransfer): Promise<ExtractDroppedResult>
```

**Тесты:** `frontend/tests/unit/extract-dropped-files.spec.ts`:
- пустой `DataTransfer` → `{files:[], hadFolders:false}`;
- только файлы через `dt.items` → корректно;
- файлы через fallback `dt.files` → корректно;
- содержит `webkitGetAsEntry` с `isDirectory:true` → `hadFolders:true`, файл-каталог пропущен;
- смешанный сценарий (файлы + папки) — оба факта корректно отражены.

Моки `DataTransfer`/`DataTransferItem` — обычные объекты с нужной структурой (см. `tests/unit/photos-store.spec.ts` как пример vitest mock).

---

### 3.6 Composable `.\frontend\src\composables\useFilesBulkOps.ts`

**Назначение:** bulk-download / bulk-delete / bulk-move (open/submit модалки), `canMoveTo`, `moveTreeData`.

**Экспорт:**

```ts
export function useFilesBulkOps(args: {
  folderId: Ref<string | null>
  selectedFilenames: ComputedRef<string[]>
  clearSelection: () => void
  onAfterMutation: () => Promise<void> | void
}): {
  bulkBusy: Ref<boolean>
  showMoveModal: Ref<boolean>
  moveTargetKey: Ref<string | null>
  moveTreeData: ComputedRef<TreeOption[]>
  bulkDownload(): Promise<void>
  confirmBulkDelete(): Promise<void>
  openMoveModal(): void
  onMoveTargetSelect(keys: Array<string | number>): void
  submitBulkMove(): Promise<void>
  canMoveTo(node: FileFolderTreeNode): boolean
}
```

Зависит от `useFilesStore` (для дерева), `useConfirmDialog`, `useMessage`, `useI18n`, `api/files`.

---

### 3.7 Composable `.\frontend\src\composables\useCollabora.ts`

**Назначение:** инкапсулирует `openCollabora` + состояние `openingCollaboraFile`.

```ts
export function useCollabora(folderId: Ref<string | null>): {
  openingCollaboraFile: Ref<string | null>
  openCollabora(item: NCItem): Promise<void>
}
```

---

### 3.8 Компоненты

Все компоненты — `<script setup lang="ts">`, props/emits через `defineProps<...>()`/`defineEmits<...>()`, без Pinia внутри (state приходит сверху или из composables).

#### 3.8.1 `FilesSidebar.vue`

**Props:**
- `tree: FileFolderTreeNode[]`
- `loading: boolean`
- `selectedId: string | null`
- `isAdmin: boolean`
- `isEditor: boolean`
- `syncing: boolean`

**Emits:**
- `select(id: string)`
- `create-root()`
- `create-child(folderId: string)`
- `manage(folderId: string)`
- `delete(folderId: string)`
- `sync()`

Внутри использует `FileFolderNode` как раньше.

#### 3.8.2 `FilesBreadcrumbs.vue`

**Props:**
- `breadcrumbs: FileFolderPublic[]`
- `current: FileFolderPublic | null`

**Emits:**
- `select(id: string)`

#### 3.8.3 `FilesToolbar.vue`

**Props:**
- `currentFolder: FileFolderPublic | null`
- `canUpload: boolean`
- `canManage: boolean`
- `uploading: boolean`
- `uploadProgress: { done; total; failed }`

**Emits:**
- `upload-click()` (триггерит скрытый input в parent)
- `manage-click()`
- `files-selected(files: File[])` (из встроенного `<input type=file>`) — **или** input оставить в оркестраторе и не тащить сюда.

> **Решение:** `<input type=file>` остаётся в оркестраторе (так проще управлять `fileInputRef`), а `FilesToolbar` только эмитит `upload-click`.

#### 3.8.4 `FilesBulkBar.vue` (опционально, можно объединить в Toolbar)

**Props:** `count`, `canUpload`, `bulkBusy`, `downloadLimit`.
**Emits:** `download`, `move`, `delete`, `clear`.

> Если итоговый размер `FilesToolbar.vue` < 200 строк с включённым bulk-bar, держать вместе. Иначе — выделить.

#### 3.8.5 `FilesTable.vue`

**Props:**
- `items: NCItem[]`
- `loading: boolean`
- `selectedKeys: string[]` (через `v-model:checked`)
- `canUpload: boolean`
- `folderId: string | null` (для url-builder'ов)
- `openingCollaboraFile: string | null`

**Emits:**
- `update:selectedKeys(keys: string[])`
- `row-click(payload: { row: NCItem; index: number; event: MouseEvent })`
- `preview-image(item: NCItem)`
- `preview-pdf(item: NCItem)`
- `download(item: NCItem)` — либо просто отдать href (рендерить `<a download>` внутри)
- `open-collabora(item: NCItem)`
- `delete-file(item: NCItem)`

Колонки и render-функции (`h(...)`) — внутри компонента. Использует утилиты `fileIcon`, `formatFileSize`, `isPreviewableImage`, `isPreviewablePdf`, `isCollaboraFile`, `formatDate` (общая `utils/formatDate.ts`).

#### 3.8.6 `FilesDropZone.vue`

**Назначение:** обёртка-overlay вокруг main-области. Не управляет состоянием, просто визуально показывает overlay.

**Props:** `active: boolean`.
**Emits:** `dragenter`, `dragover`, `dragleave`, `drop` (прокидывает нативные события наверх).

> **Альтернатива:** реализовать как `<slot>` + scoped overlay; обработчики DnD навешивать на корневой `<main>`. Решение принять при реализации; дублирования логики не должно быть.

#### 3.8.7 `FilesCreateFolderModal.vue`

**Props:**
- `show: boolean` (`v-model:show`)
- `loading: boolean`

**Emits:**
- `update:show(value: boolean)`
- `submit(payload: { name: string; description: string | null })`

Локально хранит `name`/`description`; при `show=false` сбрасывает.

#### 3.8.8 `FilesMoveModal.vue`

**Props:**
- `show: boolean` (`v-model:show`)
- `treeData: TreeOption[]`
- `targetKey: string | null` (`v-model:targetKey`)
- `loading: boolean`

**Emits:**
- `update:show`, `update:targetKey`, `confirm()`

---

### 3.9 Финальный `FilesPage.vue` (оркестратор, ≤ 250 строк)

Скелет:

```vue
<template>
  <div class="files-page">
    <FilesSidebar
      :tree="store.tree"
      :loading="store.loadingTree"
      :selected-id="store.selectedFolderId"
      :is-admin="auth.isAdmin"
      :is-editor="auth.isEditor"
      :syncing="store.syncing"
      @select="store.selectFolder"
      @create-root="onCreateRoot"
      @create-child="onCreateChild"
      @manage="onManage"
      @delete="onDeleteFolder"
      @sync="store.syncFromNextcloud"
    />

    <main
      class="files-main"
      @dragenter.prevent="upload.onMainDragEnter"
      @dragover.prevent="upload.onMainDragOver"
      @dragleave.prevent="upload.onMainDragLeave"
      @drop.prevent="upload.onMainDrop"
    >
      <FilesDropZone :active="upload.dndActive.value && store.canUpload" />

      <EmptyState v-if="!store.selectedFolderId" ... />
      <template v-else>
        <FilesBreadcrumbs ... />
        <FilesToolbar ... @upload-click="upload.triggerUpload" @manage-click="..." />
        <FilesBulkBar v-if="selection.selectedKeys.value.length" ... />
        <FilesTable ... />
        <input ref="upload.fileInputRef" type="file" multiple style="display:none" @change="upload.handleFileInput" />
      </template>
    </main>

    <FilesCreateFolderModal v-model:show="showCreateModal" :loading="creating" @submit="submitCreate" />
    <FilesMoveModal v-model:show="bulk.showMoveModal.value" :tree-data="bulk.moveTreeData.value" v-model:target-key="bulk.moveTargetKey.value" :loading="bulk.bulkBusy.value" @confirm="bulk.submitBulkMove" />
    <FilesPermissionsModal v-model:show="showPermsModal" :folder-id="permsForFolderId" />
    <FilesImagePreview v-if="showImagePreview && store.selectedFolderId" :images="previewImages" :initial-index="previewInitialIndex" :folder-id="store.selectedFolderId" @close="showImagePreview = false" />
  </div>
</template>
```

```ts
const store = useFilesStore()
const auth = useAuthStore()
const selection = useFilesSelection(toRef(store, 'ncItems'), toRef(store, 'selectedFolderId'))
const upload = useFilesUpload(toRef(store, 'selectedFolderId'), () => store.refreshCurrent())
const bulk = useFilesBulkOps({
  folderId: toRef(store, 'selectedFolderId'),
  selectedFilenames: selection.selectedFilenames,
  clearSelection: selection.clearSelection,
  onAfterMutation: () => store.refreshCurrent(),
})
const collabora = useCollabora(toRef(store, 'selectedFolderId'))

onMounted(() => store.loadTree())
watch(() => store.selectedFolderId, (id) => { if (id) store.loadDetail(id) })
```

Локально остаётся только UI-состояние модалок + image-preview state.

---

## 4. План работ (этапы)

### Этап 0 — подготовка (0.5 ч)

1. Снять baseline: `npm --prefix frontend run typecheck && npm --prefix frontend run lint && npm --prefix frontend test`.
2. Зафиксировать текущий список `i18n` ключей, используемых в `FilesPage.vue` (для проверки `i18n` чистоты после рефакторинга).
3. Создать ветку.

### Этап 1 — извлечение `extractDroppedFiles` (1 ч)

1. Создать `.\frontend\src\utils\extractDroppedFiles.ts`.
2. Создать `.\frontend\tests\unit\extract-dropped-files.spec.ts` (см. 3.5).
3. Подключить в `FilesPage.vue` (временно, до Этапа 4).
4. `npm test` — зелено.

### Этап 2 — Pinia-store `useFilesStore` (3–4 ч)

1. Создать `.\frontend\src\stores\files.ts`.
2. Перенести: `tree`, `loadingTree`, `selectedFolderId`, `currentFolder`, `ncItems`, `breadcrumbs`, `loadingDetail`, `syncing` + соответствующие actions/getters.
3. В `FilesPage.vue` заменить локальные `ref`/функции на store (минимально, без раскола компонентов).
4. Создать `.\frontend\tests\unit\files-store.spec.ts` (см. 3.1).
5. Smoke-проверка вручную: загрузка дерева, выбор папки, sync, создание/удаление папки.

### Этап 3 — composables (4–5 ч)

В порядке: `useFilesTree` → `useFilesSelection` → `useFilesUpload` (зависит от Этапа 1) → `useFilesBulkOps` → `useCollabora`.

После каждого: `typecheck` + `npm test` зелено.

### Этап 4 — компоненты (5–7 ч)

Порядок (от листьев к корню, чтобы не ломать страницу):

1. `FilesBreadcrumbs.vue` (самый простой, тривиальные props/emits).
2. `FilesCreateFolderModal.vue`.
3. `FilesMoveModal.vue`.
4. `FilesDropZone.vue`.
5. `FilesSidebar.vue`.
6. `FilesToolbar.vue` (+ `FilesBulkBar.vue` при необходимости).
7. `FilesTable.vue` — самый объёмный, переносить колонки (`h(...)`) аккуратно.

После каждого выноса:
- `typecheck` + `lint` + `npm test` — зелено;
- ручная smoke-проверка соответствующей функциональности.

### Этап 5 — финализация оркестратора (1–2 ч)

1. В `FilesPage.vue` оставить ≤ 250 строк (template + минимум setup).
2. Удалить мёртвый код, перенести scoped-styles по компонентам (sidebar-styles → `FilesSidebar.vue`, и т.д.). В `FilesPage.vue` остаются только layout-стили (`.files-page`, `.files-main`, общий drop-overlay).
3. Прогон полного чек-листа (раздел 6).

### Этап 6 — тесты + документация (1–2 ч)

1. Покрытие: store + utils + (по возможности) composables через mount-тесты.
2. Если в проекте есть e2e/snapshot — обновить.
3. В `ref.md` пометить 2.1.a выполненным (перенести в «Закрытые ранее» в формате существующих записей с указанием итоговых строк).

---

## 5. Совместимость и риски

### 5.1 Pinia-store store-id

Использовать `defineStore('files', () => { ... })` (composition style — соответствует `branding`/`layout`/`photos`/`notifications`). Никаких пересечений по id.

### 5.2 Watcher на `selectedFolderId`

Сейчас сидит в `FilesPage.vue` и сбрасывает selection + загружает детали. После рефакторинга:

- сброс selection — внутри `useFilesSelection` через `watch(folderId)`;
- загрузка деталей — в оркестраторе через `watch(() => store.selectedFolderId)` или внутри store-action `selectFolder` (предпочтительно — в action для атомарности).

### 5.3 `n-data-table` checked-row-keys

Передавать в `FilesTable.vue` через `v-model:selected-keys` (название проп — `selectedKeys`). Проследить, что disabled-чекбокс для `is_dir` корректен.

### 5.4 `<input type="file">` ref

Остаётся в шаблоне `FilesPage.vue`, ref передаётся через composable: `upload.fileInputRef.value` присваивается в шаблоне. Альтернативно — composable управляет input-элементом через `document.createElement('input')` (тогда не нужен template-ref). Решение принять при реализации.

### 5.5 i18n

Все текстовые ключи (`files.*`, `common.*`) уже существуют — переезжают вместе с кодом. После рефакторинга прогнать `npm --prefix frontend run i18n:check` (или аналог, см. `package.json`) — должно быть чисто.

### 5.6 Стили

CSS перевозится **с компонентом**, в котором отображается соответствующая разметка (sidebar-styles → `FilesSidebar.vue`, table-styles → `FilesTable.vue`, и т.д.). В `FilesPage.vue` остаются только layout-уровневые правила (`.files-page`, `.files-main`, drop-overlay при общем подходе).

### 5.7 Performance

Pinia-store не должен ввести лишних реактивных подписок: getters `canUpload`/`canManage` зависят только от `currentFolder.permission` и `auth.isAdmin`. Дерево при `loadTree` обновляется одним присваиванием.

### 5.8 Обратная совместимость

Внешний URL/маршрут `/files` (см. `router.ts`) **не меняется**. Экспорт страницы из `pages/FilesPage.vue` сохраняется (`defineOptions({ name: 'FilesPage' })`).

### 5.9 Связка с 2.3

Задача 2.3 уже закрыта (BrandingTab/GlobalSearch). Здесь следуем тому же паттерну: API-вызовы — только в store-actions / composables, в компонентах никаких прямых обращений к `api/files.ts` (за исключением чисто url-builder функций `downloadFile`, `previewFile`, которые возвращают строку).

### 5.10 Связка с 2.8 (vue-query)

В рамках 2.1.a **vue-query не вводим** (это область 2.8). Оставляем ref-флаги внутри store, чтобы 2.8 потом единообразно мигрировал и `FilesPage` тоже.

---

## 6. Приёмочные критерии (Definition of Done)

- [ ] `frontend/src/pages/FilesPage.vue` ≤ 250 строк.
- [ ] Созданы все компоненты из списка 2 (кроме уже существовавших).
- [ ] Созданы все composables из списка 2.
- [ ] Создан `stores/files.ts` (`useFilesStore`).
- [ ] Создан `utils/extractDroppedFiles.ts` + unit-тест `extract-dropped-files.spec.ts` (≥ 5 кейсов).
- [ ] Создан `tests/unit/files-store.spec.ts` (минимум 3 кейса).
- [ ] `npm --prefix frontend run typecheck` — без ошибок.
- [ ] `npm --prefix frontend run lint` — без ошибок.
- [ ] `npm --prefix frontend test` — все существующие тесты + новые зелёные (была 191/191 — должно стать ≥ 191 + новые).
- [ ] `npm --prefix frontend run i18n:check` (если есть) — чисто.
- [ ] Ручная регрессия (см. чек-лист 6.1) — все сценарии работают.
- [ ] В `ref.md` пункт 2.1.a удалён из активных, добавлена строка в «Закрытые ранее» с описанием результата (формат как для 2.1.b/2.1.c).

### 6.1 Чек-лист ручной регрессии

1. Загрузка `/files`: дерево показывается, скелетоны исчезают.
2. Выбор корневой папки: загружаются breadcrumbs, items, toolbar, права.
3. Создание корневой папки (admin/editor): успех + рефреш дерева.
4. Создание подпапки через `FileFolderNode`: успех.
5. Удаление папки: confirm, успех, сброс selection.
6. Manage permissions: открывается модалка `FilesPermissionsModal`.
7. Sync from NC (admin): спиннер, success-message, дерево обновлено.
8. Аплоад через кнопку «Upload»: progress-bar, файлы появляются.
9. DnD: drag enter показывает overlay, drop загружает файлы; папки в drop — игнорируются с info-сообщением.
10. Selection: одиночный клик, ctrl-toggle, shift-range — корректны; сброс при смене папки.
11. Bulk download (≤ лимит): скачивает по очереди.
12. Bulk download (> лимит): кнопка disabled + tooltip.
13. Bulk move: модалка с деревом (disabled узлы текущей папки/без прав), submit перемещает.
14. Bulk delete: confirm, удаляет.
15. Per-file: preview image, preview pdf, download, edit-in-collabora (loading-state), delete.
16. Image preview модалка работает.
17. Empty states: пустое дерево, пустая папка, нет выбранной папки.

---

## 7. Зависимости и порядок мерджа

- Не блокирует: 2.8 (но облегчает её последующее внедрение).
- Конфликты при rebase: маловероятны — `FilesPage.vue` крупный и редко правится; основной риск — параллельные правки в `api/files.ts`.

---

## 8. Оценка по этапам

| Этап | Часы |
|------|------|
| 0. Подготовка | 0.5 |
| 1. `extractDroppedFiles` + тесты | 1.0 |
| 2. `useFilesStore` + тесты | 3–4 |
| 3. Composables | 4–5 |
| 4. Компоненты (7 шт) | 5–7 |
| 5. Финализация оркестратора | 1–2 |
| 6. Тесты + документация | 1–2 |
| **Итого** | **15.5–21.5 ч** |

Соответствует плановой оценке **16–24 ч** из `ref.md`.
