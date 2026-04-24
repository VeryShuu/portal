<template>
  <section v-if="visible" class="widget">
    <div class="widget__header">
      <h3 class="widget__title">{{ t('videos.title') }}</h3>
      <a
        v-if="publicUrl"
        :href="publicUrl"
        target="_blank"
        rel="noopener"
        class="widget__link"
      >{{ t('videos.see_all') }}</a>
    </div>

    <div v-if="loading" class="videos-grid">
      <div v-for="i in 6" :key="`vsk-${i}`" class="video-skeleton" />
    </div>

    <div v-else-if="items.length" class="videos-grid">
      <a
        v-for="item in items"
        :key="item.uuid"
        :href="item.watch_url"
        target="_blank"
        rel="noopener"
        class="video-tile"
        :title="item.name"
      >
        <div class="video-tile__thumb">
          <img
            :src="item.thumbnail_url"
            :alt="item.name"
            loading="lazy"
            class="video-tile__img"
            @error="onImgError"
          />
          <span class="video-tile__duration">{{ formatDuration(item.duration) }}</span>
        </div>
        <p class="video-tile__name">{{ item.name }}</p>
      </a>
    </div>

    <p v-else class="videos-empty">{{ t('videos.empty') }}</p>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchRecentVideos, type VideoItem } from '../../api/videos'

const { t } = useI18n()

const loading = ref(true)
const visible = ref(false)
const publicUrl = ref('')
const items = ref<VideoItem[]>([])

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '0:00'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

onMounted(async () => {
  try {
    const data = await fetchRecentVideos()
    if (!data.configured) {
      loading.value = false
      return
    }
    visible.value = true
    publicUrl.value = data.public_url
    items.value = data.items
  } catch {
    // silently hide on error
  } finally {
    loading.value = false
  }
})

function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.visibility = 'hidden'
}
</script>

<style scoped>
.widget {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px 18px 12px;
  box-shadow: var(--shadow-sm);
}
.widget__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.widget__title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}
.widget__link {
  font-size: 12px;
  color: var(--color-brand-red);
  text-decoration: none;
}
.widget__link:hover { text-decoration: underline; }

.videos-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.video-tile {
  display: block;
  text-decoration: none;
  color: inherit;
}
.video-tile__thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: var(--color-bg-muted);
}
.video-tile__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s ease;
}
.video-tile:hover .video-tile__img { transform: scale(1.04); }
.video-tile__duration {
  position: absolute;
  bottom: 4px;
  right: 6px;
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 3px;
  letter-spacing: 0.02em;
}
.video-tile__name {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--color-text);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.video-skeleton {
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-border) 50%, var(--color-bg-muted) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.4s infinite;
}

@keyframes skeleton-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.videos-empty {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
  text-align: center;
  padding: 12px 0;
}
</style>
