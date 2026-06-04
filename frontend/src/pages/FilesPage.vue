<template>
  <div class="files-page">
    <FilesSidebar
      :tree="store.tree"
      :loading="store.loadingTree"
      :selected-id="store.selectedFolderId"
      :is-admin="auth.isAdmin"
      :is-editor="auth.isEditor"
      :syncing="store.syncing"
      :active-view="sharesView"
      @select="onSelectFolder"
      @create-root="onCreateRoot"
      @create-child="onCreateChild"
      @manage="onManage"
      @delete="onDeleteFolder"
      @sync="onSync"
      @manage-icons="manage.open('file-icons')"
      @manage-shares="manage.open('file-shares')"
      @open-my-shares="sharesView = 'my'"
      @open-shared-with-me="sharesView = 'shared-with-me'"
    />
    <FilesMainContent
      v-model:selected-keys="selection.selectedKeys.value"
      :dnd-active="upload.dndActive.value"
      :can-upload="store.canUpload"
      :can-manage="store.canManage"
      :can-edit="store.canEdit"
      :shares-view="sharesView"
      :selected-folder-id="store.selectedFolderId"
      :breadcrumbs="store.breadcrumbs"
      :current-folder="store.currentFolder"
      :uploading="upload.uploading.value"
      :upload-progress="upload.uploadProgress.value"
      :bulk-busy="bulk.bulkBusy.value"
      :loading-detail="store.loadingDetail"
      :nc-items="store.ncItems"
      :opening-collabora-file="collabora.openingCollaboraFile.value"
      :set-file-input-ref="(el) => { upload.fileInputRef.value = el }"
      :drag-handlers="dragHandlers"
      @select-breadcrumb="store.selectFolder"
      @upload-click="upload.triggerUpload"
      @manage-click="onManage(store.selectedFolderId!)"
      @bulk-download="bulk.bulkDownload"
      @bulk-move="bulk.openMoveModal"
      @bulk-delete="bulk.confirmBulkDelete"
      @clear-selection="selection.clearSelection"
      @row-click="({ row, index, event }) => selection.onRowClick(row, index, event)"
      @preview-image="onPreviewImage"
      @preview-pdf="onPreviewPdf"
      @open-collabora="collabora.openCollabora"
      @delete-file="onDeleteFile"
      @share-file="onShareFile"
      @file-change="upload.handleFileInput"
    />
    <FilesModalHost
      v-model:show-create="showCreateModal"
      v-model:show-move="bulk.showMoveModal.value"
      v-model:move-target-key="bulk.moveTargetKey.value"
      v-model:show-perms="showPermsModal"
      v-model:show-share="showShareModal"
      v-model:show-image-preview="showImagePreview"
      :creating="creating"
      :move-tree-data="bulk.moveTreeData.value"
      :move-loading="bulk.bulkBusy.value"
      :perms-folder-id="permsForFolderId"
      :perms-parent-id="permsForFolderNode?.parent_id ?? null"
      :perms-inherit="permsForFolderNode?.inherit_permissions ?? true"
      :share-folder-id="store.selectedFolderId"
      :share-filename="shareFilename"
      :preview-images="previewImages"
      :preview-initial-index="previewInitialIndex"
      :preview-folder-id="store.selectedFolderId"
      :icons-drawer-open="manage.is('file-icons') && auth.isAdmin"
      :shares-drawer-open="manage.is('file-shares') && auth.isAdmin"
      @submit-create="onSubmitCreate"
      @confirm-move="bulk.submitBulkMove"
      @tree-refresh="store.loadTree()"
      @close-icons-drawer="manage.close()"
      @close-shares-drawer="manage.close()"
    />
  </div>
</template>

<script setup lang="ts">
import { useFilesPageController } from './composables/useFilesPageController'
import FilesSidebar from '../components/files/FilesSidebar.vue'
import FilesMainContent from '../components/files/FilesMainContent.vue'
import FilesModalHost from '../components/files/FilesModalHost.vue'

defineOptions({ name: 'FilesPage' })

const {
  store,
  auth,
  manage,
  selection,
  upload,
  bulk,
  collabora,
  dragHandlers,
  showCreateModal,
  creating,
  showPermsModal,
  permsForFolderId,
  permsForFolderNode,
  showShareModal,
  shareFilename,
  sharesView,
  showImagePreview,
  previewInitialIndex,
  previewImages,
  onSelectFolder,
  onCreateRoot,
  onCreateChild,
  onManage,
  onSubmitCreate,
  onDeleteFolder,
  onSync,
  onDeleteFile,
  onShareFile,
  onPreviewImage,
  onPreviewPdf,
} = useFilesPageController()
</script>

<style scoped>
.files-page {
  display: flex;
  height: 100%;
  min-height: 0;
  gap: 0;
  width: 100%;
  max-width: var(--content-wide);
  margin-inline: auto;
}
</style>
