<template>
  <LightboxBase
    :model-value="modelValue"
    :total="photos.length"
    :aria-label="t('photos.title')"
    @update:model-value="onUpdate"
    @close="onClose"
    @prev="resetView"
    @next="resetView"
    @wheel="onLightboxWheel"
    @keydown="onExtraKey"
  >
    <PhotoLightboxViewer
      :current-photo="currentPhoto"
      :img-style="imgStyle"
      @close="close"
    />

    <template #toolbar>
      <LightboxToolbar
        :zoom="zoom"
        :slideshow-active="slideshowActive"
        :slideshow-options="slideshowOptions"
        :current-photo="currentPhoto"
        :can-upload="canUpload"
        :can-manage="canManage"
        :creating-share="creatingShare"
        :creating-folder-share="creatingFolderShare"
        @zoom-out="zoomOut"
        @zoom-in="zoomIn"
        @rotate-left="rotateLeft"
        @rotate-right="rotateRight"
        @reset-view="resetView"
        @select-slideshow="onSlideshowSelect"
        @copy-link="copyInPortalLink"
        @open-share-modal="openShareModal"
        @open-folder-share-modal="openFolderShareModal"
      />
    </template>

    <template #info>
      <div
        v-if="currentPhoto"
        class="lightbox__info"
      >
        <div class="lightbox__info-row">
          <span
            class="lightbox__breadcrumb"
            role="button"
            tabindex="0"
            @click="close"
            @keydown.enter="close"
          >{{ selectedFolder?.name }}</span>
          <span v-if="selectedFolder"> / </span>
          <strong>{{ currentPhoto.original_name }}</strong>
          <span v-if="currentPhoto.taken_at"> · {{ new Date(currentPhoto.taken_at).toLocaleString() }}</span>
          <span v-if="currentPhoto.width"> · {{ currentPhoto.width }}×{{ currentPhoto.height }}</span>
        </div>
        <LightboxTagsEditor
          v-model:editing="editingPhotoTags"
          v-model:editing-tag-ids="editingTagIds"
          :current-photo-tags="currentPhotoTags"
          :can-upload="canUpload"
          :tag-options="tagOptions"
          :saving="savingTags"
          @start-edit="startEditTags"
          @save="savePhotoTags"
        />
      </div>
    </template>
  </LightboxBase>

  <SharePhotoModal
    v-model:show="shareModalOpen"
    v-model:expires-in-days="shareExpiresInDays"
    :share-url="shareUrl"
    :creating="creatingShare"
    :expiry-options="expiryOptions"
    @generate="generateShareLink"
    @copy="copyShareUrl"
  />

  <ShareFolderModal
    v-model:show="folderShareModalOpen"
    v-model:expires-in-days="folderShareExpiresInDays"
    :share-url="folderShareUrl"
    :creating="creatingFolderShare"
    :expiry-options="expiryOptions"
    @generate="generateFolderShareLink"
    @copy="copyFolderShareUrl"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Photo, PhotoFolder, PhotoTag } from '@/api/photos'
import { useLightboxView } from '@/composables/useLightboxView'
import { useLightboxSlideshow } from '@/composables/useLightboxSlideshow'
import { useLightboxShare } from '@/composables/useLightboxShare'
import { useLightboxPhotoTags } from '@/composables/useLightboxPhotoTags'

import LightboxBase from './LightboxBase.vue'
import PhotoLightboxViewer from './PhotoLightboxViewer.vue'
import LightboxToolbar from './LightboxToolbar.vue'
import SharePhotoModal from './SharePhotoModal.vue'
import ShareFolderModal from './ShareFolderModal.vue'
import LightboxTagsEditor from './LightboxTagsEditor.vue'

const props = defineProps<{
  modelValue: number | null
  photos: Photo[]
  selectedFolder: PhotoFolder | null
  selectedFolderId: string | null
  canUpload: boolean
  canManage: boolean
  tags: PhotoTag[]
  photoTagsMap: Record<string, PhotoTag[]>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', idx: number | null): void
  (e: 'tags-updated', photoId: string, tags: PhotoTag[]): void
}>()

const { t } = useI18n()

const currentPhoto = computed(() =>
  props.modelValue !== null ? props.photos[props.modelValue] : null,
)

const { zoom, imgStyle, resetView, zoomIn, zoomOut, rotateLeft, rotateRight, onLightboxWheel } = useLightboxView()

function onUpdate(idx: number | null) {
  emit('update:modelValue', idx)
}

function close() { stopSlideshow(); emit('update:modelValue', null); resetView() }
function onClose() { stopSlideshow(); resetView() }

const {
  slideshowActive, slideshowOptions,
  stopSlideshow, onSlideshowSelect, onVisibilityChange,
} = useLightboxSlideshow(() => {
  if (props.modelValue === null) return
  emit('update:modelValue', (props.modelValue + 1) % props.photos.length)
  resetView()
})

const {
  shareModalOpen, shareExpiresInDays, shareUrl, creatingShare,
  folderShareModalOpen, folderShareExpiresInDays, folderShareUrl, creatingFolderShare,
  expiryOptions,
  openShareModal, generateShareLink, copyShareUrl,
  openFolderShareModal, generateFolderShareLink, copyFolderShareUrl,
  copyInPortalLink,
} = useLightboxShare({
  currentPhoto: () => currentPhoto.value,
  selectedFolderId: () => props.selectedFolderId,
})

const {
  editingPhotoTags, editingTagIds, savingTags,
  currentPhotoTags, tagOptions,
  startEditTags, savePhotoTags,
} = useLightboxPhotoTags({
  currentPhoto: () => currentPhoto.value,
  photoTagsMap: () => props.photoTagsMap,
  allTags: () => props.tags,
  onTagsUpdated: (photoId, tags) => emit('tags-updated', photoId, tags),
  photoIndex: () => props.modelValue,
  photos: () => props.photos,
})

function onExtraKey(e: KeyboardEvent) {
  if (props.modelValue === null) return
  if (shareModalOpen.value || folderShareModalOpen.value) return
  if (e.key === 'Home') {
    e.preventDefault(); emit('update:modelValue', 0); resetView()
  } else if (e.key === 'End') {
    e.preventDefault(); emit('update:modelValue', props.photos.length - 1); resetView()
  } else if (e.key === ' ') {
    e.preventDefault(); if (zoom.value < 1.5) zoomIn(); else resetView()
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  stopSlideshow()
})
</script>

<style scoped>
.lightbox__info {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,0.7); color: #fff; padding: 12px 20px;
  font-size: 13px; z-index: 2;
}
.lightbox__breadcrumb { cursor: pointer; opacity: 0.7; }
.lightbox__breadcrumb:hover { opacity: 1; text-decoration: underline; }
.lightbox__info-row { margin-bottom: 4px; }
</style>
