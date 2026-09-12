<template>
  <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
  <div
    class="photo-grid-drop-zone"
    :class="{ 'drag-over': isDraggingOver && canUpload }"
    role="region"
    :aria-label="t('photos.a11y.dropZone')"
    @dragover.prevent="onDragOver"
    @dragleave="$emit('drag-leave')"
    @drop.prevent="onDropEvent"
  >
    <PhotosGridBase
      :photos="photos"
      :loading="loading"
      :cell-class="cellClassFor"
      @photo-click="(p, idx) => $emit('photo-click', p, idx)"
    >
      <template #cell="{ photo }">
        <PhotoThumb
          :photo-id="photo.id"
          :processed="photo.processed"
          :blurhash="photo.blurhash"
          :preview-url="previewUrls?.[photo.id]"
          :alt="photo.original_name"
          :sizes="[400, 600]"
          sizes-attr="(max-width: 400px) 400px, 600px"
          :avif="thumbAvifUrl"
          :webp="thumbUrl"
        />
        <label
          v-if="selectMode"
          class="photo-cell__check"
          :for="`photo-check-${photo.id}`"
          @click.stop
        >
          <input
            :id="`photo-check-${photo.id}`"
            type="checkbox"
            :checked="selectedPhotoIds.has(photo.id)"
            :aria-label="photo.original_name"
            @change="$emit('toggle-select', photo.id)"
          >
        </label>
        <button
          v-if="canDelete(photo) && !selectMode"
          class="photo-cell__del"
          :aria-label="t('common.delete')"
          @click.stop="$emit('delete-photo', photo)"
        >
          ×
        </button>
      </template>
      <template #empty>
        <EmptyState
          variant="photo"
          :title="t('photos.empty')"
        />
      </template>
    </PhotosGridBase>
    <div
      v-if="isDraggingOver && canUpload"
      class="drop-overlay"
    >
      {{ t('photos.upload.dropHere') }}
    </div>
  </div>

  <div
    v-if="totalPhotos > photos.length"
    class="photo-loadmore"
  >
    <n-button
      :loading="loading"
      :disabled="loading"
      @click="$emit('load-more')"
    >
      {{ t('common.loadMore') }}
    </n-button>
  </div>

  <div
    v-if="selectMode"
    class="multiselect-toolbar"
  >
    <span>{{ t('photos.select.count', { n: selectedPhotoIds.size }) }}</span>
    <n-button
      size="small"
      type="error"
      :disabled="selectedPhotoIds.size === 0"
      @click="$emit('bulk-delete')"
    >
      {{ t('photos.select.delete') }}
    </n-button>
    <n-button
      size="small"
      :disabled="selectedPhotoIds.size === 0"
      @click="$emit('open-move')"
    >
      {{ t('photos.select.move') }}
    </n-button>
    <n-button
      size="small"
      @click="$emit('toggle-select-mode')"
    >
      {{ t('photos.select.cancel') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import EmptyState from '../EmptyState.vue'
import PhotosGridBase from './PhotosGridBase.vue'
import PhotoThumb from './PhotoThumb.vue'
import { thumbUrl, thumbAvifUrl, type Photo } from '@/api/photos'

const props = defineProps<{
  photos: Photo[]
  totalPhotos: number
  loading: boolean
  selectMode: boolean
  selectedPhotoIds: Set<string>
  canUpload: boolean
  canDelete: (p: Photo) => boolean
  isDraggingOver: boolean
  previewUrls?: Record<string, string>
}>()

const emit = defineEmits<{
  'photo-click': [photo: Photo, idx: number]
  'toggle-select': [id: string]
  'delete-photo': [photo: Photo]
  'load-more': []
  'bulk-delete': []
  'open-move': []
  'toggle-select-mode': []
  'drag-over': []
  'drag-leave': []
  'drop': [event: DragEvent]
}>()

const { t } = useI18n()

function cellClassFor(p: { id: string }): string | undefined {
  return props.selectedPhotoIds.has(p.id) ? 'photo-cell--selected' : undefined
}

// #F-6: при смене папки во время drag (canUpload → false) подсветка должна
// сбрасываться реактивно, иначе остаётся «зависший» drag-state до dragleave.
watch(
  () => props.canUpload,
  (next) => {
    if (!next && props.isDraggingOver) emit('drag-leave')
  },
)

function onDragOver() {
  if (props.canUpload) emit('drag-over')
}

function onDropEvent(event: DragEvent) {
  if (props.canUpload) emit('drop', event)
  else emit('drag-leave')
}
</script>

<style scoped>
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

:deep(.photo-cell--selected) { outline: 3px solid var(--color-primary, #3b82f6); }

.photo-cell__del {
  position: absolute; top: 4px; right: 4px;
  background: rgba(0,0,0,0.6); color: #fff; border: 0; cursor: pointer;
  width: 24px; height: 24px; border-radius: 50%; font-size: 16px; line-height: 1;
  display: none;
  z-index: 1;
}
:deep(.photo-cell:hover) .photo-cell__del { display: inline-flex; align-items: center; justify-content: center; }
.photo-cell__check {
  position: absolute; top: 6px; left: 6px;
  width: 20px; height: 20px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  z-index: 1;
}
.photo-cell__check input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }

.photo-loadmore { text-align: center; margin-top: 16px; }

.multiselect-toolbar {
  position: sticky; bottom: 0;
  display: flex; align-items: center; gap: 10px;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
  padding: 10px 0;
  margin-top: 16px;
}
</style>
