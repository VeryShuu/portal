<template>
  <!-- eslint-disable-next-line vuejs-accessibility/click-events-have-key-events, vuejs-accessibility/no-static-element-interactions -->
  <div
    class="lightbox__stage"
    @click.self="$emit('close')"
  >
    <picture v-if="currentPhoto">
      <source
        type="image/avif"
        :srcset="`${thumbAvifUrl(currentPhoto.id, 1000)} 1000w, ${thumbAvifUrl(currentPhoto.id, 1600)} 1600w`"
        sizes="(max-width: 1000px) 1000px, 1600px"
      >
      <source
        type="image/webp"
        :srcset="`${thumbUrl(currentPhoto.id, 1000)} 1000w, ${thumbUrl(currentPhoto.id, 1600)} 1600w`"
        sizes="(max-width: 1000px) 1000px, 1600px"
      >
      <img
        :src="thumbUrl(currentPhoto.id, 1600)"
        :alt="currentPhoto.original_name"
        class="lightbox__img"
        :style="imgStyle"
        @click.stop
      >
    </picture>
  </div>
</template>

<script setup lang="ts">
import { thumbUrl, thumbAvifUrl, type Photo } from '@/api/photos'

defineProps<{
  currentPhoto: Photo | null
  imgStyle: Record<string, string>
}>()

defineEmits<{
  (e: 'close'): void
}>()
</script>

<style scoped>
.lightbox__stage {
  width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.lightbox__img { max-width: 95vw; max-height: 90vh; object-fit: contain; user-select: none; -webkit-user-drag: none; }
</style>
