<template>
  <article
    class="news-card"
    :class="[
      { 'news-card--pinned': news.is_pinned, 'news-card--featured': featured },
    ]"
    tabindex="0"
    role="button"
    @click="$emit('click', news.id)"
    @keyup.enter="$emit('click', news.id)"
  >
    <div
      class="news-card__cover"
      :class="{ 'news-card__cover--gradient': !news.cover_image_url }"
      :style="fallbackStyle"
    >
      <picture v-if="news.cover_image_url">
        <source
          v-if="news.cover_avif_srcset"
          type="image/avif"
          :srcset="news.cover_avif_srcset"
          :sizes="coverSizes"
        >
        <source
          v-if="news.cover_webp_srcset"
          type="image/webp"
          :srcset="news.cover_webp_srcset"
          :sizes="coverSizes"
        >
        <img
          :src="news.cover_image_url"
          :alt="news.title"
          class="news-card__cover-img"
          :style="{ objectPosition: focalObjectPosition }"
          :width="featured ? 2100 : 1600"
          :height="900"
          :loading="featured ? 'eager' : 'lazy'"
          :fetchpriority="featured ? 'high' : 'auto'"
          decoding="async"
        >
      </picture>
      <div class="news-card__cover-overlay" />
      <div class="news-card__badges">
        <span
          v-if="news.is_pinned"
          class="badge badge--pinned"
        >
          <n-icon size="12"><StarOutline /></n-icon>
          {{ t('news.pinned') }}
        </span>
        <span
          v-for="cat in news.categories"
          :key="cat"
          class="badge"
          :style="badgeStyle(cat)"
        >
          {{ cat }}
        </span>
      </div>
      <div
        v-if="featured"
        class="news-card__overlay-title"
      >
        <h2>{{ news.title }}</h2>
      </div>
    </div>

    <div
      v-if="!featured"
      class="news-card__body"
    >
      <h3 class="news-card__title">
        {{ news.title }}
      </h3>
      <p class="news-card__excerpt">
        {{ excerpt }}
      </p>
    </div>

    <div class="news-card__footer">
      <span class="news-card__date">{{ formattedDate }}</span>
      <span class="news-card__views">
        <n-icon size="13"><EyeOutline /></n-icon>
        {{ news.view_count }}
      </span>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { EyeOutline, StarOutline } from '@vicons/ionicons5'
import type { News } from '../api/news'

defineEmits<{ click: [id: string] }>()
const props = defineProps<{
  news: News
  featured?: boolean
  categoriesMap?: Record<string, string>
}>()
const { t, locale } = useI18n()

const excerpt = computed(() => {
  const raw = props.news.body ?? ''
  const stripped = raw
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]*)`/g, '$1')
  const el = document.createElement('div')
  el.innerHTML = stripped
  const text = (el.textContent ?? '')
    .replace(/[#*_`>[\]]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return text.length > 160 ? text.slice(0, 160) + '…' : text
})

const formattedDate = computed(() => {
  const d = props.news.published_at ?? props.news.created_at
  const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
  return new Date(d).toLocaleDateString(lang, { day: 'numeric', month: 'short', year: 'numeric' })
})

const gradientPalette = [
  'linear-gradient(135deg, #0b2a4a 0%, #143a66 100%)',
  'linear-gradient(135deg, #143a66 0%, #4a90c4 100%)',
  'linear-gradient(135deg, #4a1820 0%, #d8262c 100%)',
  'linear-gradient(135deg, #1f4e85 0%, #6faed8 100%)',
  'linear-gradient(135deg, #0b2a4a 0%, #4a90c4 100%)',
  'linear-gradient(135deg, #2a1a4a 0%, #6b4a8a 100%)',
]

const fallbackStyle = computed(() => {
  if (props.news.cover_image_url) {
    if (props.news.cover_dominant_color) {
      return { backgroundColor: props.news.cover_dominant_color }
    }
    return {}
  }
  const id = props.news.id ?? ''
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash + id.charCodeAt(i)) % gradientPalette.length
  return { background: gradientPalette[hash] }
})

const coverSizes = computed(() =>
  props.featured
    ? '(max-width: 900px) 100vw, 1200px'
    : '(max-width: 600px) 100vw, (max-width: 1200px) 50vw, 400px',
)

const focalObjectPosition = computed(() => {
  const fp = props.news.cover_focal_point
  if (fp === 'top') return '50% 0%'
  if (fp === 'bottom') return '50% 100%'
  return '50% 50%'
})

const _DEFAULT_BADGE_COLOR = '#6B7AE8'

function badgeStyle(cat: string): Record<string, string> {
  const color = props.categoriesMap?.[cat] ?? _DEFAULT_BADGE_COLOR
  const r = parseInt(color.slice(1, 3), 16)
  const g = parseInt(color.slice(3, 5), 16)
  const b = parseInt(color.slice(5, 7), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  const textColor = luminance > 0.55 ? '#1a1a1a' : '#ffffff'
  return { backgroundColor: color, color: textColor }
}
</script>

<style scoped>
.news-card {
  position: relative;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: transform var(--t-base), box-shadow var(--t-base), border-color var(--t-base);
  box-shadow: var(--shadow-sm);
  outline: none;
}
.news-card:hover,
.news-card:focus-visible {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--color-brand-sky);
}
.news-card--pinned {
  border-color: var(--color-brand-red);
  box-shadow: 0 0 0 1px var(--color-brand-red), var(--shadow-sm);
}

.news-card__cover {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
}
.news-card__cover-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.news-card--featured .news-card__cover {
  aspect-ratio: 21 / 9;
}
.news-card__cover-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(11, 42, 74, 0) 0%, rgba(11, 42, 74, 0.6) 100%);
}
.news-card__badges {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  z-index: 1;
}
.news-card__overlay-title {
  position: absolute;
  left: 20px;
  right: 20px;
  bottom: 16px;
  z-index: 1;
}
.news-card__overlay-title h2 {
  margin: 0;
  color: #fff;
  font-size: 22px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.01em;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.9);
  color: var(--color-brand-navy);
}
.badge--pinned {
  background: var(--color-brand-red);
  color: #fff;
}

.news-card__body {
  padding: 16px 18px 8px;
  flex: 1;
}
.news-card__title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--color-text);
  letter-spacing: -0.01em;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.news-card__excerpt {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.news-card__footer {
  padding: 10px 18px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--color-text-subtle);
  border-top: 1px solid var(--color-border);
  margin-top: auto;
}
.news-card--featured .news-card__footer {
  border-top: none;
  padding-top: 14px;
}
.news-card__views {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
