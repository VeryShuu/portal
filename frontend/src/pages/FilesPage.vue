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
    <main class="files-main">
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
        <n-alert v-if="uploading" type="info" :title="t('files.uploading')" style="margin-bottom: 12px" />

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
          :row-props="(row: NCItem) => ({ onClick: () => onItemClick(row), class: row.is_dir ? 'files-row--dir' : '' })"
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
  NAlert,
  NButton,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NTag,
  NTooltip,
  useDialog,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import FileFolderNode from '../components/FileFolderNode.vue'
import FilesImagePreview from '../components/files/FilesImagePreview.vue'
import FilesPermissionsModal from '../components/files/FilesPermissionsModal.vue'
import { useAuthStore } from '../stores/auth'
import {
  type FileFolderPublic,
  type FileFolderTreeNode,
  type NCItem,
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
const fileInputRef = ref<HTMLInputElement | null>(null)

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
  uploading.value = true
  try {
    const result = await uploadFiles(selectedFolderId.value, files)
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

function onItemClick(item: NCItem) {
  if (item.is_dir) {
    openSubFolder(item)
  } else if (isPreviewableImage(item)) {
    openImagePreview(item)
  } else if (isPreviewablePdf(item)) {
    openPdfPreview(item)
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


