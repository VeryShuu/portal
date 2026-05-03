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
    <div class="news-card__cover" :class="{ 'news-card__cover--gradient': !news.cover_image_url }" :style="fallbackStyle">
      <img
        v-if="news.cover_image_url"
        :src="news.cover_image_url"
        :alt="news.title"
        class="news-card__cover-img"
        :style="{ objectPosition: focalObjectPosition }"
        loading="lazy"
      />
      <div class="news-card__cover-overlay" />
      <div class="news-card__badges">
        <span v-if="news.is_pinned" class="badge badge--pinned">
          <n-icon size="12"><StarOutline /></n-icon>
          {{ t('news.pinned') }}
        </span>
        <span v-if="news.category" class="badge" :class="categoryClass">
          {{ news.category }}
        </span>
      </div>
      <div v-if="featured" class="news-card__overlay-title">
        <h2>{{ news.title }}</h2>
      </div>
    </div>

    <div v-if="!featured" class="news-card__body">
      <h3 class="news-card__title">{{ news.title }}</h3>
      <p class="news-card__excerpt">{{ excerpt }}</p>
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
}>()
const { t, locale } = useI18n()

const excerpt = computed(() => {
  const text = props.news.body.replace(/<[^>]*>/g, '').replace(/[#*_`>[\]]/g, '').trim()
  return text.length > 160 ? text.slice(0, 160) + '…' : text
})

const formattedDate = computed(() => {
  const d = props.news.published_at ?? props.news.created_at
  const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
  return new Date(d).toLocaleDateString(lang, { day: 'numeric', month: 'short' })
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
  if (props.news.cover_image_url) return {}
  const id = props.news.id ?? ''
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash + id.charCodeAt(i)) % gradientPalette.length
  return { background: gradientPalette[hash] }
})

const focalObjectPosition = computed(() => {
  const fp = props.news.cover_focal_point
  if (fp === 'top') return '50% 0%'
  if (fp === 'bottom') return '50% 100%'
  return '50% 50%'
})

const categoryClass = computed(() => {
  const c = (props.news.category ?? '').toLowerCase()
  if (c.includes('hr') || c.includes('кадр')) return 'badge--hr'
  if (c.includes('it') || c.includes('ит') || c.includes('техн')) return 'badge--it'
  if (c.includes('fin') || c.includes('фин')) return 'badge--finance'
  return 'badge--general'
})
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
.badge--hr       { background: var(--badge-hr-bg); color: var(--badge-hr-fg); }
.badge--it       { background: var(--badge-it-bg); color: var(--badge-it-fg); }
.badge--finance  { background: var(--badge-finance-bg); color: var(--badge-finance-fg); }
.badge--general  { background: var(--badge-general-bg); color: var(--badge-general-fg); }

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
