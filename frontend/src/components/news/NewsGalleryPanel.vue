<template>
  <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
  <div
    class="u-panel gallery-panel"
    :class="{ 'u-panel--dropping': galleryDropping && !!newsId }"
    role="region"
    :aria-label="t('news.gallery.title')"
    @dragover.prevent="onCardDragOver"
    @dragleave="onCardDragLeave"
    @drop.prevent="onCardDrop"
  >
    <div class="u-panel__title">
      {{ t('news.gallery.title') }}
    </div>
    <div
      v-if="!newsId"
      class="u-panel__hint"
      style="color:var(--color-warning,#f0a020)"
    >
      {{ t('news.form.saveFirst') }}
    </div>
    <div
      v-else
      class="u-panel__hint"
    >
      {{ t('news.gallery.hint') }}
    </div>

    <div
      v-if="galleryImages.length"
      class="gallery-grid"
    >
      <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
      <div
        v-for="(img, idx) in galleryImages"
        :key="img.id"
        class="gallery-item"
        :class="{ 'gallery-item--drag-over': dragOverIdx === idx }"
        draggable="true"
        role="listitem"
        @dragstart="onDragStart(idx)"
        @dragover.prevent="dragOverIdx = idx"
        @dragleave="dragOverIdx = null"
        @drop.prevent="onDrop(idx)"
      >
        <img
          :src="img.url"
          :alt="img.original_name"
          class="gallery-item__img"
        >
        <div class="gallery-item__overlay">
          <n-button
            size="tiny"
            type="error"
            ghost
            circle
            :loading="deletingId === img.id"
            @click="handleDelete(img.id)"
          >
            <template #icon>
              <n-icon><TrashOutline /></n-icon>
            </template>
          </n-button>
        </div>
        <div class="gallery-item__drag-handle">
          ⠿
        </div>
      </div>
    </div>

    <n-upload
      accept="image/jpeg,image/png,image/webp,image/gif"
      :show-file-list="false"
      :custom-request="handleUpload"
      :disabled="uploading || !newsId"
      multiple
    >
      <n-button
        size="small"
        :loading="uploading"
        :disabled="!newsId"
        style="margin-top:10px"
      >
        <template #icon>
          <n-icon><ImageOutline /></n-icon>
        </template>
        {{ t('news.gallery.upload') }}
      </n-button>
    </n-upload>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NUpload, useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import { TrashOutline, ImageOutline } from '@vicons/ionicons5'
import { useNewsGalleryQuery, useUploadGalleryImageMutation, useDeleteGalleryImageMutation, useReorderGalleryMutation } from '../queries/news'
import { parseApiError } from '../utils/parseApiError'
import type { GalleryImage } from '../api/news'

const props = defineProps<{ newsId: string | undefined }>()

const { t } = useI18n()
const message = useMessage()

const uploadMutation = useUploadGalleryImageMutation()
const deleteMutation = useDeleteGalleryImageMutation()
const reorderMutation = useReorderGalleryMutation()

const galleryImages = ref<GalleryImage[]>([])
const uploading = ref(false)
const deletingId = ref<string | null>(null)
const dragStartIdx = ref<number | null>(null)
const dragOverIdx = ref<number | null>(null)
const galleryDropping = ref(false)

const ACCEPT = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']

const { data: galleryData } = useNewsGalleryQuery(
  () => props.newsId ?? '',
  { enabled: () => !!props.newsId },
)

const initialized = ref(false)
watch(galleryData, (gallery) => {
  if (gallery && !initialized.value) {
    galleryImages.value = [...gallery]
    initialized.value = true
  }
}, { immediate: true })

async function handleUpload(options: UploadCustomRequestOptions) {
  const { file, onFinish, onError } = options
  if (!props.newsId || !file.file) { onError(); return }
  uploading.value = true
  try {
    const img = await uploadMutation.mutateAsync({ newsId: props.newsId, file: file.file })
    galleryImages.value.push(img)
    onFinish()
  } catch (e) {
    message.error(parseApiError(e, t))
    onError()
  } finally {
    uploading.value = false
  }
}

async function handleDelete(imgId: string) {
  if (!props.newsId) return
  deletingId.value = imgId
  try {
    await deleteMutation.mutateAsync({ newsId: props.newsId, imgId })
    galleryImages.value = galleryImages.value.filter(i => i.id !== imgId)
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    deletingId.value = null
  }
}

function onDragStart(idx: number) {
  dragStartIdx.value = idx
}

async function onDrop(targetIdx: number) {
  if (dragStartIdx.value === null || dragStartIdx.value === targetIdx) {
    dragStartIdx.value = null
    dragOverIdx.value = null
    return
  }
  const arr = [...galleryImages.value]
  const [moved] = arr.splice(dragStartIdx.value, 1)
  arr.splice(targetIdx, 0, moved)
  galleryImages.value = arr.map((img, i) => ({ ...img, sort_order: i }))
  dragStartIdx.value = null
  dragOverIdx.value = null
  if (props.newsId) {
    try {
      await reorderMutation.mutateAsync({ newsId: props.newsId, items: galleryImages.value.map((img, i) => ({ id: img.id, sort_order: i })) })
    } catch { /* silent */ }
  }
}

function onCardDragOver(e: DragEvent) {
  if (!props.newsId) return
  if (e.dataTransfer?.types.includes('Files')) galleryDropping.value = true
}

function onCardDragLeave(e: DragEvent) {
  const card = e.currentTarget as HTMLElement
  if (!card.contains(e.relatedTarget as Node)) galleryDropping.value = false
}

async function onCardDrop(e: DragEvent) {
  galleryDropping.value = false
  if (!props.newsId) return
  const files = Array.from(e.dataTransfer?.files ?? []).filter(f => ACCEPT.includes(f.type))
  if (!files.length) return
  uploading.value = true
  try {
    for (const file of files) {
      const img = await uploadMutation.mutateAsync({ newsId: props.newsId, file })
      galleryImages.value.push(img)
    }
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.gallery-panel { margin-top: 16px; }
.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
  margin-bottom: 4px;
}
.gallery-item {
  position: relative;
  border-radius: var(--radius-sm);
  overflow: hidden;
  aspect-ratio: 4 / 3;
  cursor: grab;
  border: 2px solid transparent;
  transition: border-color 0.15s;
}
.gallery-item--drag-over { border-color: var(--color-brand-sky); }
.gallery-item:active { cursor: grabbing; }
.gallery-item__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.gallery-item__overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}
.gallery-item:hover .gallery-item__overlay { opacity: 1; }
.gallery-item__drag-handle {
  position: absolute;
  top: 4px;
  left: 6px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 16px;
  line-height: 1;
  pointer-events: none;
}
</style>
