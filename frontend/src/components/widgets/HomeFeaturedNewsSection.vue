<template>
  <section
    v-if="pinned.length || loadingNews"
    class="section section--featured"
  >
    <div class="section__header">
      <h2 class="section__title">
        {{ t('home.sections.featured') }}
      </h2>
    </div>

    <div
      v-if="loadingNews"
      class="featured-skeleton"
    >
      <SkeletonCard variant="news" />
    </div>
    <template v-else>
      <NewsCard
        v-for="item in pinned"
        :key="item.id"
        :news="item"
        featured
        :categories-map="categoriesMap"
        class="featured-card"
        @click="emit('news-click', $event)"
      />
    </template>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import NewsCard from '../news/NewsCard.vue'
import SkeletonCard from '../SkeletonCard.vue'
import type { News } from '../../api/news'

defineProps<{
  loadingNews: boolean
  pinned: News[]
  categoriesMap: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'news-click', id: string): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.section { margin-bottom: 32px; }
.section--featured { margin-bottom: 0; }
.section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  gap: 12px;
  flex-wrap: wrap;
}
.section__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--color-text);
}
.featured-card,
.featured-skeleton { margin-bottom: 4px; }
</style>
