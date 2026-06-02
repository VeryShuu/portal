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
import NewsCard from '../NewsCard.vue'
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
.news-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 720px) {
  .news-grid { grid-template-columns: 1fr; }
}
</style>
