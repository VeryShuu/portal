<template>
  <section v-if="visible" class="widget">
    <div class="widget__header">
      <h3 class="widget__title">{{ t('photos.title') }}</h3>
      <a
        v-if="publicUrl"
        :href="publicUrl"
        target="_blank"
        rel="noopener"
        class="widget__link"
      >{{ t('photos.see_all') }}</a>
    </div>

    <div v-if="loading" class="photos-grid">
      <div v-for="i in 8" :key="`psk-${i}`" class="photo-skeleton" />
    </div>

    <div v-else-if="items.length" class="photos-grid">
      <a
        v-for="item in items"
        :key="item.id"
        :href="item.original_url"
        target="_blank"
        rel="noopener"
        class="photo-tile"
        :title="item.file_name"
      >
        <img
          :src="item.thumbnail_url"
          :alt="item.file_name"
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
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchRecentPhotos, type PhotoItem } from '../../api/photos'

const { t } = useI18n()

const loading = ref(true)
const visible = ref(false)
const publicUrl = ref('')
const items = ref<PhotoItem[]>([])

onMounted(async () => {
  try {
    const data = await fetchRecentPhotos()
    if (!data.configured) {
      loading.value = false
      return
    }
    visible.value = true
    publicUrl.value = data.public_url
    items.value = data.items
  } catch {
    // silently hide the widget on error
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

.photos-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px;
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
