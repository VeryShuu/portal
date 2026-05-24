<template>
  <div
    class="kb-card"
    role="button"
    tabindex="0"
    @click="$emit('open', article)"
    @keydown.enter="$emit('open', article)"
    @keydown.space.prevent="$emit('open', article)"
  >
    <div class="kb-card__top">
      <span
        class="kb-card__status"
        :class="`kb-card__status--${article.status}`"
      >
        <span
          class="kb-card__status-dot"
          aria-hidden="true"
        />{{ t(`kb.status.${article.status}`, article.status) }}
      </span>
      <span class="kb-card__views">👁 {{ article.view_count }}</span>
    </div>
    <h3 class="kb-card__title">
      {{ article.title }}
    </h3>
    <div class="kb-card__tags">
      <span
        v-for="tag in article.tags.slice(0, 3)"
        :key="tag.id"
        class="kb-tag"
        :class="{ 'kb-tag--active': activeTag === tag.slug }"
        role="button"
        tabindex="0"
        @click.stop="$emit('select-tag', tag.slug)"
        @keydown.enter.stop="$emit('select-tag', tag.slug)"
        @keydown.space.prevent.stop="$emit('select-tag', tag.slug)"
      >
        {{ tag.name }}
      </span>
    </div>
    <div class="kb-card__meta">
      <span v-if="article.created_by">{{ article.created_by.full_name }}</span>
      <span>{{ formatDate(article.updated_at, locale) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { formatDate } from '../utils/formatDate'
import type { KbArticleListItem } from '../api/kb'

defineProps<{
  article: KbArticleListItem
  activeTag: string | null
}>()

defineEmits<{
  (e: 'open', article: KbArticleListItem): void
  (e: 'select-tag', slug: string): void
}>()

const { t, locale } = useI18n()
</script>

<style scoped>
.kb-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 14px 18px;
  cursor: pointer;
  transition: all var(--t-fast);
}
.kb-card:hover {
  border-color: var(--color-brand-sky);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.kb-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.kb-card__status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
}
.kb-card__status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.kb-card__status--published { background: #e8f5e9; color: #2e7d32; }
.kb-card__status--draft { background: #fff3e0; color: #e65100; }
.kb-card__status--archived { background: var(--color-border); color: var(--color-text-muted); }

.kb-card__views {
  font-size: 12px;
  color: var(--color-text-muted);
}

.kb-card__title {
  margin: 0 0 10px;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.kb-card__tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.kb-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--color-brand-sky) 12%, transparent);
  color: var(--color-brand-sky);
  cursor: pointer;
  transition: all var(--t-fast);
}
.kb-tag:hover {
  background: color-mix(in srgb, var(--color-brand-sky) 22%, transparent);
}
.kb-tag--active {
  background: var(--color-brand-sky);
  color: #fff;
}

.kb-card__meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
