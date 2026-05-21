<template>
  <div
    class="kb-row"
    role="button"
    tabindex="0"
    @click="$emit('open', article)"
    @keydown.enter="$emit('open', article)"
  >
    <span
      class="kb-row__status"
      :class="`kb-row__status--${article.status}`"
      :title="t(`kb.status.${article.status}`, article.status)"
    >
      <span
        class="kb-row__status-dot"
        aria-hidden="true"
      />
    </span>

    <div class="kb-row__main">
      <span class="kb-row__title">{{ article.title }}</span>
      <div
        v-if="article.tags.length"
        class="kb-row__tags"
      >
        <span
          v-for="tag in article.tags.slice(0, 4)"
          :key="tag.id"
          class="kb-tag"
          :class="{ 'kb-tag--active': activeTag === tag.slug }"
          role="button"
          tabindex="0"
          @click.stop="$emit('select-tag', tag.slug)"
          @keydown.enter.stop="$emit('select-tag', tag.slug)"
        >
          {{ tag.name }}
        </span>
      </div>
    </div>

    <span
      v-if="article.created_by"
      class="kb-row__author"
    >{{ article.created_by.full_name }}</span>

    <span class="kb-row__date">{{ formatDate(article.updated_at, locale) }}</span>

    <span
      class="kb-row__views"
      :title="t('kb.views', { n: article.view_count })"
    >👁 {{ article.view_count }}</span>
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
.kb-row {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--t-fast);
}
.kb-row + .kb-row {
  margin-top: 6px;
}
.kb-row:hover {
  border-color: var(--color-brand-sky);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.kb-row__status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.kb-row__status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: currentColor;
}
.kb-row__status--published { color: #2e7d32; }
.kb-row__status--draft { color: #e65100; }
.kb-row__status--archived { color: var(--color-text-muted); }

.kb-row__main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.kb-row__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-row__tags {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
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

.kb-row__author,
.kb-row__date,
.kb-row__views {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}
.kb-row__author {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 720px) {
  .kb-row {
    grid-template-columns: 14px minmax(0, 1fr) auto;
    gap: 10px;
  }
  .kb-row__author,
  .kb-row__date {
    display: none;
  }
}
</style>
