<template>
  <div
    v-if="info"
    class="video-embed"
  >
    <iframe
      class="video-embed__frame"
      :src="info.embedUrl"
      :title="title ?? ''"
      sandbox="allow-scripts allow-same-origin allow-presentation"
      allowfullscreen
      loading="lazy"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { parseVideoEmbed, DEFAULT_VIDEO_IFRAME_ORIGINS } from '../../utils/videoEmbed'

/**
 * Встроенный видео-плеер материала курса. Плеер встраивается сразу — как в
 * новостях/БЗ: превью с кнопкой play рисует сам плеер хостинга, а
 * loading="lazy" откладывает загрузку невидимых кадров до прокрутки.
 * allowedOrigins — живой список из /learning/meta; до загрузки — дефолт.
 */
const props = withDefaults(
  defineProps<{ url: string; title?: string; allowedOrigins?: string[] }>(),
  { title: '', allowedOrigins: () => DEFAULT_VIDEO_IFRAME_ORIGINS },
)

const info = computed(() => parseVideoEmbed(props.url, props.allowedOrigins))
</script>

<style scoped>
.video-embed {
  margin-top: 8px;
  width: 100%;
  max-width: 560px;
  aspect-ratio: 16 / 9;
}

.video-embed__frame {
  width: 100%;
  height: 100%;
  border: 0;
  border-radius: 10px;
  background: #000;
}
</style>
