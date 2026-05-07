<template>
  <div class="photos-page">
    <!-- Sidebar: folder tree -->
    <aside class="photos-side">
      <div class="photos-side__head">
        <h2 class="photos-side__title">{{ t('photos.folders.title') }}</h2>
        <n-button
          v-if="auth.isAdmin"
          size="tiny"
          @click="openCreateRoot"
        >+ {{ t('photos.folders.newRoot') }}</n-button>
      </div>

      <div v-if="loadingTree" class="photos-side__loading">
        <SkeletonCard v-for="i in 6" :key="i" variant="folder-item" />
      </div>
      <ul v-else-if="tree.length" class="folder-tree">
        <FolderNode
          v-for="n in tree"
          :key="n.id"
          :node="n"
          :selected-id="selectedFolderId"
          @select="selectFolder"
          @subfolder="openCreateChild"
          @permissions="openPermissions"
          @delete="confirmDeleteFolder"
          @drag-start="onFolderDragStart"
          @drop="onFolderDrop"
          @move-to-root="onFolderMoveToRoot"
        />
      </ul>
      <p v-else class="photos-side__empty">{{ t('photos.folders.empty') }}</p>

      <div v-if="tags.length" class="photos-side__tags">
        <div class="photos-side__tags-head">
          <span class="photos-side__tags-title">{{ t('photos.tags.title') }}</span>
          <button v-if="activeTagFilter" class="photos-side__tags-clear" @click="clearTagFilter">× {{ t('photos.tags.clearFilter') }}</button>
        </div>
        <div class="tag-cloud">
          <button
            v-for="tag in tags"
            :key="tag.id"
            class="tag-chip"
            :class="{ 'tag-chip--active': activeTagFilter === tag.id }"
            @click="setTagFilter(tag)"
          >{{ tag.name }}</button>
        </div>
      </div>

      <div class="photos-side__trash">
        <button class="photos-side__trash-btn" @click="openTrash">
          {{ t('photos.trash.button') }}
          <span v-if="trashTotal > 0" class="photos-side__trash-badge">{{ trashTotal }}</span>
        </button>
      </div>

      <div v-if="auth.isAdmin" class="photos-side__import">
        <n-button size="small" block @click="confirmImportScan">
          {{ t('photos.import.button') }}
        </n-button>
      </div>

      <div class="photos-side__myshares">
        <button class="photos-side__myshares-btn" @click="router.push('/photos/my-shares')">
          {{ t('photos.myShares.title') }}
        </button>
      </div>
    </aside>

    <!-- Main: photos in folder -->
    <main class="photos-main">
      <!-- Trash mode -->
      <PhotoTrashView
        v-if="trashMode"
        :is-admin="auth.isAdmin"
        @close="trashMode = false"
        @total-changed="trashTotal = $event"
        @tree-refresh="loadTree"
      />

      <!-- Normal mode -->
      <template v-else>
        <EmptyState
          v-if="!selectedFolder"
          variant="photo"
          :title="t('photos.emptyState.title')"
          :description="t('photos.emptyState.desc')"
        />

        <template v-else>
          <header class="photos-header">
            <div class="photos-header__info">
              <h1 class="photos-title">{{ selectedFolder.name }}</h1>

              <div v-if="editingDescription" class="desc-edit">
                <n-input
                  v-model:value="editDescValue"
                  type="textarea"
                  :rows="2"
                  :placeholder="t('photos.folders.description')"
                />
                <div class="desc-edit__actions">
                  <n-button size="small" type="primary" @click="saveDescription">{{ t('common.save') }}</n-button>
                  <n-button size="small" @click="editingDescription = false">{{ t('common.cancel') }}</n-button>
                </div>
              </div>
              <template v-else>
                <p v-if="selectedFolder.description" class="photos-desc">{{ selectedFolder.description }}</p>
                <button
                  v-else-if="canManage"
                  class="photos-add-desc"
                  @click="startEditDescription"
                >+ {{ t('photos.folders.addDescription') }}</button>
              </template>

              <p class="photos-meta">{{ t('photos.count', { n: selectedFolder.photos_count }) }}</p>
            </div>
            <div class="photos-actions">
              <n-select
                v-model:value="sortBy"
                :options="[
                  { label: t('photos.sort.createdAt'), value: 'created_at' },
                  { label: t('photos.sort.takenAt'), value: 'taken_at' },
                  { label: t('photos.sort.name'), value: 'original_name' },
                ]"
                style="width: 160px"
                @update:value="onSortChange"
              />
              <n-button v-if="canUpload" @click="toggleSelectMode">
                {{ selectMode ? t('photos.select.cancel') : t('photos.select.mode') }}
              </n-button>
              <n-button v-if="canUpload" type="primary" @click="triggerUpload">
                + {{ t('photos.upload.button') }}
              </n-button>
              <n-button v-if="canManage" @click="openPermissions(selectedFolder)">
                {{ t('photos.permissions.manage') }}
              </n-button>
              <n-button v-if="selectedFolder" @click="startZip">
                ⬇ {{ t('photos.zip.download') }}
              </n-button>
              <input
                ref="fileInputRef"
                type="file"
                multiple
                accept="image/*,.heic,.heif"
                style="display:none"
                @change="onFilesPicked"
              />
            </div>
          </header>

          <div v-if="zipJob" class="zip-status">
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

          <div v-if="uploadQueue.length" class="upload-queue">
            <div class="upload-queue__header">
              <span>{{ t('photos.upload.progress', { done: uploadDoneCount, total: uploadQueue.length }) }}</span>
              <n-button
                v-if="uploadingActive && !uploadAborted"
                size="tiny"
                type="error"
                ghost
                @click="abortUpload()"
              >{{ t('photos.upload.cancel') }}</n-button>
              <n-button
                v-if="!uploadingActive"
                size="tiny"
                @click="uploadQueue = []"
              >{{ t('common.close') }}</n-button>
            </div>
            <ul class="upload-queue__list">
              <li v-for="(item, i) in uploadQueue" :key="i" class="upload-queue__item">
                <span class="upload-queue__status">
                  <template v-if="item.status === 'pending'">⏳</template>
                  <template v-else-if="item.status === 'uploading'">🔄</template>
                  <template v-else-if="item.status === 'done'">✓</template>
                  <template v-else>✗</template>
                </span>
                <span class="upload-queue__name">{{ item.file.name }}</span>
                <span v-if="item.error" class="upload-queue__error">{{ item.error }}</span>
              </li>
            </ul>
          </div>

          <div
            class="photo-grid-drop-zone"
            :class="{ 'drag-over': isDraggingOver && canUpload }"
            @dragover.prevent="isDraggingOver = canUpload"
            @dragleave="isDraggingOver = false"
            @drop.prevent="canUpload ? onDrop($event) : (isDraggingOver = false)"
          >
            <div v-if="loadingPhotos" class="photo-grid">
              <div v-for="i in 12" :key="`pgsk-${i}`" class="photo-skeleton" />
            </div>
            <div v-else-if="photos.length" class="photo-grid">
              <div
                v-for="(p, idx) in photos"
                :key="p.id"
                class="photo-cell"
                :class="{ 'photo-cell--selected': selectedPhotoIds.has(p.id) }"
                draggable="false"
                @click="onPhotoClick(p, idx)"
              >
                <picture>
                  <source :srcset="`${thumbUrl(p.id, 400)} 400w, ${thumbUrl(p.id, 600)} 600w`" sizes="(max-width: 400px) 400px, 600px" />
                  <img
                    :src="thumbUrl(p.id, 600)"
                    :alt="p.original_name"
                    loading="lazy"
                    draggable="false"
                    class="photo-cell__img"
                  />
                </picture>
                <label v-if="selectMode" class="photo-cell__check" @click.stop>
                  <input type="checkbox" :checked="selectedPhotoIds.has(p.id)" @change="togglePhotoSelect(p.id)" />
                </label>
                <button
                  v-if="canDelete(p) && !selectMode"
                  class="photo-cell__del"
                  :aria-label="t('common.delete')"
                  @click.stop="confirmDeletePhoto(p)"
                >×</button>
              </div>
            </div>
            <EmptyState v-else variant="photo" :title="t('photos.empty')" />
            <div v-if="isDraggingOver && canUpload" class="drop-overlay">
              {{ t('photos.upload.dropHere') }}
            </div>
          </div>

          <div v-if="totalPhotos > photos.length" class="photo-loadmore">
            <n-button @click="loadMorePhotos">{{ t('common.loadMore') }}</n-button>
          </div>

          <div v-if="selectMode" class="multiselect-toolbar">
            <span>{{ t('photos.select.count', { n: selectedPhotoIds.size }) }}</span>
            <n-button size="small" type="error" :disabled="selectedPhotoIds.size === 0" @click="bulkDelete">{{ t('photos.select.delete') }}</n-button>
            <n-button size="small" :disabled="selectedPhotoIds.size === 0" @click="openMoveModal">{{ t('photos.select.move') }}</n-button>
            <n-button size="small" @click="toggleSelectMode">{{ t('photos.select.cancel') }}</n-button>
          </div>
        </template>
      </template>
    </main>

    <!-- Lightbox -->
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

    <!-- Permissions modal -->
    <PhotoPermissionsModal
      v-model:show="permsModalOpen"
      :target="permsTarget"
    />

    <!-- Create folder modal -->
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
          <n-input v-model:value="newFolderName" :placeholder="t('photos.folders.namePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('photos.folders.description')">
          <n-input v-model:value="newFolderDesc" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
    </n-modal>

    <!-- Move folder modal -->
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
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NButton, NForm, NFormItem, NInput, NModal, NSelect, useDialog, useMessage,
} from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import {
  fetchFolderTree, fetchFolder, fetchFolderPhotos, createFolder, deleteFolder,
  updateFolder, getPhoto, deletePhoto,
  thumbUrl,
  fetchDeletedPhotos,
  bulkAction, startFolderZip, getZipJob, zipJobDownloadUrl, importScan, getImportScanStatus,
  fetchFolderPhotosFiltered, moveFolder,
  fetchTags,
  type Photo, type PhotoFolder, type PhotoFolderTreeNode, type PhotoTag,
  type ZipJob, type FolderPhotosParams,
} from '@/api/photos'
import SkeletonCard from '@/components/SkeletonCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import FolderNode from '@/components/photos/FolderNode.vue'
import LightboxModal from '@/components/photos/LightboxModal.vue'
import PhotoPermissionsModal from '@/components/photos/PhotoPermissionsModal.vue'
import PhotoTrashView from '@/components/photos/PhotoTrashView.vue'
import { usePhotoUpload } from '@/composables/usePhotoUpload'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()

const tree = ref<PhotoFolderTreeNode[]>([])
const loadingTree = ref(false)
const selectedFolderId = ref<string | null>(null)
const selectedFolder = ref<PhotoFolder | null>(null)
const photos = ref<Photo[]>([])
const totalPhotos = ref(0)
const page = ref(1)
const pageSize = 60
const loadingPhotos = ref(false)

const sortBy = ref<'created_at' | 'taken_at' | 'original_name'>('created_at')

const selectMode = ref(false)
const selectedPhotoIds = ref<Set<string>>(new Set())

const editingDescription = ref(false)
const editDescValue = ref('')

const folderModalOpen = ref(false)
const newFolderParent = ref<string | null>(null)
const newFolderName = ref('')
const newFolderDesc = ref('')

const permsModalOpen = ref(false)
const permsTarget = ref<PhotoFolder | PhotoFolderTreeNode | null>(null)

const trashMode = ref(false)
const trashTotal = ref(0)

const zipJob = ref<ZipJob | null>(null)
const zipPolling = ref<ReturnType<typeof setInterval> | null>(null)

const moveModalOpen = ref(false)
const moveTargetFolderId = ref<string | null>(null)

const tags = ref<PhotoTag[]>([])
const photoTagsMap = ref<Record<string, PhotoTag[]>>({})
const activeTagFilter = ref<string | null>(null)

const draggingFolderNode = ref<PhotoFolderTreeNode | null>(null)

const lightboxIdx = ref<number | null>(null)

const canUpload = computed(() => {
  const p = selectedFolder.value?.permission
  return p === 'uploader' || p === 'manager' || auth.isAdmin
})
const canManage = computed(() => selectedFolder.value?.permission === 'manager' || auth.isAdmin)
function canDelete(p: Photo): boolean {
  return canManage.value || (auth.user?.id === p.uploaded_by)
}

const hasActiveFilters = computed(() => !!activeTagFilter.value)

const flatFolderOptions = computed(() =>
  flatten(tree.value).map(n => ({ label: n.name, value: n.id })),
)

const {
  fileInputRef,
  uploadQueue,
  uploadAborted,
  uploadingActive,
  uploadDoneCount,
  isDraggingOver,
  triggerUpload,
  abortUpload,
  onFilesPicked,
  onDrop,
} = usePhotoUpload(selectedFolderId, async () => {
  page.value = 1
  await loadPhotos()
})

function onTagsUpdated(photoId: string, updatedTags: PhotoTag[]) {
  photoTagsMap.value = { ...photoTagsMap.value, [photoId]: updatedTags }
}

async function loadTree() {
  loadingTree.value = true
  try {
    const data = await fetchFolderTree()
    tree.value = data.items
  } catch {
    message.error(t('errors.generic'))
  } finally {
    loadingTree.value = false
  }
}

async function selectFolder(node: PhotoFolderTreeNode) {
  stopZipPolling()
  zipJob.value = null
  selectedFolderId.value = node.id
  page.value = 1
  photos.value = []
  totalPhotos.value = 0
  try {
    selectedFolder.value = await fetchFolder(node.id)
    await loadPhotos()
  } catch {
    message.error(t('errors.generic'))
  }
}

async function loadPhotos() {
  if (!selectedFolderId.value) return
  loadingPhotos.value = true
  try {
    const params: FolderPhotosParams = { page: page.value, per_page: pageSize, sort: sortBy.value }
    if (activeTagFilter.value) params.tag_id = activeTagFilter.value
    const res = hasActiveFilters.value
      ? await fetchFolderPhotosFiltered(selectedFolderId.value, params)
      : await fetchFolderPhotos(selectedFolderId.value, { page: page.value, per_page: pageSize, sort: sortBy.value })
    if (page.value === 1) photos.value = res.items
    else photos.value = [...photos.value, ...res.items]
    totalPhotos.value = res.total
  } finally {
    loadingPhotos.value = false
  }
}

async function loadMorePhotos() {
  page.value++
  await loadPhotos()
}

function onSortChange() {
  page.value = 1
  photos.value = []
  loadPhotos()
}

function openCreateRoot() {
  newFolderParent.value = null
  newFolderName.value = ''
  newFolderDesc.value = ''
  folderModalOpen.value = true
}

function openCreateChild(node: PhotoFolderTreeNode) {
  newFolderParent.value = node.id
  newFolderName.value = ''
  newFolderDesc.value = ''
  folderModalOpen.value = true
}

async function submitCreateFolder() {
  if (!newFolderName.value.trim()) { message.warning(t('photos.folders.nameRequired')); return false }
  try {
    await createFolder({
      parent_id: newFolderParent.value,
      name: newFolderName.value.trim(),
      description: newFolderDesc.value.trim() || null,
    })
    message.success(t('photos.folders.created'))
    folderModalOpen.value = false
    await loadTree()
  } catch {
    message.error(t('errors.generic'))
    return false
  }
}

function confirmDeleteFolder(node: PhotoFolderTreeNode) {
  dialog.warning({
    title: t('photos.folders.deleteTitle'),
    content: t('photos.folders.deleteConfirm', { name: node.name }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await deleteFolder(node.id)
        message.success(t('photos.folders.deleted'))
        if (selectedFolderId.value === node.id) {
          selectedFolderId.value = null
          selectedFolder.value = null
          photos.value = []
        }
        await loadTree()
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

function confirmDeletePhoto(p: Photo) {
  dialog.warning({
    title: t('photos.deleteTitle'),
    content: t('photos.deleteConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await deletePhoto(p.id)
        photos.value = photos.value.filter(x => x.id !== p.id)
        totalPhotos.value = Math.max(0, totalPhotos.value - 1)
        message.success(t('photos.deleted'))
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

function openPermissions(node: PhotoFolder | PhotoFolderTreeNode) {
  permsTarget.value = node
  permsModalOpen.value = true
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) selectedPhotoIds.value = new Set()
}

function togglePhotoSelect(id: string) {
  const s = new Set(selectedPhotoIds.value)
  if (s.has(id)) s.delete(id); else s.add(id)
  selectedPhotoIds.value = s
}

function onPhotoClick(p: Photo, idx: number) {
  if (selectMode.value) togglePhotoSelect(p.id)
  else lightboxIdx.value = idx
}

function startEditDescription() {
  editDescValue.value = selectedFolder.value?.description ?? ''
  editingDescription.value = true
}

async function saveDescription() {
  if (!selectedFolder.value) return
  try {
    const updated = await updateFolder(selectedFolder.value.id, { description: editDescValue.value.trim() || null })
    selectedFolder.value = updated
    editingDescription.value = false
    message.success(t('photos.folders.descriptionSaved'))
  } catch {
    message.error(t('errors.generic'))
  }
}

async function loadTags() {
  try {
    const data = await fetchTags()
    tags.value = data.items
  } catch { }
}

function setTagFilter(tag: PhotoTag) {
  activeTagFilter.value = activeTagFilter.value === tag.id ? null : tag.id
  page.value = 1
  photos.value = []
  loadPhotos()
}

function clearTagFilter() {
  activeTagFilter.value = null
  page.value = 1
  photos.value = []
  loadPhotos()
}

function onFolderDragStart(node: PhotoFolderTreeNode) {
  draggingFolderNode.value = node
}

function onFolderDrop(targetNode: PhotoFolderTreeNode) {
  const dragged = draggingFolderNode.value
  draggingFolderNode.value = null
  if (!dragged || dragged.id === targetNode.id) return
  dialog.warning({
    title: t('photos.folders.moveTo', { name: targetNode.name }),
    content: t('photos.folders.moveConfirm', { name: dragged.name, target: targetNode.name }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await moveFolder(dragged.id, targetNode.id)
        message.success(t('photos.folders.moved'))
        await loadTree()
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

function onFolderMoveToRoot(node: PhotoFolderTreeNode) {
  dialog.warning({
    title: t('photos.folders.moveToRootTitle'),
    content: t('photos.folders.moveToRootConfirm', { name: node.name }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await moveFolder(node.id, null)
        message.success(t('photos.folders.moved'))
        await loadTree()
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

function stopZipPolling() {
  if (zipPolling.value !== null) { clearInterval(zipPolling.value); zipPolling.value = null }
}

async function startZip() {
  if (!selectedFolderId.value) return
  stopZipPolling()
  zipJob.value = null
  try {
    const job = await startFolderZip(selectedFolderId.value)
    zipJob.value = job
    if (job.status === 'done') {
      window.open(zipJobDownloadUrl(job.id), '_blank', 'noopener,noreferrer')
      message.success(t('photos.zip.ready'))
      return
    }
    if (job.status === 'error') { message.error(t('photos.zip.error')); return }
    let pollAttempts = 0
    const ZIP_POLL_LIMIT = 60
    zipPolling.value = setInterval(async () => {
      pollAttempts++
      if (pollAttempts > ZIP_POLL_LIMIT) {
        stopZipPolling(); zipJob.value = null; message.error(t('photos.zip.timeout')); return
      }
      try {
        const updated = await getZipJob(zipJob.value!.id)
        zipJob.value = updated
        if (updated.status === 'done') {
          stopZipPolling()
          window.open(zipJobDownloadUrl(updated.id), '_blank', 'noopener,noreferrer')
          message.success(t('photos.zip.ready'))
        } else if (updated.status === 'error') {
          stopZipPolling(); message.error(t('photos.zip.error'))
        }
      } catch {
        stopZipPolling(); message.error(t('errors.generic'))
      }
    }, 2000)
  } catch {
    message.error(t('errors.generic'))
  }
}

function bulkDelete() {
  if (selectedPhotoIds.value.size === 0) return
  const ids = [...selectedPhotoIds.value]
  dialog.warning({
    title: t('photos.select.delete'),
    content: t('photos.select.deleteConfirm', { n: ids.length }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        const res = await bulkAction({ action: 'delete', photo_ids: ids })
        photos.value = photos.value.filter(p => !ids.includes(p.id))
        totalPhotos.value = Math.max(0, totalPhotos.value - res.processed)
        message.success(t('photos.select.deleteDone', { n: res.processed }))
        toggleSelectMode()
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

function openMoveModal() {
  if (selectedPhotoIds.value.size === 0) return
  moveTargetFolderId.value = null
  moveModalOpen.value = true
}

async function confirmMove() {
  if (!moveTargetFolderId.value) return false
  const ids = [...selectedPhotoIds.value]
  try {
    const res = await bulkAction({ action: 'move', photo_ids: ids, target_folder_id: moveTargetFolderId.value })
    message.success(t('photos.select.moveDone', { n: res.processed }))
    moveModalOpen.value = false
    toggleSelectMode()
    page.value = 1
    await loadPhotos()
  } catch {
    message.error(t('errors.generic'))
    return false
  }
}

let importPollTimer: ReturnType<typeof setTimeout> | null = null

function confirmImportScan() {
  dialog.warning({
    title: t('photos.import.button'),
    content: t('photos.import.confirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        const job = await importScan()
        message.info(t('photos.import.queued'))
        const poll = async () => {
          const s = await getImportScanStatus(job.job_id)
          if (s.status === 'complete') {
            importPollTimer = null
            if (s.result) {
              message.success(t('photos.import.done', { photos: s.result.photos_imported, folders: s.result.folders_created, skipped: s.result.skipped }))
            }
            await loadTree()
          } else if (s.status === 'queued' || s.status === 'in_progress' || s.status === 'deferred') {
            importPollTimer = setTimeout(poll, 2000)
          } else {
            importPollTimer = null
            message.error(t('errors.generic'))
          }
        }
        importPollTimer = setTimeout(poll, 2000)
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

async function openTrash() {
  trashMode.value = true
}

async function loadTrashCount() {
  try {
    const res = await fetchDeletedPhotos({ page: 1, per_page: 1 })
    trashTotal.value = res.total
  } catch { }
}

function flatten(nodes: PhotoFolderTreeNode[]): PhotoFolderTreeNode[] {
  const out: PhotoFolderTreeNode[] = []
  const walk = (ns: PhotoFolderTreeNode[]) => {
    for (const n of ns) {
      out.push(n)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(nodes)
  return out
}

onMounted(async () => {
  await loadTree()
  loadTrashCount()
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
      } catch { }
    }
  }
})

onUnmounted(() => {
  stopZipPolling()
  if (importPollTimer) clearTimeout(importPollTimer)
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
.photos-side {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px;
  height: fit-content;
  position: sticky;
  top: 16px;
}
.photos-side__head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px;
}
.photos-side__title { margin: 0; font-size: 14px; font-weight: 700; }
.photos-side__loading, .photos-side__empty {
  font-size: 13px; color: var(--color-text-muted); margin: 12px 0;
}
.folder-tree { list-style: none; margin: 0; padding: 0; }

.photos-main {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px;
  min-height: 400px;
}
.photos-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 20px; gap: 16px;
}
.photos-header__info { flex: 1; min-width: 0; }
.photos-title { margin: 0 0 4px; font-size: 22px; }
.photos-desc { margin: 0 0 4px; color: var(--color-text-muted); }
.photos-meta { margin: 0; font-size: 12px; color: var(--color-text-muted); }
.photos-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-start; }
.photos-add-desc {
  background: transparent; border: 0; cursor: pointer;
  font-size: 13px; color: var(--color-text-muted); padding: 0; margin: 0 0 4px;
  text-decoration: underline dashed;
}
.photos-add-desc:hover { color: var(--color-text); }

.desc-edit { margin-bottom: 8px; }
.desc-edit__actions { display: flex; gap: 8px; margin-top: 8px; }

.upload-queue {
  background: var(--color-bg-muted);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.upload-queue__header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 6px;
}
.upload-queue__list { list-style: none; margin: 0; padding: 0; max-height: 160px; overflow-y: auto; }
.upload-queue__item {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 0; border-bottom: 1px solid var(--color-border);
}
.upload-queue__item:last-child { border-bottom: 0; }
.upload-queue__status { flex-shrink: 0; font-size: 14px; }
.upload-queue__name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.upload-queue__error { font-size: 11px; color: var(--color-error, #e53e3e); flex-shrink: 0; }

.photo-grid-drop-zone {
  position: relative;
  border: 2px dashed transparent;
  border-radius: var(--radius-sm);
  transition: border-color 0.15s;
}
.photo-grid-drop-zone.drag-over {
  border-color: var(--color-primary, #3b82f6);
}
.drop-overlay {
  position: absolute; inset: 0;
  background: rgba(59, 130, 246, 0.15);
  border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 600; color: var(--color-primary, #3b82f6);
  pointer-events: none;
}

.photo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.photo-cell {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: var(--color-bg-muted);
  cursor: pointer;
}
.photo-cell--selected { outline: 3px solid var(--color-primary, #3b82f6); }
.photo-cell__img {
  width: 100%; height: 100%; object-fit: cover;
  transition: transform 0.2s ease;
}
.photo-cell:hover .photo-cell__img { transform: scale(1.04); }
.photo-cell__del {
  position: absolute; top: 4px; right: 4px;
  background: rgba(0,0,0,0.6); color: #fff; border: 0; cursor: pointer;
  width: 24px; height: 24px; border-radius: 50%; font-size: 16px; line-height: 1;
  display: none;
}
.photo-cell:hover .photo-cell__del { display: inline-flex; align-items: center; justify-content: center; }
.photo-cell__check {
  position: absolute; top: 6px; left: 6px;
  width: 20px; height: 20px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.photo-cell__check input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }

.photo-skeleton {
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-border) 50%, var(--color-bg-muted) 75%);
  background-size: 200% 100%;
  animation: skel 1.4s infinite;
}
@keyframes skel { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

.photo-loadmore { text-align: center; margin-top: 16px; }

.multiselect-toolbar {
  position: sticky; bottom: 0;
  display: flex; align-items: center; gap: 10px;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
  padding: 10px 0;
  margin-top: 16px;
}

.zip-status {
  font-size: 13px; color: var(--color-text-muted);
  padding: 6px 0; margin-bottom: 8px;
}

.photos-side__trash {
  margin-top: 12px;
  border-top: 1px solid var(--color-border);
  padding-top: 10px;
}
.photos-side__trash-btn {
  background: transparent; border: 0; cursor: pointer; padding: 0;
  font-size: 13px; color: var(--color-text-muted);
  display: flex; align-items: center; gap: 6px;
  width: 100%; text-align: left;
}
.photos-side__trash-btn:hover { color: var(--color-text); }
.photos-side__trash-badge {
  background: var(--color-border-strong); color: var(--color-text-muted);
  border-radius: 999px; font-size: 10px; font-weight: 700;
  padding: 1px 6px; min-width: 18px; text-align: center;
}
.photos-side__import { margin-top: 8px; }

.photos-side__tags {
  margin-top: 12px;
  border-top: 1px solid var(--color-border);
  padding-top: 10px;
}
.photos-side__tags-head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;
}
.photos-side__tags-title {
  font-size: 12px; font-weight: 600; color: var(--color-text-muted); text-transform: uppercase;
}
.photos-side__tags-clear {
  background: transparent; border: 0; cursor: pointer; font-size: 11px; color: var(--color-text-muted);
}
.photos-side__tags-clear:hover { color: var(--color-text); }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 4px; }
.tag-chip {
  background: var(--color-bg-muted); border: 1px solid var(--color-border);
  border-radius: 999px; padding: 2px 8px; font-size: 11px; cursor: pointer;
  color: var(--color-text); white-space: nowrap;
}
.tag-chip:hover { background: var(--color-border); }
.tag-chip--active { background: var(--color-primary, #3b82f6); color: #fff; border-color: var(--color-primary, #3b82f6); }

.photos-side__myshares {
  margin-top: 8px;
  border-top: 1px solid var(--color-border);
  padding-top: 10px;
}
.photos-side__myshares-btn {
  background: transparent; border: 0; cursor: pointer; padding: 0;
  font-size: 13px; color: var(--color-text-muted); text-align: left; width: 100%;
}
.photos-side__myshares-btn:hover { color: var(--color-text); text-decoration: underline; }

@media (max-width: 900px) {
  .photos-page { grid-template-columns: 1fr; }
  .photos-side { position: static; }
}
</style>
