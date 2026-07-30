<template>
  <div
    class="html-image-lightbox"
    @click="onClick"
  >
    <slot />

    <!-- Lightbox: клик по любой картинке в slot → полноэкранный просмотр. -->
    <n-modal
      v-model:show="open"
      :auto-focus="false"
      style="background: transparent; box-shadow: none"
    >
      <div
        class="lightbox"
        @click="open = false"
      >
        <img
          v-if="src"
          :src="src"
          :alt="alt"
          class="lightbox__img"
        >
        <span class="lightbox__close">{{ t('common.imageClose') }}</span>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal } from 'naive-ui'

const { t } = useI18n()

const open = ref(false)
const src = ref('')
const alt = ref('')

/**
 * Event-delegation: клик по любому <img> внутри slot открывает полноэкранный
 * просмотр. Содержимое slot рендерится родителем через v-html (sanitized), —
 * повесить @click на каждый <img> напрямую нельзя, делегируем на корень.
 * Аналогично helpdesk-чату; общая логика для KB/helpdesk/news.
 */
function onClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.tagName !== 'IMG') return
  const img = target as HTMLImageElement
  const imgSrc = img.getAttribute('src') || img.currentSrc
  if (!imgSrc) return
  e.preventDefault()
  src.value = imgSrc
  alt.value = img.getAttribute('alt') || ''
  open.value = true
}
</script>

<style scoped>
/* Картинки в обёрнутом контенте: кликабельны (zoom-in). */
.html-image-lightbox :deep(img) {
  cursor: zoom-in;
}
/* Lightbox: полноэкранный просмотр картинки. */
.lightbox {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.88);
  z-index: 2000;
  padding: 24px;
}
.lightbox__img {
  max-width: 92vw;
  max-height: 88vh;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.5);
}
.lightbox__close {
  margin-top: 16px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  font-family: sans-serif;
  user-select: none;
}
</style>
