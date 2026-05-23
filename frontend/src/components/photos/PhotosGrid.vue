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
    <div
      v-if="loading"
      class="photo-grid"
    >
      <div
        v-for="i in 12"
        :key="`pgsk-${i}`"
        class="photo-skeleton"
      />
    </div>
    <div
      v-else-if="photos.length"
      class="photo-grid"
    >
      <div
        v-for="(p, idx) in photos"
        :key="p.id"
        class="photo-cell"
        :class="{ 'photo-cell--selected': selectedPhotoIds.has(p.id) }"
        draggable="false"
        role="button"
        tabindex="0"
        @click="$emit('photo-click', p, idx)"
        @keydown.enter="$emit('photo-click', p, idx)"
        @keydown.space.prevent="$emit('photo-click', p, idx)"
      >
        <picture>
          <source
            type="image/avif"
            :srcset="`${thumbAvifUrl(p.id, 400)} 400w, ${thumbAvifUrl(p.id, 600)} 600w`"
            sizes="(max-width: 400px) 400px, 600px"
          >
          <source
            type="image/webp"
            :srcset="`${thumbUrl(p.id, 400)} 400w, ${thumbUrl(p.id, 600)} 600w`"
            sizes="(max-width: 400px) 400px, 600px"
          >
          <img
            :src="thumbUrl(p.id, 600)"
            :alt="p.original_name"
            loading="lazy"
            draggable="false"
            class="photo-cell__img"
          >
        </picture>
        <label
          v-if="selectMode"
          class="photo-cell__check"
          :for="`photo-check-${p.id}`"
          @click.stop
        >
          <input
            :id="`photo-check-${p.id}`"
            type="checkbox"
            :checked="selectedPhotoIds.has(p.id)"
            :aria-label="p.original_name"
            @change="$emit('toggle-select', p.id)"
          >
        </label>
        <button
          v-if="canDelete(p) && !selectMode"
          class="photo-cell__del"
          :aria-label="t('common.delete')"
          @click.stop="$emit('delete-photo', p)"
        >
          ×
        </button>
      </div>
    </div>
    <EmptyState
      v-else
      variant="photo"
      :title="t('photos.empty')"
    />
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
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import EmptyState from '../EmptyState.vue'
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
</style>
