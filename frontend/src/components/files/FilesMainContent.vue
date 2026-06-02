<template>
  <main
    class="files-main"
    @dragenter.prevent="dragHandlers.onMainDragEnter"
    @dragover.prevent="dragHandlers.onMainDragOver"
    @dragleave.prevent="dragHandlers.onMainDragLeave"
    @drop.prevent="dragHandlers.onMainDrop"
  >
    <FilesDropZone :active="dndActive && canUpload && sharesView === 'folders'" />
    <FilesSharesPanel
      v-if="sharesView !== 'folders'"
      :mode="(sharesView as 'my' | 'shared-with-me')"
    />
    <EmptyState
      v-else-if="!selectedFolderId"
      variant="file"
      :title="t('files.emptyState.title')"
      :description="t('files.emptyState.desc')"
    />
    <template v-else>
      <FilesBreadcrumbs
        :breadcrumbs="breadcrumbs"
        :current="currentFolder"
        @select="(id) => $emit('select-breadcrumb', id)"
      />
      <FilesToolbar
        :current-folder="currentFolder"
        :can-upload="canUpload"
        :can-manage="canManage"
        :can-edit="canEdit"
        :uploading="uploading"
        :upload-progress="uploadProgress"
        @upload-click="$emit('upload-click')"
        @manage-click="$emit('manage-click')"
      />
      <FilesBulkBar
        v-if="selectedKeys.length"
        :count="selectedKeys.length"
        :can-upload="canUpload"
        :bulk-busy="bulkBusy"
        :download-limit="BULK_DOWNLOAD_LIMIT"
        @download="$emit('bulk-download')"
        @move="$emit('bulk-move')"
        @delete="$emit('bulk-delete')"
        @clear="$emit('clear-selection')"
      />
      <div
        v-if="loadingDetail"
        class="files-loading-skeleton"
      >
        <SkeletonCard
          v-for="i in 8"
          :key="i"
          variant="file-row"
        />
      </div>
      <EmptyState
        v-else-if="!ncItems.length"
        variant="file"
        :title="t('files.emptyFolder')"
      />
      <FilesTable
        v-else
        :items="ncItems"
        :loading="loadingDetail"
        :selected-keys="selectedKeys"
        :can-upload="canUpload"
        :can-edit="canEdit"
        :can-manage="canManage"
        :folder-id="selectedFolderId"
        :opening-collabora-file="openingCollaboraFile"
        @update:selected-keys="(keys) => (selectedKeys = keys)"
        @row-click="(payload) => $emit('row-click', payload)"
        @preview-image="(item) => $emit('preview-image', item)"
        @preview-pdf="(item) => $emit('preview-pdf', item)"
        @open-collabora="(item) => $emit('open-collabora', item)"
        @delete-file="(item) => $emit('delete-file', item)"
        @share-file="(item) => $emit('share-file', item)"
      />
      <input
        :ref="(el) => setFileInputRef(el as HTMLInputElement | null)"
        type="file"
        multiple
        style="display: none"
        aria-label="Upload files"
        @change="(e) => $emit('file-change', e)"
      >
    </template>
  </main>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import EmptyState from '../EmptyState.vue'
import SkeletonCard from '../SkeletonCard.vue'
import FilesBreadcrumbs from './FilesBreadcrumbs.vue'
import FilesToolbar from './FilesToolbar.vue'
import FilesBulkBar from './FilesBulkBar.vue'
import FilesTable from './FilesTable.vue'
import FilesDropZone from './FilesDropZone.vue'
import FilesSharesPanel from './FilesSharesPanel.vue'
import { BULK_DOWNLOAD_LIMIT, type FileFolderPublic, type NCItem } from '../../api/files'

defineProps<{
  dndActive: boolean
  canUpload: boolean
  canManage: boolean
  canEdit: boolean
  sharesView: 'folders' | 'my' | 'shared-with-me'
  selectedFolderId: string | null
  breadcrumbs: FileFolderPublic[]
  currentFolder: FileFolderPublic | null
  uploading: boolean
  uploadProgress: { done: number; total: number; failed: number }
  bulkBusy: boolean
  loadingDetail: boolean
  ncItems: NCItem[]
  openingCollaboraFile: string | null
  setFileInputRef: (el: HTMLInputElement | null) => void
  dragHandlers: {
    onMainDragEnter: (e: DragEvent) => void
    onMainDragOver: (e: DragEvent) => void
    onMainDragLeave: (e: DragEvent) => void
    onMainDrop: (e: DragEvent) => void
  }
}>()

defineEmits<{
  (e: 'select-breadcrumb', id: string): void
  (e: 'upload-click' | 'manage-click'): void
  (e: 'bulk-download' | 'bulk-move' | 'bulk-delete' | 'clear-selection'): void
  (e: 'row-click', payload: { row: NCItem; index: number; event: MouseEvent }): void
  (e: 'preview-image' | 'preview-pdf' | 'open-collabora' | 'delete-file' | 'share-file', item: NCItem): void
  (e: 'file-change', event: Event): void
}>()

const selectedKeys = defineModel<string[]>('selectedKeys', { required: true })

const { t } = useI18n()
</script>

<style scoped>
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
