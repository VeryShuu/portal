<template>
  <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
  <div
    v-if="modelValue !== null"
    class="lightbox"
    role="dialog"
    aria-modal="true"
    :aria-label="t('photos.title')"
    @click.self="close"
    @keydown.escape="close"
    @wheel.prevent="onLightboxWheel"
  >
    <button
      class="lightbox__close"
      :title="t('common.close')"
      @click="close"
    >
      ✕
    </button>
    <button
      class="lightbox__nav lightbox__nav--prev"
      :title="t('common.prev')"
      @click="prevManual"
    >
      ‹
    </button>

    <PhotoLightboxViewer
      :current-photo="currentPhoto"
      :img-style="imgStyle"
      @close="close"
    />

    <button
      class="lightbox__nav lightbox__nav--next"
      :title="t('common.next')"
      @click="nextManual"
    >
      ›
    </button>

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
  </div>

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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Photo, PhotoFolder, PhotoTag } from '@/api/photos'
import { useLightboxView } from '@/composables/useLightboxView'
import { useLightboxSlideshow } from '@/composables/useLightboxSlideshow'
import { useLightboxShare } from '@/composables/useLightboxShare'
import { useLightboxPhotoTags } from '@/composables/useLightboxPhotoTags'

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

const previouslyFocusedElement = ref<HTMLElement | null>(null)

watch(() => props.modelValue, (newVal) => {
  if (newVal !== null) {
    previouslyFocusedElement.value = document.activeElement as HTMLElement | null
    setTimeout(() => {
      const closeBtn = document.querySelector('.lightbox__close') as HTMLElement | null
      if (closeBtn) {
        closeBtn.focus()
      }
    }, 50)
  } else {
    if (previouslyFocusedElement.value && typeof previouslyFocusedElement.value.focus === 'function') {
      previouslyFocusedElement.value.focus()
    }
    previouslyFocusedElement.value = null
  }
})

const currentPhoto = computed(() =>
  props.modelValue !== null ? props.photos[props.modelValue] : null,
)

const { zoom, imgStyle, resetView, zoomIn, zoomOut, rotateLeft, rotateRight, onLightboxWheel } = useLightboxView()

function close() { stopSlideshow(); emit('update:modelValue', null); resetView() }
function prev() {
  if (props.modelValue === null) return
  emit('update:modelValue', (props.modelValue - 1 + props.photos.length) % props.photos.length)
  resetView()
}
function next() {
  if (props.modelValue === null) return
  emit('update:modelValue', (props.modelValue + 1) % props.photos.length)
  resetView()
}
function prevManual() { stopSlideshow(); prev() }
function nextManual() { stopSlideshow(); next() }

const {
  slideshowActive, slideshowOptions,
  stopSlideshow, onSlideshowSelect, onVisibilityChange,
} = useLightboxSlideshow(() => next())

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

function handleTab(e: KeyboardEvent) {
  if (props.modelValue === null) return
  if (shareModalOpen.value || folderShareModalOpen.value) return

  const lightboxEl = document.querySelector('.lightbox')
  if (!lightboxEl) return

  const focusableSelectors = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  const focusable = Array.from(lightboxEl.querySelectorAll(focusableSelectors)) as HTMLElement[]
  if (focusable.length === 0) return

  const first = focusable[0]
  const last = focusable[focusable.length - 1]

  if (e.shiftKey) {
    if (document.activeElement === first) {
      last.focus()
      e.preventDefault()
    }
  } else {
    if (document.activeElement === last) {
      first.focus()
      e.preventDefault()
    }
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (props.modelValue === null) return
  if (e.key === 'Tab') {
    handleTab(e)
    return
  }
  const target = e.target as HTMLElement | null
  if (target) {
    const tag = target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) {
      return
    }
  }
  if (e.key === 'Escape') { close() }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); prevManual() }
  else if (e.key === 'ArrowRight') { e.preventDefault(); nextManual() }
  else if (e.key === 'Home') { e.preventDefault(); emit('update:modelValue', 0); resetView() }
  else if (e.key === 'End') { e.preventDefault(); emit('update:modelValue', props.photos.length - 1); resetView() }
  else if (e.key === ' ') { e.preventDefault(); if (zoom.value < 1.5) zoomIn(); else resetView() }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  stopSlideshow()
})
</script>

<style scoped>
.lightbox {
  position: fixed; inset: 0; background: rgba(0,0,0,0.92); z-index: 1500;
  display: flex; align-items: center; justify-content: center;
}
.lightbox__close, .lightbox__nav {
  position: absolute; background: rgba(255,255,255,0.1); color: #fff;
  border: 0; cursor: pointer; font-size: 24px;
  width: 44px; height: 44px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; z-index: 2;
}
.lightbox__close { top: 16px; right: 16px; }
.lightbox__nav--prev { left: 16px; top: 50%; transform: translateY(-50%); }
.lightbox__nav--next { right: 16px; top: 50%; transform: translateY(-50%); }
.lightbox__info {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,0.7); color: #fff; padding: 12px 20px;
  font-size: 13px; z-index: 2;
}
.lightbox__breadcrumb { cursor: pointer; opacity: 0.7; }
.lightbox__breadcrumb:hover { opacity: 1; text-decoration: underline; }
.lightbox__info-row { margin-bottom: 4px; }
</style>
