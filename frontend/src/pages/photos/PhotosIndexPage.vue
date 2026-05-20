<template>
  <div class="photos-page">
    <PhotosSidebar
      :tree="tree"
      :loading-tree="loadingTree"
      :selected-folder-id="selectedFolderId"
      :tags="tags"
      :active-tag-filter="activeTagFilter"
      @create-root="openCreateRoot"
      @select="selectFolder"
      @create-child="openCreateChild"
      @permissions="openPermissions"
      @delete="confirmDeleteFolder"
      @drag-start="onFolderDragStart"
      @drop="onFolderDrop"
      @move-to-root="onFolderMoveToRoot"
      @set-tag-filter="setTagFilter"
      @clear-tag-filter="clearTagFilter"
      @import-scan="confirmImportScan"
      @open-trash="showTrash = true"
      @open-module-settings="manage.open('module')"
    />

    <main class="photos-main">
      <template v-if="showTrash && auth.isEditor">
        <div class="photos-trash-bar">
          <h2 class="photos-trash-bar__title">
            {{ t('photos.trash.button') }}
          </h2>
          <n-button
            size="small"
            @click="showTrash = false"
          >
            {{ t('photos.trash.back') }}
          </n-button>
        </div>
        <Suspense>
          <PhotoTrashView
            :is-admin="auth.isAdmin"
            embedded
            @close="showTrash = false"
            @tree-refresh="loadTree"
          />
        </Suspense>
      </template>

      <EmptyState
        v-else-if="!selectedFolder"
        variant="photo"
        :title="t('photos.emptyState.title')"
        :description="t('photos.emptyState.desc')"
      />

      <template v-else>
        <PhotosFolderHeader
          v-model:edit-desc-value="editDescValue"
          v-model:sort-by="sortBy"
          :folder="selectedFolder"
          :editing-description="editingDescription"
          :can-manage="canManage"
          :can-upload="canUpload"
          :select-mode="selectMode"
          @start-edit-description="startEditDescription"
          @save-description="saveDescription"
          @cancel-description="editingDescription = false"
          @toggle-select-mode="toggleSelectMode"
          @trigger-upload="triggerUpload"
          @open-permissions="openPermissions(selectedFolder)"
          @start-zip="startZip"
          @update:sort-by="onSortChange"
        />

        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept="image/*,.heic,.heif"
          style="display:none"
          aria-label="Upload photos"
          @change="onFilesPicked"
        >

        <div
          v-if="zipJob"
          class="zip-status"
        >
          <template v-if="zipJob.status === 'pending' || zipJob.status === 'processing'">
            ⏳ {{ t('photos.zip.preparing') }}
          </template>
          <template v-else-if="zipJob.status === 'done'">
            ✓ {{ t('photos.zip.ready') }}
          </template>
          <template v-else>
            ✗ {{ t('photos.zip.error') }}
          </template>
        </div>

        <PhotosUploadQueue
          :queue="uploadQueue"
          :active="uploadingActive"
          :aborted="uploadAborted"
          :done-count="uploadDoneCount"
          :total-progress="totalProgress"
          @abort="abortUpload()"
          @close="uploadQueue = []"
        />

        <PhotosGrid
          :photos="photos"
          :total-photos="totalPhotos"
          :loading="loadingPhotos"
          :select-mode="selectMode"
          :selected-photo-ids="selectedPhotoIds"
          :can-upload="canUpload"
          :can-delete="canDelete"
          :is-dragging-over="isDraggingOver"
          @photo-click="onPhotoClick"
          @toggle-select="togglePhotoSelect"
          @delete-photo="confirmDeletePhoto"
          @load-more="loadMorePhotos"
          @bulk-delete="bulkDelete"
          @open-move="openMoveModal"
          @toggle-select-mode="toggleSelectMode"
          @drag-over="isDraggingOver = true"
          @drag-leave="isDraggingOver = false"
          @drop="onDrop"
        />
      </template>
    </main>

    <LightboxModal
      v-model="lightboxIdx"
      :photos="photos"
      :selected-folder="selectedFolder"
      :selected-folder-id="selectedFolderId"
      :can-upload="canUpload"
      :can-manage="canManage"
      :tags="tags"
      :photo-tags-map="photoTagsMap"
      @tags-updated="onTagsUpdated"
    />

    <PhotoPermissionsModal
      v-model:show="permsModalOpen"
      :target="permsTarget"
    />

    <n-drawer
      v-if="auth.isAdmin"
      :show="manage.is('module')"
      :width="640"
      placement="right"
      :on-update:show="(v: boolean) => { if (!v) manage.close() }"
    >
      <n-drawer-content
        :title="t('admin.modules.openPhotosSettings')"
        closable
      >
        <Suspense>
          <PhotosModuleSettings />
        </Suspense>
      </n-drawer-content>
    </n-drawer>

    <n-modal
      v-model:show="folderModalOpen"
      preset="dialog"
      :title="t('photos.folders.create')"
      :positive-text="t('common.create')"
      :negative-text="t('common.cancel')"
      @positive-click="submitCreateFolder"
      @negative-click="folderModalOpen = false"
    >
      <n-form>
        <n-form-item :label="t('photos.folders.name')">
          <n-input
            v-model:value="newFolderName"
            :placeholder="t('photos.folders.namePlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="t('photos.folders.description')">
          <n-input
            v-model:value="newFolderDesc"
            type="textarea"
            :rows="2"
          />
        </n-form-item>
      </n-form>
    </n-modal>

    <n-modal
      v-model:show="moveModalOpen"
      preset="dialog"
      :title="t('photos.select.moveTitle')"
      :positive-text="t('common.confirm')"
      :negative-text="t('common.cancel')"
      @positive-click="confirmMove"
      @negative-click="moveModalOpen = false"
    >
      <n-form>
        <n-form-item :label="t('photos.folders.title')">
          <n-select
            v-model:value="moveTargetFolderId"
            :options="flatFolderOptions"
            filterable
          />
        </n-form-item>
      </n-form>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NModal, NSelect } from 'naive-ui'
import { useManageDrawer } from '@/composables/useManageDrawer'
import { useAuthStore } from '@/stores/auth'
import { getPhoto, type Photo } from '@/api/photos'
import EmptyState from '@/components/EmptyState.vue'
import LightboxModal from '@/components/photos/LightboxModal.vue'
import PhotoPermissionsModal from '@/components/photos/PhotoPermissionsModal.vue'
import PhotosSidebar from '@/components/photos/PhotosSidebar.vue'
import PhotosFolderHeader from '@/components/photos/PhotosFolderHeader.vue'
import PhotosUploadQueue from '@/components/photos/PhotosUploadQueue.vue'
import PhotosGrid from '@/components/photos/PhotosGrid.vue'
import { usePhotoUpload } from '@/composables/usePhotoUpload'
import { useZipExport } from '@/composables/useZipExport'
import { useImportScan } from '@/composables/useImportScan'
import { usePhotoFolderActions } from '@/composables/usePhotoFolderActions'
import { usePhotoSelection } from '@/composables/usePhotoSelection'
import { usePhotoListing } from '@/composables/usePhotoListing'
import { usePhotoFolderSelection } from '@/composables/usePhotoFolderSelection'

const route = useRoute()
const { t } = useI18n()
const auth = useAuthStore()

const lightboxIdx = ref<number | null>(null)
const showTrash = ref(false)

const manage = useManageDrawer(['module'])

const PhotoTrashView = defineAsyncComponent(() => import('@/components/photos/PhotoTrashView.vue'))
const PhotosModuleSettings = defineAsyncComponent(() => import('@/components/admin/PhotosModuleSettings.vue'))

const {
  tree,
  loadingTree,
  selectedFolderId,
  selectedFolder,
  editingDescription,
  editDescValue,
  loadTree,
  selectFolder,
  startEditDescription,
  saveDescription,
  flatten,
} = usePhotoFolderSelection({
  beforeSelect: () => {
    stopZipPolling()
    zipJob.value = null
    resetForFolder()
  },
  onAfterSelect: () => loadPhotos(),
})

const {
  photos,
  totalPhotos,
  loadingPhotos,
  sortBy,
  tags,
  photoTagsMap,
  activeTagFilter,
  loadPhotos,
  loadMorePhotos,
  onSortChange,
  reloadFromFirstPage,
  confirmDeletePhoto,
  loadTags,
  setTagFilter,
  clearTagFilter,
  onTagsUpdated,
  resetForFolder,
} = usePhotoListing({ selectedFolderId })

const {
  folderModalOpen,
  newFolderName,
  newFolderDesc,
  permsModalOpen,
  permsTarget,
  openCreateRoot,
  openCreateChild,
  submitCreateFolder,
  confirmDeleteFolder,
  openPermissions,
  onFolderDragStart,
  onFolderDrop,
  onFolderMoveToRoot,
} = usePhotoFolderActions({
  selectedFolderId,
  selectedFolder,
  photos,
  loadTree: () => loadTree(),
})

const {
  selectMode,
  selectedPhotoIds,
  moveModalOpen,
  moveTargetFolderId,
  toggleSelectMode,
  togglePhotoSelect,
  bulkDelete,
  openMoveModal,
  confirmMove,
} = usePhotoSelection({
  photos,
  totalPhotos,
  reloadPhotos: reloadFromFirstPage,
})

const canUpload = computed(() => {
  const p = selectedFolder.value?.permission
  return p === 'uploader' || p === 'manager' || auth.isAdmin
})
const canManage = computed(() => selectedFolder.value?.permission === 'manager' || auth.isAdmin)
function canDelete(p: Photo): boolean {
  return canManage.value || (auth.user?.id === p.uploaded_by)
}

const flatFolderOptions = computed(() =>
  flatten(tree.value).map(n => ({ label: n.name, value: n.id })),
)

const {
  fileInputRef,
  uploadQueue,
  uploadAborted,
  uploadingActive,
  uploadDoneCount,
  totalProgress,
  isDraggingOver,
  triggerUpload,
  abortUpload,
  onFilesPicked,
  onDrop,
} = usePhotoUpload(selectedFolderId, reloadFromFirstPage)

const { zipJob, startZip, stopZipPolling } = useZipExport(selectedFolderId)
const { confirmImportScan } = useImportScan(loadTree)

function onPhotoClick(p: Photo, idx: number) {
  if (selectMode.value) togglePhotoSelect(p.id)
  else lightboxIdx.value = idx
}

onMounted(async () => {
  await loadTree()
  loadTags()
  const id = (route.query.folder as string) || null
  if (id) {
    const flat = flatten(tree.value).find(n => n.id === id)
    if (flat) await selectFolder(flat)
  }
  const photoId = (route.query.photo as string) || null
  if (photoId) {
    const idx = photos.value.findIndex(p => p.id === photoId)
    if (idx >= 0) {
      lightboxIdx.value = idx
    } else {
      try {
        const photo = await getPhoto(photoId)
        photos.value.unshift(photo)
        lightboxIdx.value = 0
      } catch { /* noop */ }
    }
  }
})
</script>

<style scoped>
.photos-page {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 24px;
  max-width: 1440px;
  margin: 0 auto;
}
.photos-main {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px;
  min-height: 400px;
}
.zip-status {
  font-size: 13px; color: var(--color-text-muted);
  padding: 6px 0; margin-bottom: 8px;
}
.photos-trash-bar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px; gap: 12px;
}
.photos-trash-bar__title { margin: 0; font-size: 18px; font-weight: 600; }
@media (max-width: 900px) {
  .photos-page { grid-template-columns: 1fr; }
}
</style>
