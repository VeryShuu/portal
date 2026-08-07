<template>
  <div
    v-if="loadingNews"
    class="news-grid"
  >
    <SkeletonCard
      v-for="i in 4"
      :key="`sk-${i}`"
      variant="news"
    />
  </div>
  <div
    v-else-if="regular.length"
    class="news-grid"
  >
    <NewsCard
      v-for="item in regular"
      :key="item.id"
      :news="item"
      :categories-map="categoriesMap"
      @click="emit('news-click', $event)"
    />
  </div>
  <EmptyState
    v-else
    variant="news"
    :title="t('news.noNews')"
  />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import NewsCard from '../news/NewsCard.vue'
import EmptyState from '../EmptyState.vue'
import SkeletonCard from '../SkeletonCard.vue'
import type { News } from '../../api/news'

defineProps<{
  loadingNews: boolean
  regular: News[]
  categoriesMap: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'news-click', id: string): void
}>()

const { t } = useI18n()
</script>

<style scoped>
/* Сетка новостей 3×N (концепт). Это единственный grid внутри main; правая
   колонка страницы — отдельный <aside>, в этой сетке не участвует. */
.news-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-card-gap, 20px);
}
@media (max-width: 900px) {
  /* На узком main (мобильный/планшет после коллапса aside) — 2 колонки, потом 1 */
  .news-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .news-grid { grid-template-columns: 1fr; }
}
</style>
