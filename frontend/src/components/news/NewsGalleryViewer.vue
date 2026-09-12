<template>
  <div
    v-if="images.length"
    class="gallery"
  >
    <h3 class="gallery__title">
      {{ t('news.gallery.title') }}
    </h3>

    <n-image-group>
      <div
        class="gallery__main"
        role="button"
        tabindex="0"
        @click="openLightbox"
        @keydown.enter="openLightbox"
      >
        <n-image
          :src="images[activeIdx].url"
          :alt="images[activeIdx].original_name"
          class="gallery__main-img"
          object-fit="contain"
          preview-disabled
        />
        <div
          v-if="images.length > 1"
          class="gallery__nav gallery__nav--prev"
          role="button"
          tabindex="0"
          @click.stop="prev"
          @keydown.enter.stop="prev"
        >
          <n-icon size="20">
            <ChevronBackOutline />
          </n-icon>
        </div>
        <div
          v-if="images.length > 1"
          class="gallery__nav gallery__nav--next"
          role="button"
          tabindex="0"
          @click.stop="next"
          @keydown.enter.stop="next"
        >
          <n-icon size="20">
            <ChevronForwardOutline />
          </n-icon>
        </div>
        <div
          v-if="images.length > 1"
          class="gallery__counter"
        >
          {{ activeIdx + 1 }} / {{ images.length }}
        </div>
      </div>

      <div
        v-if="images.length > 1"
        class="gallery__thumbs"
      >
        <div
          v-for="(img, idx) in images"
          :key="img.id"
          class="gallery__thumb"
          :class="{ 'gallery__thumb--active': idx === activeIdx }"
          role="button"
          tabindex="0"
          @click="activeIdx = idx"
          @keydown.enter="activeIdx = idx"
        >
          <n-image
            :src="img.url"
            :alt="img.original_name"
            width="80"
            height="60"
            object-fit="cover"
            preview-disabled
          />
        </div>
      </div>

      <div
        class="gallery__lightbox-images"
        aria-hidden="true"
      >
        <n-image
          v-for="img in images"
          :key="`lb-${img.id}`"
          :ref="el => setImgRef(el, img.id)"
          :src="img.url"
          :alt="img.original_name"
          style="display:none"
        />
      </div>
    </n-image-group>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NImage, NImageGroup, NIcon } from 'naive-ui'
import { ChevronBackOutline, ChevronForwardOutline } from '@vicons/ionicons5'
import type { ComponentPublicInstance } from 'vue'
import type { GalleryImage } from '../../api/news'

type NImageInstance = ComponentPublicInstance & { $el?: HTMLElement }

const props = defineProps<{ images: GalleryImage[] }>()
const { t } = useI18n()

const activeIdx = ref(0)
const imgRefs = ref<Record<string, NImageInstance>>({})

function setImgRef(el: Element | ComponentPublicInstance | null, id: string) {
  if (el && '$el' in el) imgRefs.value[id] = el as NImageInstance
}

function prev() {
  activeIdx.value = (activeIdx.value - 1 + props.images.length) % props.images.length
}

function next() {
  activeIdx.value = (activeIdx.value + 1) % props.images.length
}

function openLightbox() {
  const img = props.images[activeIdx.value]
  imgRefs.value[img.id]?.$el?.querySelector('img')?.click()
}
</script>

<style scoped>
.gallery {
  margin-top: 32px;
  padding-top: 28px;
  border-top: 1px solid var(--color-border);
}

.gallery__title {
  margin: 0 0 16px;
  font-size: 15px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
}

.gallery__main {
  position: relative;
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: zoom-in;
  background: var(--color-bg-muted);
  aspect-ratio: 16 / 9;
}

.gallery__main-img {
  width: 100%;
  height: 100%;
  display: block;
}

.gallery__main-img :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.gallery__nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s;
  z-index: 2;
}

.gallery__nav:hover { background: rgba(0, 0, 0, 0.7); }
.gallery__nav--prev { left: 12px; }
.gallery__nav--next { right: 12px; }

.gallery__counter {
  position: absolute;
  bottom: 10px;
  right: 12px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: rgba(0, 0, 0, 0.45);
  padding: 2px 8px;
  border-radius: 20px;
  pointer-events: none;
}

.gallery__thumbs {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.gallery__thumb {
  flex-shrink: 0;
  width: 80px;
  height: 60px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
  opacity: 0.6;
  border: 2px solid transparent;
  transition: opacity 0.15s, border-color 0.15s;
}

.gallery__thumb:hover { opacity: 0.85; }

.gallery__thumb--active {
  opacity: 1;
  border-color: var(--color-brand-sky);
}

.gallery__thumb :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.gallery__lightbox-images {
  position: absolute;
  pointer-events: none;
  opacity: 0;
  width: 0;
  height: 0;
  overflow: hidden;
}
</style>
