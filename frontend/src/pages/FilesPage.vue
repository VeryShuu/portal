<template>
  <div class="files-page">
    <!-- Sidebar: folder tree -->
    <aside class="files-side">
      <div class="files-side__head">
        <h2 class="files-side__title">{{ t('files.folders.title') }}</h2>
        <n-button
          v-if="auth.isEditor"
          size="tiny"
          type="primary"
          ghost
          @click="openCreateRoot"
        >+ {{ t('files.folders.newRoot') }}</n-button>
      </div>
      <div v-if="auth.isAdmin" class="files-side__sync">
        <n-button
          size="tiny"
          :loading="syncing"
          :disabled="syncing"
          @click="syncFromNc"
        >{{ t('files.sync.button') }}</n-button>
      </div>

      <div v-if="loadingTree" class="files-side__loading">
        <SkeletonCard v-for="i in 6" :key="i" variant="folder-item" />
      </div>
      <ul v-else-if="tree.length" class="folder-tree">
        <FileFolderNode
          v-for="node in tree"
          :key="node.id"
          :node="node"
          :selected-id="selectedFolderId"
          @select="selectFolder"
          @create-child="openCreateChild"
          @manage="openManage"
          @delete="confirmDeleteFolder"
        />
      </ul>
      <p v-else class="files-side__empty">{{ t('files.folders.empty') }}</p>
    </aside>

    <!-- Main: folder content -->
    <main
      class="files-main"
      @dragenter.prevent="onMainDragEnter"
      @dragover.prevent="onMainDragOver"
      @dragleave.prevent="onMainDragLeave"
      @drop.prevent="onMainDrop"
    >
      <div v-if="dndActive && canUpload" class="files-dropzone-overlay">
        <span>{{ t('files.dropzone.hint') }}</span>
      </div>
      <EmptyState
        v-if="!selectedFolderId"
        variant="file"
        :title="t('files.emptyState.title')"
        :description="t('files.emptyState.desc')"
      />

      <template v-else>
        <!-- Breadcrumbs -->
        <nav v-if="breadcrumbs.length" class="files-breadcrumbs">
          <span
            v-for="(crumb, i) in breadcrumbs"
            :key="crumb.id"
            class="files-breadcrumb"
          >
            <span
              class="files-breadcrumb__link"
              @click="selectFolder(crumb.id)"
            >{{ crumb.name }}</span>
            <span v-if="i < breadcrumbs.length - 1" class="files-breadcrumb__sep">/</span>
          </span>
          <span class="files-breadcrumb files-breadcrumb--current">{{ currentFolder?.name }}</span>
        </nav>

        <!-- Toolbar -->
        <div class="files-toolbar">
          <div class="files-toolbar__left">
            <h1 class="files-title">{{ currentFolder?.name }}</h1>
            <n-tag v-if="currentFolder?.permission" size="small" :type="permTagType(currentFolder.permission)">
              {{ t(`files.permission.${currentFolder.permission}`) }}
            </n-tag>
          </div>
          <div class="files-toolbar__right">
            <n-button
              v-if="canUpload"
              size="small"
              type="primary"
              @click="triggerUpload"
            >{{ t('files.upload') }}</n-button>
            <n-button
              v-if="canManage"
              size="small"
              @click="openManage(selectedFolderId!)"
            >{{ t('files.manage') }}</n-button>
            <input
              ref="fileInputRef"
              type="file"
              multiple
              style="display: none"
              @change="handleFileInput"
            />
          </div>
        </div>

        <!-- Upload progress -->
        <div v-if="uploading" class="files-upload-progress">
          <n-progress
            type="line"
            :percentage="uploadProgress.total ? Math.round((uploadProgress.done / uploadProgress.total) * 100) : 0"
            :show-indicator="false"
            :height="6"
          />
          <span class="files-upload-progress__text">
            {{ t('files.uploadProgress', { done: uploadProgress.done, total: uploadProgress.total }) }}
          </span>
        </div>

        <!-- Bulk-bar -->
        <div v-if="selectedKeys.length" class="files-bulk-bar">
          <span class="files-bulk-bar__count">{{ t('files.bulk.selected', { n: selectedKeys.length }) }}</span>
          <n-tooltip v-if="selectedKeys.length > BULK_DOWNLOAD_LIMIT" trigger="hover">
            <template #trigger>
              <span>
                <n-button size="small" disabled>{{ t('files.bulk.download') }}</n-button>
              </span>
            </template>
            {{ t('files.bulk.downloadLimit') }}
          </n-tooltip>
          <n-button
            v-else
            size="small"
            @click="bulkDownload"
          >{{ t('files.bulk.download') }}</n-button>
          <n-button
            size="small"
            :disabled="!canUpload || bulkBusy"
            :loading="bulkBusy"
            @click="openMoveModal"
          >{{ t('files.bulk.move') }}</n-button>
          <n-button
            size="small"
            type="error"
            ghost
            :disabled="!canUpload || bulkBusy"
            :loading="bulkBusy"
            @click="confirmBulkDelete"
          >{{ t('files.bulk.delete') }}</n-button>
          <n-button size="small" text @click="clearSelection">{{ t('files.bulk.clear') }}</n-button>
        </div>

        <!-- File list -->
        <div v-if="loadingDetail" class="files-loading-skeleton">
          <SkeletonCard v-for="i in 8" :key="i" variant="file-row" />
        </div>
        <EmptyState
          v-else-if="!ncItems.length"
          variant="file"
          :title="t('files.emptyFolder')"
        />
        <n-data-table
          v-else
          :columns="tableColumns"
          :data="ncItems"
          :row-key="(row: NCItem) => row.nc_path"
          v-model:checked-row-keys="selectedKeys"
          :row-props="(row: NCItem, index: number) => ({ onClick: (e: MouseEvent) => onRowClick(row, index, e), class: row.is_dir ? 'files-row--dir' : '' })"
          size="small"
          :bordered="false"
          :single-line="false"
        />
      </template>
    </main>

    <!-- Create folder modal -->
    <n-modal v-model:show="showCreateModal" :title="t('files.folders.create')" preset="card" style="width: 480px">
      <n-form>
        <n-form-item :label="t('files.folders.name')">
          <n-input v-model:value="createForm.name" :placeholder="t('files.folders.namePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('files.folders.description')">
          <n-input v-model:value="createForm.description" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <n-button @click="showCreateModal = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="creating" @click="submitCreate">{{ t('common.create') }}</n-button>
        </div>
      </template>
    </n-modal>

    <FilesPermissionsModal
      v-model:show="showPermsModal"
      :folder-id="permsForFolderId"
    />

    <!-- Bulk move modal -->
    <n-modal
      v-model:show="showMoveModal"
      :title="t('files.bulk.moveTitle')"
      preset="card"
      style="width: 520px"
    >
      <n-tree
        v-if="moveTreeData.length"
        :data="moveTreeData"
        :selected-keys="moveTargetKey ? [moveTargetKey] : []"
        :default-expand-all="true"
        block-line
        selectable
        @update:selected-keys="onMoveTargetSelect"
      />
      <p v-else class="files-bulk-bar__empty">{{ t('files.bulk.noEditableTargets') }}</p>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <n-button @click="showMoveModal = false">{{ t('common.cancel') }}</n-button>
          <n-button
            type="primary"
            :loading="bulkBusy"
            :disabled="!moveTargetKey || bulkBusy"
            @click="submitBulkMove"
          >{{ t('files.bulk.moveConfirm') }}</n-button>
        </div>
      </template>
    </n-modal>

  </div>

  <FilesImagePreview
    v-if="showImagePreview && selectedFolderId"
    :images="previewImages"
    :initial-index="previewInitialIndex"
    :folder-id="selectedFolderId"
    @close="showImagePreview = false"
  />
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NProgress,
  NTag,
  NTooltip,
  NTree,
  useDialog,
  useMessage,
  type DataTableColumns,
  type TreeOption,
} from 'naive-ui'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import FileFolderNode from '../components/FileFolderNode.vue'
import FilesImagePreview from '../components/files/FilesImagePreview.vue'
import FilesPermissionsModal from '../components/files/FilesPermissionsModal.vue'
import { useAuthStore } from '../stores/auth'
import {
  BULK_DOWNLOAD_LIMIT,
  type FileFolderPublic,
  type FileFolderTreeNode,
  type NCItem,
  bulkDeleteFiles,
  bulkMoveFiles,
  createFolder,
  deleteFile,
  deleteFolder,
  downloadFile,
  fetchFolderDetail,
  fetchFolderTree,
  fileIcon,
  formatFileSize,
  isCollaboraFile,
  isPreviewableImage,
  isPreviewablePdf,
  openInCollabora,
  previewFile,
  syncFromNextcloud,
  uploadFiles,
} from '../api/files'

const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()
const dialog = useDialog()

const tree = ref<FileFolderTreeNode[]>([])
const loadingTree = ref(false)
const selectedFolderId = ref<string | null>(null)
const currentFolder = ref<FileFolderPublic | null>(null)
const ncItems = ref<NCItem[]>([])
const breadcrumbs = ref<FileFolderPublic[]>([])
const loadingDetail = ref(false)

const showCreateModal = ref(false)
const createParentId = ref<string | null>(null)
const creating = ref(false)
const createForm = ref({ name: '', description: '' })

const showPermsModal = ref(false)
const permsForFolderId = ref<string | null>(null)

const uploading = ref(false)
const uploadProgress = ref<{ done: number; total: number; failed: number }>({ done: 0, total: 0, failed: 0 })
const fileInputRef = ref<HTMLInputElement | null>(null)

// Selection state
const selectedKeys = ref<string[]>([])
const lastSelectedIndex = ref<number | null>(null)

// Bulk operation state
const bulkBusy = ref(false)
const showMoveModal = ref(false)
const moveTargetKey = ref<string | null>(null)

// Drag-and-drop state
const dragDepth = ref(0)
const dndActive = computed(() => dragDepth.value > 0)

const showImagePreview = ref(false)
const previewInitialIndex = ref(0)
const previewImages = computed(() => ncItems.value.filter(isPreviewableImage))

const syncing = ref(false)
const openingCollaboraFile = ref<string | null>(null)

function formatDateTime(dt: string | null): string {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const tableColumns = computed<DataTableColumns<NCItem>>(() => [
  {
    type: 'selection',
    disabled: (row: NCItem) => row.is_dir,
  },
  {
    key: 'name',
    title: t('files.table.name'),
    render(row) {
      return h('div', { class: 'files-cell-name' }, [
        h('span', { class: 'file-type-icon' }, getFileIcon(row)),
        h('span', { class: 'files-cell-name__text' }, row.name),
      ])
    },
    ellipsis: { tooltip: true },
  },
  {
    key: 'size_bytes',
    title: t('files.table.size'),
    width: 100,
    render(row) {
      return row.is_dir ? '—' : formatFileSize(row.size_bytes)
    },
  },
  {
    key: 'uploaded_at',
    title: t('files.table.uploaded'),
    width: 160,
    render(row) {
      if (row.is_dir || !row.uploaded_at) return '—'
      const dateStr = formatDateTime(row.uploaded_at)
      if (!row.uploaded_by) return dateStr
      return h(
        NTooltip,
        {},
        {
          trigger: () => h('span', { class: 'files-cell-date' }, dateStr),
          default: () => row.uploaded_by!.full_name,
        }
      )
    },
  },
  {
    key: 'last_modified',
    title: t('files.table.modified'),
    width: 160,
    render(row) {
      return row.is_dir ? '—' : formatDateTime(row.last_modified)
    },
  },
  {
    key: 'actions',
    title: '',
    width: 220,
    render(row) {
      if (row.is_dir) return null
      const btns = []
      if (isPreviewableImage(row) || isPreviewablePdf(row)) {
        btns.push(
          h(NButton, { size: 'tiny', onClick: (e: MouseEvent) => { e.stopPropagation(); isPreviewablePdf(row) ? openPdfPreview(row) : openImagePreview(row) } }, { default: () => t('files.preview') })
        )
      }
      btns.push(
        h(NButton, { size: 'tiny', tag: 'a', href: getDownloadUrl(row), download: true, onClick: (e: MouseEvent) => e.stopPropagation() }, { default: () => t('files.download') })
      )
      if (isCollaboraFile(row)) {
        const isOpening = openingCollaboraFile.value === row.name
        btns.push(
          h(NButton, { size: 'tiny', type: 'primary', ghost: true, loading: isOpening, disabled: isOpening, onClick: (e: MouseEvent) => { e.stopPropagation(); openCollabora(row) } }, { default: () => t('files.edit') })
        )
      }
      if (canUpload.value) {
        btns.push(
          h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: (e: MouseEvent) => { e.stopPropagation(); confirmDeleteFile(row) } }, { default: () => t('common.delete') })
        )
      }
      return h('div', { class: 'files-cell-actions' }, btns)
    },
  },
])

const canUpload = computed(() => {
  const p = currentFolder.value?.permission
  return p === 'editor' || p === 'manager' || auth.isAdmin
})

const canManage = computed(() => {
  const p = currentFolder.value?.permission
  return p === 'manager' || auth.isAdmin
})

function getFileIcon(item: NCItem): string {
  return fileIcon(item)
}

function getDownloadUrl(item: NCItem): string {
  if (!selectedFolderId.value) return '#'
  return downloadFile(selectedFolderId.value, item.name)
}

function permTagType(perm: string) {
  if (perm === 'manager') return 'success'
  if (perm === 'editor') return 'info'
  return 'default'
}

async function loadTree() {
  loadingTree.value = true
  try {
    const data = await fetchFolderTree()
    tree.value = data.items
  } catch {
    message.error(t('files.error.loadTree'))
  } finally {
    loadingTree.value = false
  }
}

async function syncFromNc() {
  syncing.value = true
  try {
    const report = await syncFromNextcloud()
    message.success(t('files.sync.success', { created: report.created, skipped: report.skipped }))
    await loadTree()
  } catch {
    message.error(t('files.sync.error'))
  } finally {
    syncing.value = false
  }
}

async function loadDetail(folderId: string) {
  loadingDetail.value = true
  try {
    const data = await fetchFolderDetail(folderId)
    currentFolder.value = data.folder
    ncItems.value = data.items
    breadcrumbs.value = data.breadcrumbs
  } catch {
    message.error(t('files.error.loadFolder'))
  } finally {
    loadingDetail.value = false
  }
}

function selectFolder(id: string) {
  selectedFolderId.value = id
}

function openSubFolder(item: NCItem) {
  const node = findNodeByNcPath(tree.value, item.nc_path)
  if (node) selectFolder(node.id)
}

function findNodeByNcPath(nodes: FileFolderTreeNode[], path: string): FileFolderTreeNode | null {
  for (const n of nodes) {
    if (n.nc_path === path) return n
    const child = findNodeByNcPath(n.children, path)
    if (child) return child
  }
  return null
}

watch(selectedFolderId, (id) => {
  selectedKeys.value = []
  lastSelectedIndex.value = null
  if (id) loadDetail(id)
})

function openCreateRoot() {
  createParentId.value = null
  createForm.value = { name: '', description: '' }
  showCreateModal.value = true
}

function openCreateChild(folderId: string) {
  createParentId.value = folderId
  createForm.value = { name: '', description: '' }
  showCreateModal.value = true
}

async function submitCreate() {
  if (!createForm.value.name.trim()) return
  creating.value = true
  try {
    await createFolder({
      name: createForm.value.name.trim(),
      parent_id: createParentId.value,
      description: createForm.value.description || null,
    })
    showCreateModal.value = false
    message.success(t('files.folders.created'))
    await loadTree()
  } catch {
    message.error(t('files.error.createFolder'))
  } finally {
    creating.value = false
  }
}

function confirmDeleteFolder(folderId: string) {
  dialog.warning({
    title: t('files.folders.deleteTitle'),
    content: t('files.folders.deleteConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await deleteFolder(folderId)
        message.success(t('files.folders.deleted'))
        if (selectedFolderId.value === folderId) selectedFolderId.value = null
        await loadTree()
      } catch {
        message.error(t('files.error.deleteFolder'))
      }
    },
  })
}

function openManage(folderId: string) {
  permsForFolderId.value = folderId
  showPermsModal.value = true
}

function triggerUpload() {
  fileInputRef.value?.click()
}

async function handleFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length || !selectedFolderId.value) return
  const files = Array.from(input.files)
  input.value = ''
  await runUpload(files)
}

async function runUpload(files: File[]) {
  if (!files.length || !selectedFolderId.value) return
  uploading.value = true
  uploadProgress.value = { done: 0, total: files.length, failed: 0 }
  try {
    const result = await uploadFiles(selectedFolderId.value, files)
    uploadProgress.value = {
      done: result.uploaded.length,
      total: files.length,
      failed: result.failed.length,
    }
    if (result.uploaded.length) {
      message.success(t('files.uploaded', { n: result.uploaded.length }))
    }
    if (result.failed.length) {
      message.warning(t('files.uploadFailed', { n: result.failed.length }))
    }
    await loadDetail(selectedFolderId.value)
  } catch {
    message.error(t('files.error.upload'))
  } finally {
    uploading.value = false
  }
}

// ── Drag-and-drop ────────────────────────────────────────────────────────────
function onMainDragEnter(e: DragEvent) {
  if (!canUpload.value || !selectedFolderId.value) return
  if (!e.dataTransfer?.types?.includes('Files')) return
  dragDepth.value += 1
}

function onMainDragOver(e: DragEvent) {
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
}

function onMainDragLeave(_e: DragEvent) {
  if (dragDepth.value > 0) dragDepth.value -= 1
}

async function onMainDrop(e: DragEvent) {
  dragDepth.value = 0
  if (!canUpload.value || !selectedFolderId.value || !e.dataTransfer) return
  const { files, hadFolders } = await extractDroppedFiles(e.dataTransfer)
  if (hadFolders) {
    message.info(t('files.dropzone.foldersSkipped'))
  }
  if (!files.length) return
  await runUpload(files)
}

async function extractDroppedFiles(
  dt: DataTransfer
): Promise<{ files: File[]; hadFolders: boolean }> {
  const files: File[] = []
  let hadFolders = false
  if (dt.items && dt.items.length) {
    for (const item of Array.from(dt.items)) {
      if (item.kind !== 'file') continue
      const entry = (item as DataTransferItem & { webkitGetAsEntry?: () => { isDirectory: boolean } | null }).webkitGetAsEntry?.()
      if (entry && entry.isDirectory) {
        hadFolders = true
        continue
      }
      const f = item.getAsFile()
      if (f) files.push(f)
    }
  } else if (dt.files) {
    for (const f of Array.from(dt.files)) files.push(f)
  }
  return { files, hadFolders }
}

// ── Selection / multi-click ──────────────────────────────────────────────────
function onRowClick(row: NCItem, index: number, e: MouseEvent) {
  if (row.is_dir) {
    if (!e.shiftKey && !e.ctrlKey && !e.metaKey) {
      openSubFolder(row)
    }
    return
  }
  if (e.shiftKey && lastSelectedIndex.value !== null) {
    e.preventDefault()
    const start = Math.min(lastSelectedIndex.value, index)
    const end = Math.max(lastSelectedIndex.value, index)
    const range = ncItems.value
      .slice(start, end + 1)
      .filter((it) => !it.is_dir)
      .map((it) => it.nc_path)
    const set = new Set(selectedKeys.value)
    for (const k of range) set.add(k)
    selectedKeys.value = Array.from(set)
    return
  }
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    const set = new Set(selectedKeys.value)
    if (set.has(row.nc_path)) {
      set.delete(row.nc_path)
    } else {
      set.add(row.nc_path)
    }
    selectedKeys.value = Array.from(set)
    lastSelectedIndex.value = index
    return
  }
  lastSelectedIndex.value = index
  // Default click — preview/open behavior, only when nothing selected
  if (!selectedKeys.value.length) {
    if (isPreviewableImage(row)) openImagePreview(row)
    else if (isPreviewablePdf(row)) openPdfPreview(row)
  }
}

function clearSelection() {
  selectedKeys.value = []
  lastSelectedIndex.value = null
}

const selectedFilenames = computed(() => {
  const names: string[] = []
  for (const it of ncItems.value) {
    if (selectedKeys.value.includes(it.nc_path) && !it.is_dir) {
      names.push(it.name)
    }
  }
  return names
})

// ── Bulk download ────────────────────────────────────────────────────────────
async function bulkDownload() {
  if (!selectedFolderId.value) return
  const names = selectedFilenames.value
  if (!names.length) return
  if (names.length > BULK_DOWNLOAD_LIMIT) {
    message.warning(t('files.bulk.downloadLimit'))
    return
  }
  message.info(t('files.bulk.downloadStarted', { n: names.length }))
  for (const name of names) {
    const a = document.createElement('a')
    a.href = downloadFile(selectedFolderId.value, name)
    a.download = name
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    await new Promise((resolve) => setTimeout(resolve, 150))
  }
}

// ── Bulk delete ──────────────────────────────────────────────────────────────
function confirmBulkDelete() {
  const names = selectedFilenames.value
  if (!names.length) return
  dialog.warning({
    title: t('files.bulk.deleteTitle'),
    content: t('files.bulk.deleteConfirm', { n: names.length }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => runBulkDelete(names),
  })
}

async function runBulkDelete(names: string[]) {
  if (!selectedFolderId.value || !names.length) return
  bulkBusy.value = true
  try {
    const result = await bulkDeleteFiles(selectedFolderId.value, names)
    if (result.failed.length === 0) {
      message.success(t('files.bulk.deleteSuccess', { n: result.deleted.length }))
    } else {
      message.warning(
        t('files.bulk.deletePartial', {
          deleted: result.deleted.length,
          failed: result.failed.length,
        })
      )
    }
    clearSelection()
    await loadDetail(selectedFolderId.value)
  } catch (err) {
    const status = (err as { status?: number; data?: { detail?: string } })?.status
    if (status === 409) {
      message.warning(t('files.error.bulkInProgress'))
    } else {
      message.error(t('files.error.bulkDelete'))
    }
  } finally {
    bulkBusy.value = false
  }
}

// ── Bulk move ────────────────────────────────────────────────────────────────
const moveTreeData = computed<TreeOption[]>(() => {
  function map(nodes: FileFolderTreeNode[]): TreeOption[] {
    return nodes
      .map((n) => {
        const opt: TreeOption = {
          key: n.id,
          label: n.name,
          disabled: n.id === selectedFolderId.value || !canMoveTo(n),
          children: map(n.children),
        }
        return opt
      })
      .filter((opt) => {
        if (!opt.disabled) return true
        return Array.isArray(opt.children) && opt.children.length > 0
      })
  }
  return map(tree.value)
})

function canMoveTo(node: FileFolderTreeNode): boolean {
  return node.permission === 'editor' || node.permission === 'manager' || auth.isAdmin
}

function openMoveModal() {
  if (!selectedFilenames.value.length) return
  moveTargetKey.value = null
  showMoveModal.value = true
}

function onMoveTargetSelect(keys: Array<string | number>) {
  if (!keys.length) {
    moveTargetKey.value = null
    return
  }
  const id = String(keys[0])
  const node = findNodeById(tree.value, id)
  if (!node || !canMoveTo(node) || id === selectedFolderId.value) return
  moveTargetKey.value = id
}

function findNodeById(nodes: FileFolderTreeNode[], id: string): FileFolderTreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    const child = findNodeById(n.children, id)
    if (child) return child
  }
  return null
}

async function submitBulkMove() {
  if (!selectedFolderId.value || !moveTargetKey.value) return
  const names = selectedFilenames.value
  if (!names.length) return
  bulkBusy.value = true
  try {
    const targetId = moveTargetKey.value
    const result = await bulkMoveFiles(selectedFolderId.value, names, targetId)
    if (result.failed.length === 0) {
      message.success(t('files.bulk.moveSuccess', { n: result.moved.length }))
    } else {
      message.warning(
        t('files.bulk.movePartial', {
          moved: result.moved.length,
          failed: result.failed.length,
        })
      )
    }
    showMoveModal.value = false
    clearSelection()
    await loadDetail(selectedFolderId.value)
  } catch (err) {
    const status = (err as { status?: number })?.status
    if (status === 409) {
      message.warning(t('files.error.bulkInProgress'))
    } else {
      message.error(t('files.error.bulkMove'))
    }
  } finally {
    bulkBusy.value = false
  }
}

function confirmDeleteFile(item: NCItem) {
  dialog.warning({
    title: t('files.deleteFileTitle'),
    content: `${t('files.deleteFileConfirm')} "${item.name}"?`,
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      if (!selectedFolderId.value) return
      try {
        await deleteFile(selectedFolderId.value, item.name)
        message.success(t('files.fileDeleted'))
        await loadDetail(selectedFolderId.value)
      } catch {
        message.error(t('files.error.deleteFile'))
      }
    },
  })
}

async function openCollabora(item: NCItem) {
  if (!selectedFolderId.value || openingCollaboraFile.value === item.name) return
  openingCollaboraFile.value = item.name
  try {
    const resp = await openInCollabora(selectedFolderId.value, item.name)
    window.open(resp.url, '_blank', 'noopener,noreferrer')
  } catch {
    message.error(t('files.error.collabora'))
  } finally {
    openingCollaboraFile.value = null
  }
}

function openImagePreview(item: NCItem) {
  const idx = previewImages.value.findIndex(x => x.name === item.name)
  if (idx >= 0) {
    previewInitialIndex.value = idx
    showImagePreview.value = true
  }
}

function openPdfPreview(item: NCItem) {
  if (!selectedFolderId.value) return
  window.open(previewFile(selectedFolderId.value, item.name), '_blank', 'noopener,noreferrer')
}

onMounted(() => {
  loadTree()
})
</script>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({ name: 'FilesPage' })
</script>

<style scoped>
.files-page {
  display: flex;
  height: 100%;
  min-height: 0;
  gap: 0;
}

.files-side {
  width: 260px;
  min-width: 200px;
  border-right: 1px solid var(--n-border-color, #e0e0e0);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  overflow-y: auto;
  flex-shrink: 0;
}

.files-side__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.files-side__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}

.files-side__loading,
.files-side__empty {
  font-size: 13px;
  color: var(--n-text-color-3, #999);
  padding: 8px 0;
}

.files-side__sync {
  margin-bottom: 10px;
}

.folder-tree {
  list-style: none;
  margin: 0;
  padding: 0;
}

.files-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 20px 24px;
  overflow-y: auto;
  position: relative;
}

.files-dropzone-overlay {
  position: absolute;
  inset: 0;
  background: rgba(24, 160, 88, 0.08);
  border: 2px dashed var(--n-primary-color, #18a058);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 500;
  color: var(--n-primary-color, #18a058);
  pointer-events: none;
  z-index: 10;
}

.files-bulk-bar {
  position: sticky;
  top: 0;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: var(--n-color, #fff);
  border: 1px solid var(--n-border-color, #e0e0e0);
  border-radius: 6px;
  margin-bottom: 12px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
  z-index: 5;
}

.files-bulk-bar__count {
  font-weight: 500;
  margin-right: 8px;
}

.files-bulk-bar__empty {
  color: var(--n-text-color-3, #999);
  font-size: 13px;
  margin: 12px 0;
}

.files-upload-progress {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.files-upload-progress__text {
  font-size: 12px;
  color: var(--n-text-color-3, #666);
}

.files-breadcrumbs {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  margin-bottom: 12px;
  color: var(--n-text-color-3, #666);
}

.files-breadcrumb__link {
  cursor: pointer;
  color: var(--n-primary-color, #18a058);
}

.files-breadcrumb__link:hover {
  text-decoration: underline;
}

.files-breadcrumb__sep {
  margin: 0 2px;
}

.files-breadcrumb--current {
  font-weight: 600;
  color: var(--n-text-color, #333);
}

.files-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.files-toolbar__left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.files-toolbar__right {
  display: flex;
  gap: 8px;
}

.files-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}

.files-loading-skeleton {
  padding: 4px 0;
}

.file-type-icon {
  font-size: 18px;
  line-height: 1;
  margin-right: 8px;
  flex-shrink: 0;
}

.files-cell-name {
  display: flex;
  align-items: center;
  min-width: 0;
}

.files-cell-name__text {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.files-cell-date {
  cursor: default;
  border-bottom: 1px dashed var(--n-text-color-3, #bbb);
}

.files-cell-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
</style>

<style>
.files-row--dir {
  cursor: pointer;
}
.files-row--dir:hover td {
  background: var(--n-hover-color, #f5f5f5) !important;
}
</style>


