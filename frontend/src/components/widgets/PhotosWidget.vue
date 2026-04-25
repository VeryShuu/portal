<template>
  <section v-if="show" class="widget">
    <div class="widget__header">
      <h3 class="widget__title">{{ t('photos.title') }}</h3>
      <a class="widget__link" href="/photos">{{ t('photos.see_all') }}</a>
    </div>

    <div v-if="loading" class="photos-grid">
      <div v-for="i in 8" :key="`psk-${i}`" class="photo-skeleton" />
    </div>

    <div v-else-if="store.recent.length" class="photos-grid">
      <a
        v-for="p in store.recent"
        :key="p.id"
        :href="`/photos?photo=${p.id}`"
        class="photo-tile"
        :title="p.original_name"
      >
        <img
          :src="thumbUrl(p.id, 200)"
          :alt="p.original_name"
          loading="lazy"
          class="photo-tile__img"
          @error="onImgError"
        />
      </a>
    </div>

    <p v-else class="photos-empty">{{ t('photos.empty') }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePhotosStore } from '@/stores/photos'
import { thumbUrl } from '@/api/photos'

const { t } = useI18n()
const store = usePhotosStore()

const loading = computed(() => store.recentLoading && !store.recentLoaded)
const show = computed(() => store.configured)

onMounted(() => {
  if (!store.recentLoaded) store.loadRecent(8)
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

.photos-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}
.photo-tile {
  display: block;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: var(--color-bg-muted);
}
.photo-tile__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s ease;
}
.photo-tile:hover .photo-tile__img { transform: scale(1.06); }

.photo-skeleton {
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-border) 50%, var(--color-bg-muted) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.4s infinite;
}
@keyframes skeleton-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.photos-empty {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
  text-align: center;
  padding: 12px 0;
}
</style>
