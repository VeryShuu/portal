<template>
  <Teleport to="body">
    <div class="image-overlay" @click.self="$emit('close')">
      <div class="image-overlay__header">
        <span class="image-overlay__name">{{ currentImage?.name }}</span>
        <span class="image-overlay__counter">{{ previewIndex + 1 }} / {{ images.length }}</span>
        <button class="image-overlay__close" @click="$emit('close')">✕</button>
      </div>
      <div class="image-overlay__body">
        <button
          v-if="images.length > 1"
          class="image-overlay__nav image-overlay__nav--prev"
          @click="prev"
        >‹</button>
        <img
          v-if="currentImage"
          :key="currentImage.name"
          :src="previewFile(folderId, currentImage.name)"
          :alt="currentImage.name"
          class="image-overlay__img"
        />
        <button
          v-if="images.length > 1"
          class="image-overlay__nav image-overlay__nav--next"
          @click="next"
        >›</button>
      </div>
      <div class="image-overlay__footer">
        <n-button
          size="small"
          ghost
          style="color: #fff; border-color: rgba(255,255,255,0.3)"
          tag="a"
          :href="currentImage ? downloadFile(folderId, currentImage.name) : '#'"
          download
        >
          {{ t('files.download') }}
        </n-button>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import { type NCItem, downloadFile, previewFile } from '../../api/files'

const props = defineProps<{
  images: NCItem[]
  initialIndex: number
  folderId: string
}>()

const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()

const previewIndex = ref(props.initialIndex)

const currentImage = computed(() => props.images[previewIndex.value] ?? null)

function prev() {
  previewIndex.value = (previewIndex.value - 1 + props.images.length) % props.images.length
}

function next() {
  previewIndex.value = (previewIndex.value + 1) % props.images.length
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft') prev()
  else if (e.key === 'ArrowRight') next()
  else if (e.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<style>
.image-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.92);
  display: flex;
  flex-direction: column;
  user-select: none;
}

.image-overlay__header {
  display: flex;
  align-items: center;
  padding: 12px 20px;
  flex-shrink: 0;
  gap: 12px;
}

.image-overlay__name {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 500;
  color: #fff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-overlay__counter {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
  flex-shrink: 0;
}

.image-overlay__close {
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.7);
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  flex-shrink: 0;
  line-height: 1;
  transition: color 0.15s, background 0.15s;
}

.image-overlay__close:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}

.image-overlay__body {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  padding: 0 72px;
}

.image-overlay__img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 4px 40px rgba(0, 0, 0, 0.6);
  display: block;
}

.image-overlay__nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255, 255, 255, 0.12);
  border: none;
  color: #fff;
  font-size: 36px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
  line-height: 1;
}

.image-overlay__nav:hover {
  background: rgba(255, 255, 255, 0.25);
}

.image-overlay__nav--prev {
  left: 12px;
}

.image-overlay__nav--next {
  right: 12px;
}

.image-overlay__footer {
  display: flex;
  justify-content: center;
  padding: 12px 20px;
  flex-shrink: 0;
}
</style>
