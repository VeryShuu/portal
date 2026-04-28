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

      <div v-if="loadingTree" class="photos-side__loading">{{ t('common.loading') }}</div>
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
      <div v-if="trashMode" class="trash-view">
        <header class="photos-header">
          <div class="photos-header__info">
            <h1 class="photos-title">{{ t('photos.trash.button') }}</h1>
          </div>
          <div class="photos-actions">
            <n-button
              v-if="auth.isAdmin && (trashPhotos.length > 0)"
              type="error"
              ghost
              @click="confirmEmptyTrash"
            >{{ t('photos.trash.emptyAll') }}</n-button>
            <n-button @click="closeTrash">{{ t('photos.trash.back') }}</n-button>
          </div>
        </header>
        <div v-if="loadingTrash" class="photo-grid">
          <div v-for="i in 12" :key="`tsk-${i}`" class="photo-skeleton" />
        </div>
        <div v-else-if="trashPhotos.length" class="photo-grid">
          <div v-for="p in trashPhotos" :key="p.id" class="photo-cell" draggable="false">
            <picture>
              <source :srcset="`${thumbUrl(p.id, 400)} 400w, ${thumbUrl(p.id, 600)} 600w`" sizes="(max-width: 400px) 400px, 600px" />
              <img :src="thumbUrl(p.id, 600)" :alt="p.original_name" loading="lazy" draggable="false" class="photo-cell__img" />
            </picture>
            <button class="photo-cell__restore" :title="t('photos.trash.restore')" @click.stop="doRestorePhoto(p)">↩</button>
            <button class="photo-cell__purge" :title="t('photos.trash.purge')" @click.stop="confirmPurgePhoto(p)">🗑</button>
          </div>
        </div>
        <p v-else class="photos-empty-state">{{ t('photos.trash.emptyTitle') }}</p>
        <template v-if="auth.isAdmin && trashFolders.length">
          <h3 class="trash-section-title">{{ t('photos.folders.title') }}</h3>
          <ul class="trash-folders-list">
            <li v-for="f in trashFolders" :key="f.id" class="trash-folder-row">
              <span>{{ f.name }}</span>
              <n-button size="tiny" @click="doRestoreFolder(f)">{{ t('photos.trash.restore') }}</n-button>
            </li>
          </ul>
        </template>
      </div>

      <!-- Normal mode -->
      <template v-else>
      <div v-if="!selectedFolder" class="photos-no-folder">
        <div class="photos-no-folder__icon">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none" aria-hidden="true">
            <rect x="6" y="20" width="52" height="36" rx="5" fill="var(--color-bg-muted)" stroke="var(--color-border)" stroke-width="1.5"/>
            <path d="M6 28h52" stroke="var(--color-border)" stroke-width="1.5"/>
            <path d="M6 28V24a5 5 0 015-5h16l4 4h21a5 5 0 015 5v1" stroke="var(--color-border)" stroke-width="1.5"/>
            <circle cx="32" cy="40" r="6" fill="var(--color-border)" opacity="0.4"/>
            <path d="M29 40l2 2 4-4" stroke="var(--color-brand-navy)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
          </svg>
        </div>
        <h3 class="photos-no-folder__title">{{ t('photos.emptyState.title') }}</h3>
        <p class="photos-no-folder__desc">{{ t('photos.emptyState.desc') }}</p>
      </div>

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
                <n-button size="small" @click="cancelEditDescription">{{ t('common.cancel') }}</n-button>
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
              @click="uploadAborted = true"
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
          @dragover.prevent="isDraggingOver = true"
          @dragleave="isDraggingOver = false"
          @drop.prevent="onDrop"
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
          <p v-else class="photos-empty-state">{{ t('photos.empty') }}</p>
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
    <div v-if="lightboxIdx !== null" class="lightbox" @click.self="closeLightbox" @wheel.prevent="onLightboxWheel">
      <button class="lightbox__close" :title="t('common.close')" @click="closeLightbox">✕</button>
      <button class="lightbox__nav lightbox__nav--prev" :title="t('common.prev')" @click="prevManual">‹</button>
      <div class="lightbox__stage" @click.self="closeLightbox">
        <picture v-if="currentLightboxPhoto">
          <source :srcset="`${thumbUrl(currentLightboxPhoto.id, 1000)} 1000w, ${thumbUrl(currentLightboxPhoto.id, 1600)} 1600w`" sizes="(max-width: 1000px) 1000px, 1600px" />
          <img
            :src="thumbUrl(currentLightboxPhoto.id, 1600)"
            :alt="currentLightboxPhoto.original_name"
            class="lightbox__img"
            :style="lightboxImgStyle"
            @click.stop
          />
        </picture>
      </div>
      <button class="lightbox__nav lightbox__nav--next" :title="t('common.next')" @click="nextManual">›</button>

      <div class="lightbox__toolbar" @click.stop>
        <button class="lb-btn" :title="t('photos.lightbox.zoomOut')" @click="zoomOut">−</button>
        <span class="lb-zoom">{{ Math.round(zoom * 100) }}%</span>
        <button class="lb-btn" :title="t('photos.lightbox.zoomIn')" @click="zoomIn">+</button>
        <button class="lb-btn" :title="t('photos.lightbox.rotate')" @click="rotateLeft">⟲</button>
        <button class="lb-btn" :title="t('photos.lightbox.rotateRight')" @click="rotateRight">⟳</button>
        <button class="lb-btn" :title="t('photos.lightbox.reset')" @click="resetView">⤾</button>
        <n-dropdown
          :options="slideshowOptions"
          @select="onSlideshowSelect"
          trigger="click"
        >
          <button
            class="lb-btn"
            :class="{ 'lb-btn--active': slideshowActive }"
            :title="slideshowActive ? t('photos.lightbox.slideshowStop') : t('photos.lightbox.slideshow')"
          >{{ slideshowActive ? '⏸' : '▶' }}</button>
        </n-dropdown>
        <a
          v-if="currentLightboxPhoto"
          class="lb-btn lb-btn--link"
          :href="originalUrl(currentLightboxPhoto.id, true)"
          :download="currentLightboxPhoto.original_name"
          :title="t('photos.lightbox.download')"
        >⬇</a>
        <button class="lb-btn" :title="t('photos.lightbox.copyLink')" @click="copyInPortalLink">🔗</button>
        <button
          v-if="canShareCurrent"
          class="lb-btn"
          :title="t('photos.lightbox.createShareLink')"
          :disabled="creatingShare"
          @click="openShareModal"
        >🌐</button>
        <button
          v-if="canManage && currentLightboxPhoto"
          class="lb-btn"
          :title="t('photos.myShares.shareFolder')"
          :disabled="creatingFolderShare"
          @click="openFolderShareModal"
        >📂</button>
      </div>

      <div v-if="currentLightboxPhoto" class="lightbox__info">
        <div class="lightbox__info-row">
          <span class="lightbox__breadcrumb" @click="closeLightbox">{{ selectedFolder?.name }}</span>
          <span v-if="selectedFolder"> / </span>
          <strong>{{ currentLightboxPhoto.original_name }}</strong>
          <span v-if="currentLightboxPhoto.taken_at"> · {{ new Date(currentLightboxPhoto.taken_at).toLocaleString() }}</span>
          <span v-if="currentLightboxPhoto.width">  · {{ currentLightboxPhoto.width }}×{{ currentLightboxPhoto.height }}</span>
        </div>
        <div class="lightbox__tags-row" @click.stop>
          <template v-if="!editingPhotoTags">
            <n-tag
              v-for="tag in currentPhotoTags"
              :key="tag.id"
              size="small"
              class="lightbox__tag"
            >{{ tag.name }}</n-tag>
            <button v-if="canUpload" class="lightbox__tags-edit-btn" @click="startEditTags">
              {{ currentPhotoTags.length ? '✎' : t('photos.tags.addTags') }}
            </button>
          </template>
          <template v-else>
            <n-select
              v-model:value="editingTagIds"
              multiple
              filterable
              :options="tagOptions"
              size="small"
              style="min-width: 200px; max-width: 400px"
              :placeholder="t('photos.tags.addTags')"
            />
            <n-button size="tiny" type="primary" :loading="savingTags" @click="savePhotoTags">{{ t('photos.tags.saveTags') }}</n-button>
            <n-button size="tiny" @click="editingPhotoTags = false">{{ t('common.cancel') }}</n-button>
          </template>
        </div>
      </div>
    </div>

    <!-- Share modal -->
    <n-modal
      v-model:show="shareModalOpen"
      preset="card"
      :title="t('photos.lightbox.createShareLink')"
      style="width:520px;max-width:94vw"
    >
      <n-form>
        <n-form-item :label="t('photos.lightbox.expiresIn')">
          <n-select
            v-model:value="shareExpiresInDays"
            :options="[
              { label: t('photos.lightbox.expires1d'), value: 1 },
              { label: t('photos.lightbox.expires7d'), value: 7 },
              { label: t('photos.lightbox.expires30d'), value: 30 },
              { label: t('photos.lightbox.expires90d'), value: 90 },
              { label: t('photos.lightbox.expiresNever'), value: null as unknown as number },
            ]"
          />
        </n-form-item>
        <div v-if="shareUrl" class="share-result">
          <n-input :value="shareUrl" readonly />
          <n-button size="small" @click="copyShareUrl">{{ t('common.copy') }}</n-button>
        </div>
        <div class="share-actions">
          <n-button @click="shareModalOpen = false">{{ t('common.close') }}</n-button>
          <n-button type="primary" :loading="creatingShare" @click="generateShareLink">
            {{ t('photos.lightbox.generate') }}
          </n-button>
        </div>
      </n-form>
    </n-modal>

    <!-- Folder share modal -->
    <n-modal
      v-model:show="folderShareModalOpen"
      preset="card"
      :title="t('photos.myShares.shareFolder')"
      style="width:520px;max-width:94vw"
    >
      <n-form>
        <n-form-item :label="t('photos.lightbox.expiresIn')">
          <n-select
            v-model:value="folderShareExpiresInDays"
            :options="[
              { label: t('photos.lightbox.expires1d'), value: 1 },
              { label: t('photos.lightbox.expires7d'), value: 7 },
              { label: t('photos.lightbox.expires30d'), value: 30 },
              { label: t('photos.lightbox.expires90d'), value: 90 },
              { label: t('photos.lightbox.expiresNever'), value: null as unknown as number },
            ]"
          />
        </n-form-item>
        <div v-if="folderShareUrl" class="share-result">
          <n-input :value="folderShareUrl" readonly />
          <n-button size="small" @click="copyFolderShareUrl">{{ t('common.copy') }}</n-button>
        </div>
        <div class="share-actions">
          <n-button @click="folderShareModalOpen = false">{{ t('common.close') }}</n-button>
          <n-button type="primary" :loading="creatingFolderShare" @click="generateFolderShareLink">
            {{ t('photos.lightbox.generate') }}
          </n-button>
        </div>
      </n-form>
    </n-modal>

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

    <!-- Permissions modal -->
    <n-modal
      v-model:show="permsModalOpen"
      preset="card"
      :title="t('photos.permissions.title')"
      style="width:540px;max-width:94vw"
      :mask-closable="true"
    >
      <div v-if="permsTarget">
        <p class="perms-target"><strong>{{ permsTarget.name }}</strong></p>
        <ul v-if="permsList.length" class="perms-list">
          <li v-for="p in permsList" :key="p.id" class="perms-row">
            <span>{{ p.subject_name }} <em>({{ t(`photos.permissions.perm_${p.permission}`) }})</em></span>
            <n-button size="tiny" type="error" ghost @click="revoke(p)">{{ t('common.delete') }}</n-button>
          </li>
        </ul>
        <p v-else class="perms-empty">{{ t('photos.permissions.empty') }}</p>

        <div class="perms-add">
          <h4>{{ t('photos.permissions.add') }}</h4>
          <n-form>
            <n-form-item :label="t('photos.permissions.subjectType')">
              <n-select
                v-model:value="newPerm.subject_type"
                :options="[
                  { label: t('photos.permissions.subjectUser'), value: 'user' },
                  { label: t('photos.permissions.subjectGroup'), value: 'group' },
                ]"
              />
            </n-form-item>
            <n-form-item :label="t('photos.permissions.subjectId')">
              <n-input v-model:value="newPerm.subject_id" placeholder="keycloak-id или group-id" />
            </n-form-item>
            <n-form-item :label="t('photos.permissions.subjectName')">
              <n-input v-model:value="newPerm.subject_name" />
            </n-form-item>
            <n-form-item :label="t('photos.permissions.level')">
              <n-select
                v-model:value="newPerm.permission"
                :options="[
                  { label: t('photos.permissions.perm_viewer'), value: 'viewer' },
                  { label: t('photos.permissions.perm_uploader'), value: 'uploader' },
                  { label: t('photos.permissions.perm_manager'), value: 'manager' },
                ]"
              />
            </n-form-item>
            <n-button type="primary" :loading="permsAdding" @click="addPerm">
              {{ t('photos.permissions.add') }}
            </n-button>
          </n-form>
        </div>
      </div>
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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NButton, NModal, NForm, NFormItem, NInput, NSelect, NDropdown, NTag, useMessage, useDialog,
} from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import {
  fetchFolderTree, fetchFolder, fetchFolderPhotos, createFolder, deleteFolder,
  updateFolder, uploadPhotos, getPhoto, deletePhoto, fetchPermissions, grantPermission, revokePermission,
  thumbUrl, originalUrl, createShareLink,
  fetchDeletedPhotos, restorePhoto, purgePhoto, emptyTrash, fetchDeletedFolders, restoreFolder,
  bulkAction, startFolderZip, getZipJob, zipJobDownloadUrl, importScan,
  fetchFolderPhotosFiltered, moveFolder,
  fetchTags, fetchPhotoTags, setPhotoTags, createFolderShareLink,
  type Photo, type PhotoFolder, type PhotoFolderTreeNode, type PhotoPermission,
  type ZipJob, type FolderPhotosParams, type PhotoTag,
} from '@/api/photos'
import FolderNode from '@/components/photos/FolderNode.vue'

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

const fileInputRef = ref<HTMLInputElement | null>(null)

interface UploadQueueItem {
  file: File
  status: 'pending' | 'uploading' | 'done' | 'error'
  error?: string
}
const uploadQueue = ref<UploadQueueItem[]>([])
const uploadAborted = ref(false)
const uploadingActive = computed(() =>
  uploadQueue.value.length > 0 &&
  uploadQueue.value.some(i => i.status === 'pending' || i.status === 'uploading')
)
const uploadDoneCount = computed(() => uploadQueue.value.filter(i => i.status === 'done').length)

const sortBy = ref<'created_at' | 'taken_at' | 'original_name'>('created_at')

const isDraggingOver = ref(false)

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
const permsList = ref<PhotoPermission[]>([])
const permsAdding = ref(false)
const newPerm = ref<{ subject_type: 'user' | 'group'; subject_id: string; subject_name: string; permission: 'viewer' | 'uploader' | 'manager' }>({
  subject_type: 'user', subject_id: '', subject_name: '', permission: 'viewer',
})

const trashMode = ref(false)
const trashPhotos = ref<Photo[]>([])
const trashTotal = ref(0)
const trashFolders = ref<PhotoFolder[]>([])
const loadingTrash = ref(false)

const zipJob = ref<ZipJob | null>(null)
const zipPolling = ref<ReturnType<typeof setInterval> | null>(null)

const moveModalOpen = ref(false)
const moveTargetFolderId = ref<string | null>(null)

const tags = ref<PhotoTag[]>([])
const photoTagsMap = ref<Record<string, PhotoTag[]>>({})
const activeTagFilter = ref<string | null>(null)
const editingPhotoTags = ref(false)
const editingTagIds = ref<string[]>([])
const savingTags = ref(false)

const draggingFolderNode = ref<PhotoFolderTreeNode | null>(null)

const folderShareModalOpen = ref(false)
const folderShareExpiresInDays = ref<number | null>(7)
const folderShareUrl = ref('')
const creatingFolderShare = ref(false)

const lightboxIdx = ref<number | null>(null)
const currentLightboxPhoto = computed(() => lightboxIdx.value !== null ? photos.value[lightboxIdx.value] : null)

const zoom = ref(1)
const rotation = ref(0)
const lightboxImgStyle = computed(() => ({
  transform: `rotate(${rotation.value}deg) scale(${zoom.value})`,
  transition: 'transform 0.15s ease-out',
}))

const slideshowActive = ref(false)
const slideshowInterval = ref<ReturnType<typeof setInterval> | null>(null)
const slideshowDelay = ref(5000)

const slideshowOptions = computed(() => {
  const opts: { label: string; key: string }[] = [
    { label: t('photos.lightbox.slideshow5s'), key: '5000' },
    { label: t('photos.lightbox.slideshow10s'), key: '10000' },
    { label: t('photos.lightbox.slideshow30s'), key: '30000' },
  ]
  if (slideshowActive.value) {
    opts.unshift({ label: t('photos.lightbox.slideshowStop'), key: 'stop' })
  }
  return opts
})

const shareModalOpen = ref(false)
const shareExpiresInDays = ref<number | null>(7)
const shareUrl = ref('')
const creatingShare = ref(false)
const sharePhotoId = ref<string | null>(null)
const _canUploadOrShare = computed(() => {
  const p = selectedFolder.value?.permission
  return p === 'uploader' || p === 'manager' || auth.isAdmin
})
const canShareCurrent = _canUploadOrShare
const canUpload = _canUploadOrShare
const canManage = computed(() => {
  const p = selectedFolder.value?.permission
  return p === 'manager' || auth.isAdmin
})
function canDelete(p: Photo): boolean {
  return canManage.value || (auth.user?.id === p.uploaded_by)
}

const hasActiveFilters = computed(() => !!activeTagFilter.value)

const currentPhotoTags = computed(() =>
  currentLightboxPhoto.value ? (photoTagsMap.value[currentLightboxPhoto.value.id] ?? []) : []
)

const tagOptions = computed(() =>
  tags.value.map(t => ({ label: t.name, value: t.id }))
)

const flatFolderOptions = computed(() =>
  flatten(tree.value).map(n => ({ label: n.name, value: n.id }))
)

function handleKeydown(e: KeyboardEvent) {
  if (lightboxIdx.value === null) return
  if (e.key === 'Escape') {
    closeLightbox()
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault()
    prevManual()
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    nextManual()
  } else if (e.key === 'Home') {
    e.preventDefault()
    lightboxIdx.value = 0
    resetView()
  } else if (e.key === 'End') {
    e.preventDefault()
    lightboxIdx.value = photos.value.length - 1
    resetView()
  } else if (e.key === ' ') {
    e.preventDefault()
    if (zoom.value < 1.5) zoomIn(); else resetView()
  }
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

function triggerUpload() { fileInputRef.value?.click() }

async function runUploadQueue(files: File[]) {
  if (!selectedFolderId.value) return
  uploadAborted.value = false
  uploadQueue.value = files.map(f => ({ file: f, status: 'pending' as const }))
  const batchSize = 5
  for (let i = 0; i < files.length; i += batchSize) {
    if (uploadAborted.value) break
    const end = Math.min(i + batchSize, files.length)
    for (let j = i; j < end; j++) {
      uploadQueue.value[j].status = 'uploading'
    }
    try {
      await uploadPhotos(selectedFolderId.value, files.slice(i, end))
      for (let j = i; j < end; j++) {
        uploadQueue.value[j].status = 'done'
      }
    } catch {
      for (let j = i; j < end; j++) {
        uploadQueue.value[j].status = 'error'
        uploadQueue.value[j].error = t('photos.upload.error')
      }
    }
  }

  if (uploadAborted.value) {
    for (let j = 0; j < uploadQueue.value.length; j++) {
      if (uploadQueue.value[j].status === 'pending') {
        uploadQueue.value[j].status = 'error'
        uploadQueue.value[j].error = t('photos.upload.aborted')
      }
    }
    message.warning(t('photos.upload.aborted'))
  } else {
    const doneCount = uploadQueue.value.filter(i => i.status === 'done').length
    if (doneCount > 0) message.success(t('photos.upload.done', { n: doneCount }))
  }
  page.value = 1
  await loadPhotos()
}

async function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files || !input.files.length || !selectedFolderId.value) return
  const files = Array.from(input.files)
  if (input) input.value = ''
  await runUploadQueue(files)
}

function onDrop(e: DragEvent) {
  isDraggingOver.value = false
  if (!canUpload.value || !e.dataTransfer?.files.length || !selectedFolderId.value) return
  if (!Array.from(e.dataTransfer.types).includes('Files')) return
  const files = Array.from(e.dataTransfer.files).filter(
    f => f.type.startsWith('image/') || /\.(heic|heif)$/i.test(f.name)
  )
  if (!files.length) return
  runUploadQueue(files)
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

async function openPermissions(node: PhotoFolder | PhotoFolderTreeNode) {
  permsTarget.value = node
  try {
    const r = await fetchPermissions(node.id)
    permsList.value = r.items
  } catch {
    permsList.value = []
  }
  permsModalOpen.value = true
}

async function addPerm() {
  if (!permsTarget.value) return
  if (!newPerm.value.subject_id.trim() || !newPerm.value.subject_name.trim()) {
    message.warning(t('photos.permissions.fieldsRequired'))
    return
  }
  permsAdding.value = true
  try {
    const created = await grantPermission(permsTarget.value.id, { ...newPerm.value })
    permsList.value = [...permsList.value.filter(p => p.subject_id !== created.subject_id), created]
    newPerm.value.subject_id = ''
    newPerm.value.subject_name = ''
    message.success(t('photos.permissions.granted'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    permsAdding.value = false
  }
}

async function revoke(p: PhotoPermission) {
  if (!permsTarget.value) return
  try {
    await revokePermission(permsTarget.value.id, p.subject_id)
    permsList.value = permsList.value.filter(x => x.id !== p.id)
    message.success(t('photos.permissions.revoked'))
  } catch {
    message.error(t('errors.generic'))
  }
}

function resetView() { zoom.value = 1; rotation.value = 0 }
function openLightbox(idx: number) { lightboxIdx.value = idx; resetView() }
function closeLightbox() { stopSlideshow(); lightboxIdx.value = null; resetView() }
function prev() {
  if (lightboxIdx.value === null) return
  lightboxIdx.value = (lightboxIdx.value - 1 + photos.value.length) % photos.value.length
  resetView()
}
function next() {
  if (lightboxIdx.value === null) return
  lightboxIdx.value = (lightboxIdx.value + 1) % photos.value.length
  resetView()
}
function prevManual() { stopSlideshow(); prev() }
function nextManual() { stopSlideshow(); next() }
function zoomIn() { zoom.value = Math.min(8, +(zoom.value + 0.25).toFixed(2)) }
function zoomOut() { zoom.value = Math.max(0.25, +(zoom.value - 0.25).toFixed(2)) }
function rotateLeft() { rotation.value = (rotation.value - 90) % 360 }
function rotateRight() { rotation.value = (rotation.value + 90) % 360 }
function onLightboxWheel(e: WheelEvent) {
  if (e.deltaY < 0) zoomIn(); else zoomOut()
}

function startSlideshow(delay: number) {
  stopSlideshow()
  slideshowDelay.value = delay
  slideshowActive.value = true
  slideshowInterval.value = setInterval(() => next(), delay)
}

function stopSlideshow() {
  if (slideshowInterval.value !== null) {
    clearInterval(slideshowInterval.value)
    slideshowInterval.value = null
  }
  slideshowActive.value = false
}

function onSlideshowSelect(key: string) {
  if (key === 'stop') {
    stopSlideshow()
  } else {
    startSlideshow(Number(key))
  }
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
  if (selectMode.value) {
    togglePhotoSelect(p.id)
  } else {
    openLightbox(idx)
  }
}

function startEditDescription() {
  editDescValue.value = selectedFolder.value?.description ?? ''
  editingDescription.value = true
}

function cancelEditDescription() {
  editingDescription.value = false
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

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.focus(); ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch { return false }
}

async function copyInPortalLink() {
  const p = currentLightboxPhoto.value
  if (!p) return
  const folderQ = selectedFolderId.value ? `folder=${selectedFolderId.value}&` : ''
  const url = `${window.location.origin}/photos?${folderQ}photo=${p.id}`
  const ok = await copyToClipboard(url)
  ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
}

function openShareModal() {
  sharePhotoId.value = currentLightboxPhoto.value?.id ?? null
  shareUrl.value = ''
  shareExpiresInDays.value = 7
  shareModalOpen.value = true
}

async function generateShareLink() {
  const photoId = sharePhotoId.value
  if (!photoId) return
  creatingShare.value = true
  try {
    const link = await createShareLink(photoId, shareExpiresInDays.value)
    shareUrl.value = `${window.location.origin}/p/${link.token}`
    message.success(t('photos.lightbox.shareLinkCreated'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    creatingShare.value = false
  }
}

async function copyShareUrl() {
  if (!shareUrl.value) return
  const ok = await copyToClipboard(shareUrl.value)
  ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
}

async function loadTags() {
  try {
    const data = await fetchTags()
    tags.value = data.items
  } catch {
    // ignore
  }
}

async function loadPhotoTags(photoId: string) {
  if (photoTagsMap.value[photoId]) return
  try {
    const data = await fetchPhotoTags(photoId)
    photoTagsMap.value = { ...photoTagsMap.value, [photoId]: data }
  } catch {
    // ignore
  }
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

function startEditTags() {
  editingTagIds.value = currentPhotoTags.value.map(t => t.id)
  editingPhotoTags.value = true
}

async function savePhotoTags() {
  const photo = currentLightboxPhoto.value
  if (!photo) return
  savingTags.value = true
  try {
    const updated = await setPhotoTags(photo.id, editingTagIds.value)
    photoTagsMap.value = { ...photoTagsMap.value, [photo.id]: updated }
    editingPhotoTags.value = false
    message.success(t('photos.tags.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    savingTags.value = false
  }
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

function openFolderShareModal() {
  folderShareUrl.value = ''
  folderShareExpiresInDays.value = 7
  folderShareModalOpen.value = true
}

async function generateFolderShareLink() {
  if (!selectedFolderId.value) return
  creatingFolderShare.value = true
  try {
    const link = await createFolderShareLink(selectedFolderId.value, folderShareExpiresInDays.value)
    folderShareUrl.value = `${window.location.origin}/photos/public/${link.token}`
    message.success(t('photos.lightbox.shareLinkCreated'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    creatingFolderShare.value = false
  }
}

async function copyFolderShareUrl() {
  if (!folderShareUrl.value) return
  const ok = await copyToClipboard(folderShareUrl.value)
  ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
}

watch(lightboxIdx, (idx) => {
  editingPhotoTags.value = false
  editingTagIds.value = []
  if (idx !== null && currentLightboxPhoto.value) {
    loadPhotoTags(currentLightboxPhoto.value.id)
  }
})

onMounted(async () => {
  window.addEventListener('keydown', handleKeydown)
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
      openLightbox(idx)
    } else {
      try {
        const photo = await getPhoto(photoId)
        photos.value.unshift(photo)
        openLightbox(0)
      } catch {
        // photo not accessible or not found — silently ignore
      }
    }
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  stopSlideshow()
  stopZipPolling()
})

async function loadTrashCount() {
  try {
    const res = await fetchDeletedPhotos({ page: 1, per_page: 1 })
    trashTotal.value = res.total
  } catch {
    // ignore
  }
}

async function openTrash() {
  trashMode.value = true
  loadingTrash.value = true
  try {
    const photosRes = await fetchDeletedPhotos({ page: 1, per_page: 50 })
    trashPhotos.value = photosRes.items
    trashTotal.value = photosRes.total
    if (auth.isAdmin) {
      try {
        trashFolders.value = await fetchDeletedFolders()
      } catch {
        trashFolders.value = []
      }
    }
  } catch {
    message.error(t('errors.generic'))
  } finally {
    loadingTrash.value = false
  }
}

function closeTrash() {
  trashMode.value = false
}

async function doRestorePhoto(p: Photo) {
  try {
    await restorePhoto(p.id)
    trashPhotos.value = trashPhotos.value.filter(x => x.id !== p.id)
    trashTotal.value = Math.max(0, trashTotal.value - 1)
    message.success(t('photos.trash.restoreDone'))
  } catch {
    message.error(t('errors.generic'))
  }
}

async function doRestoreFolder(f: PhotoFolder) {
  try {
    await restoreFolder(f.id)
    trashFolders.value = trashFolders.value.filter(x => x.id !== f.id)
    message.success(t('photos.trash.restoreDone'))
    await loadTree()
  } catch {
    message.error(t('errors.generic'))
  }
}

function confirmPurgePhoto(p: Photo) {
  dialog.warning({
    title: t('photos.trash.purgeTitle'),
    content: t('photos.trash.purgeConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await purgePhoto(p.id)
        trashPhotos.value = trashPhotos.value.filter(x => x.id !== p.id)
        trashTotal.value = Math.max(0, trashTotal.value - 1)
        message.success(t('photos.trash.purgeDone'))
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

function confirmEmptyTrash() {
  dialog.warning({
    title: t('photos.trash.emptyAll'),
    content: t('photos.trash.emptyAllConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        const res = await emptyTrash()
        trashPhotos.value = []
        trashTotal.value = 0
        message.success(t('photos.trash.emptyAllDone', { n: res.purged }))
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

function stopZipPolling() {
  if (zipPolling.value !== null) {
    clearInterval(zipPolling.value)
    zipPolling.value = null
  }
}

async function startZip() {
  if (!selectedFolderId.value) return
  stopZipPolling()
  zipJob.value = null
  try {
    const job = await startFolderZip(selectedFolderId.value)
    zipJob.value = job
    if (job.status === 'done') {
      window.open(zipJobDownloadUrl(job.id), '_blank')
      message.success(t('photos.zip.ready'))
      return
    }
    if (job.status === 'error') {
      message.error(t('photos.zip.error'))
      return
    }
    let pollAttempts = 0
    const ZIP_POLL_LIMIT = 60
    zipPolling.value = setInterval(async () => {
      pollAttempts++
      if (pollAttempts > ZIP_POLL_LIMIT) {
        stopZipPolling()
        zipJob.value = null
        message.error(t('photos.zip.timeout'))
        return
      }
      try {
        const updated = await getZipJob(zipJob.value!.id)
        zipJob.value = updated
        if (updated.status === 'done') {
          stopZipPolling()
          window.open(zipJobDownloadUrl(updated.id), '_blank')
          message.success(t('photos.zip.ready'))
        } else if (updated.status === 'error') {
          stopZipPolling()
          message.error(t('photos.zip.error'))
        }
      } catch {
        stopZipPolling()
        message.error(t('errors.generic'))
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

function confirmImportScan() {
  dialog.warning({
    title: t('photos.import.button'),
    content: t('photos.import.confirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        const r = await importScan()
        message.success(t('photos.import.done', { photos: r.photos_imported, folders: r.folders_created, skipped: r.skipped }))
        await loadTree()
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
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
.photos-empty-state {
  text-align: center; color: var(--color-text-muted); padding: 60px 20px;
}

.photos-no-folder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 12px;
  padding: 60px 24px 40px;
  text-align: center;
}

.photos-no-folder__icon {
  opacity: 0.7;
  margin-bottom: 4px;
}

.photos-no-folder__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
}

.photos-no-folder__desc {
  font-size: 13px;
  color: var(--color-text-muted);
  margin: 0;
  max-width: 320px;
}

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
.photo-cell__check input[type="checkbox"] {
  width: 16px; height: 16px; cursor: pointer;
}

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

.lightbox {
  position: fixed; inset: 0; background: rgba(0,0,0,0.92); z-index: 1500;
  display: flex; align-items: center; justify-content: center;
}
.lightbox__stage {
  width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.lightbox__img { max-width: 95vw; max-height: 90vh; object-fit: contain; user-select: none; -webkit-user-drag: none; }
.lightbox__close, .lightbox__nav {
  position: absolute; background: rgba(255,255,255,0.1); color: #fff;
  border: 0; cursor: pointer; font-size: 24px;
  width: 44px; height: 44px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; z-index: 2;
}
.lightbox__close { top: 16px; right: 16px; }
.lightbox__nav--prev { left: 16px; top: 50%; transform: translateY(-50%); }
.lightbox__nav--next { right: 16px; top: 50%; transform: translateY(-50%); }
.lightbox__toolbar {
  position: absolute; top: 16px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 6px;
  background: rgba(0,0,0,0.55); padding: 6px 10px; border-radius: 999px;
  z-index: 3;
}
.lb-btn {
  background: rgba(255,255,255,0.12); color: #fff; border: 0; cursor: pointer;
  width: 36px; height: 36px; border-radius: 50%; font-size: 16px;
  display: inline-flex; align-items: center; justify-content: center;
  text-decoration: none;
}
.lb-btn[disabled] { opacity: 0.5; cursor: not-allowed; }
.lb-btn:hover { background: rgba(255,255,255,0.22); }
.lb-btn--active { background: rgba(59,130,246,0.5); }
.lb-btn--active:hover { background: rgba(59,130,246,0.7); }
.lb-zoom { color: #fff; font-size: 12px; min-width: 44px; text-align: center; }
.lightbox__info {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,0.7); color: #fff; padding: 12px 20px;
  font-size: 13px; z-index: 2;
}
.lightbox__breadcrumb {
  cursor: pointer; opacity: 0.7;
}
.lightbox__breadcrumb:hover { opacity: 1; text-decoration: underline; }

.share-result { display: flex; gap: 8px; align-items: center; margin: 12px 0; }
.share-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }

.perms-target { margin-bottom: 12px; }
.perms-list { list-style: none; margin: 0 0 16px; padding: 0; }
.perms-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid var(--color-border);
}
.perms-empty { color: var(--color-text-muted); font-size: 13px; margin: 0 0 16px; }
.perms-add h4 { margin: 16px 0 8px; }

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
.photos-side__import {
  margin-top: 8px;
}

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

.lightbox__info-row { margin-bottom: 4px; }
.lightbox__tags-row {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 4px;
}
.lightbox__tag { margin: 0; }
.lightbox__tags-edit-btn {
  background: transparent; border: 0; cursor: pointer; font-size: 12px;
  color: rgba(255,255,255,0.6); padding: 0;
}
.lightbox__tags-edit-btn:hover { color: #fff; }

.zip-status {
  font-size: 13px; color: var(--color-text-muted);
  padding: 6px 0; margin-bottom: 8px;
}

.photo-cell__restore {
  position: absolute; top: 4px; right: 4px;
  background: rgba(0,0,0,0.6); color: #fff; border: 0; cursor: pointer;
  width: 28px; height: 28px; border-radius: 50%; font-size: 16px; line-height: 1;
  display: none; align-items: center; justify-content: center;
}
.photo-cell:hover .photo-cell__restore { display: inline-flex; }
.photo-cell__purge {
  position: absolute; top: 4px; right: 36px;
  background: rgba(180,30,30,0.75); color: #fff; border: 0; cursor: pointer;
  width: 28px; height: 28px; border-radius: 50%; font-size: 14px; line-height: 1;
  display: none; align-items: center; justify-content: center;
}
.photo-cell:hover .photo-cell__purge { display: inline-flex; }

.trash-section-title { margin: 16px 0 8px; font-size: 14px; font-weight: 600; }
.trash-folders-list { list-style: none; margin: 0; padding: 0; }
.trash-folder-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid var(--color-border); font-size: 13px;
}
.trash-folder-row:last-child { border-bottom: 0; }

@media (max-width: 900px) {
  .photos-page { grid-template-columns: 1fr; }
  .photos-side { position: static; }
}
</style>
