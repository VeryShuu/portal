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
      @sync="onSync"
    />
    <main
      class="files-main"
      @dragenter.prevent="upload.onMainDragEnter"
      @dragover.prevent="upload.onMainDragOver"
      @dragleave.prevent="upload.onMainDragLeave"
      @drop.prevent="upload.onMainDrop"
    >
      <FilesDropZone :active="upload.dndActive.value && store.canUpload" />
      <EmptyState v-if="!store.selectedFolderId" variant="file" :title="t('files.emptyState.title')" :description="t('files.emptyState.desc')" />
      <template v-else>
        <FilesBreadcrumbs :breadcrumbs="store.breadcrumbs" :current="store.currentFolder" @select="store.selectFolder" />
        <FilesToolbar
          :current-folder="store.currentFolder"
          :can-upload="store.canUpload"
          :can-manage="store.canManage"
          :uploading="upload.uploading.value"
          :upload-progress="upload.uploadProgress.value"
          @upload-click="upload.triggerUpload"
          @manage-click="onManage(store.selectedFolderId!)"
        />
        <FilesBulkBar
          v-if="selection.selectedKeys.value.length"
          :count="selection.selectedKeys.value.length"
          :can-upload="store.canUpload"
          :bulk-busy="bulk.bulkBusy.value"
          :download-limit="BULK_DOWNLOAD_LIMIT"
          @download="bulk.bulkDownload"
          @move="bulk.openMoveModal"
          @delete="bulk.confirmBulkDelete"
          @clear="selection.clearSelection"
        />
        <div v-if="store.loadingDetail" class="files-loading-skeleton">
          <SkeletonCard v-for="i in 8" :key="i" variant="file-row" />
        </div>
        <EmptyState v-else-if="!store.ncItems.length" variant="file" :title="t('files.emptyFolder')" />
        <FilesTable
          v-else
          :items="store.ncItems"
          :loading="store.loadingDetail"
          :selected-keys="selection.selectedKeys.value"
          :can-upload="store.canUpload"
          :folder-id="store.selectedFolderId"
          :opening-collabora-file="collabora.openingCollaboraFile.value"
          @update:selected-keys="selection.selectedKeys.value = $event"
          @row-click="({ row, index, event }) => selection.onRowClick(row, index, event)"
          @preview-image="onPreviewImage"
          @preview-pdf="onPreviewPdf"
          @open-collabora="collabora.openCollabora"
          @delete-file="onDeleteFile"
        />
        <input
          :ref="(el) => { upload.fileInputRef.value = el as HTMLInputElement | null }"
          type="file" multiple style="display: none"
          @change="upload.handleFileInput"
        />
      </template>
    </main>
    <FilesCreateFolderModal v-model:show="showCreateModal" :loading="creating" @submit="onSubmitCreate" />
    <FilesMoveModal
      v-model:show="bulk.showMoveModal.value"
      :tree-data="bulk.moveTreeData.value"
      :target-key="bulk.moveTargetKey.value"
      :loading="bulk.bulkBusy.value"
      @update:target-key="bulk.moveTargetKey.value = $event"
      @confirm="bulk.submitBulkMove"
    />
    <FilesPermissionsModal v-model:show="showPermsModal" :folder-id="permsForFolderId" />
    <FilesImagePreview
      v-if="showImagePreview && store.selectedFolderId"
      :images="previewImages"
      :initial-index="previewInitialIndex"
      :folder-id="store.selectedFolderId"
      @close="showImagePreview = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import { useFilesStore } from '../stores/files'
import { useAuthStore } from '../stores/auth'
import { useFilesSelection } from '../composables/useFilesSelection'
import { useFilesUpload } from '../composables/useFilesUpload'
import { useFilesBulkOps } from '../composables/useFilesBulkOps'
import { useCollabora } from '../composables/useCollabora'
import { BULK_DOWNLOAD_LIMIT, deleteFile, isPreviewableImage, isPreviewablePdf, previewFile, type NCItem } from '../api/files'
import EmptyState from '../components/EmptyState.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import FilesSidebar from '../components/files/FilesSidebar.vue'
import FilesBreadcrumbs from '../components/files/FilesBreadcrumbs.vue'
import FilesToolbar from '../components/files/FilesToolbar.vue'
import FilesBulkBar from '../components/files/FilesBulkBar.vue'
import FilesTable from '../components/files/FilesTable.vue'
import FilesDropZone from '../components/files/FilesDropZone.vue'
import FilesCreateFolderModal from '../components/files/FilesCreateFolderModal.vue'
import FilesMoveModal from '../components/files/FilesMoveModal.vue'
import FilesPermissionsModal from '../components/files/FilesPermissionsModal.vue'
import FilesImagePreview from '../components/files/FilesImagePreview.vue'

defineOptions({ name: 'FilesPage' })

const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()
const store = useFilesStore()
const auth = useAuthStore()

const selection = useFilesSelection(toRef(store, 'ncItems'), toRef(store, 'selectedFolderId'), {
  onOpenDir(item) {
    const node = store.findNodeByNcPath(item.nc_path)
    if (node) store.selectFolder(node.id)
  },
  onPreview(item) {
    if (isPreviewableImage(item)) onPreviewImage(item)
    else if (isPreviewablePdf(item)) onPreviewPdf(item)
  },
})
const upload = useFilesUpload(toRef(store, 'selectedFolderId'), () => store.refreshCurrent())
const bulk = useFilesBulkOps({
  folderId: toRef(store, 'selectedFolderId'),
  selectedFilenames: selection.selectedFilenames,
  clearSelection: selection.clearSelection,
  onAfterMutation: () => store.refreshCurrent(),
})
const collabora = useCollabora(toRef(store, 'selectedFolderId'))

const showCreateModal = ref(false)
const createParentId = ref<string | null>(null)
const creating = ref(false)
const showPermsModal = ref(false)
const permsForFolderId = ref<string | null>(null)
const showImagePreview = ref(false)
const previewInitialIndex = ref(0)
const previewImages = computed(() => store.ncItems.filter(isPreviewableImage))

onMounted(async () => {
  try { await store.loadTree() } catch { message.error(t('files.error.loadTree')) }
})
watch(() => store.selectedFolderId, async (id) => {
  if (id) try { await store.loadDetail(id) } catch { message.error(t('files.error.loadFolder')) }
})

function onCreateRoot() { createParentId.value = null; showCreateModal.value = true }
function onCreateChild(folderId: string) { createParentId.value = folderId; showCreateModal.value = true }
function onManage(folderId: string) { permsForFolderId.value = folderId; showPermsModal.value = true }

async function onSubmitCreate(payload: { name: string; description: string | null }) {
  creating.value = true
  try {
    await store.createFolder({ name: payload.name, parent_id: createParentId.value, description: payload.description })
    showCreateModal.value = false
    message.success(t('files.folders.created'))
  } catch {
    message.error(t('files.error.createFolder'))
  } finally {
    creating.value = false
  }
}

async function onDeleteFolder(folderId: string) {
  const ok = await confirm({ title: t('files.folders.deleteTitle'), content: t('files.folders.deleteConfirm'), positiveText: t('common.delete'), negativeText: t('common.cancel') })
  if (!ok) return
  try { await store.deleteFolder(folderId); message.success(t('files.folders.deleted')) }
  catch { message.error(t('files.error.deleteFolder')) }
}

async function onSync() {
  try { const r = await store.syncFromNextcloud(); message.success(t('files.sync.success', { created: r.created, skipped: r.skipped })) }
  catch { message.error(t('files.sync.error')) }
}

async function onDeleteFile(item: NCItem) {
  const ok = await confirm({ title: t('files.deleteFileTitle'), content: `${t('files.deleteFileConfirm')} "${item.name}"?`, positiveText: t('common.delete'), negativeText: t('common.cancel') })
  if (!ok || !store.selectedFolderId) return
  try { await deleteFile(store.selectedFolderId, item.name); message.success(t('files.fileDeleted')); await store.refreshCurrent() }
  catch { message.error(t('files.error.deleteFile')) }
}

function onPreviewImage(item: NCItem) {
  const idx = previewImages.value.findIndex((x: NCItem) => x.name === item.name)
  if (idx >= 0) { previewInitialIndex.value = idx; showImagePreview.value = true }
}
function onPreviewPdf(item: NCItem) {
  if (store.selectedFolderId) window.open(previewFile(store.selectedFolderId, item.name), '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.files-page {
  display: flex;
  height: 100%;
  min-height: 0;
  gap: 0;
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
.files-loading-skeleton {
  padding: 4px 0;
}
</style>
