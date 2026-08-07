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
      v-for="(item, i) in regular"
      :key="item.id"
      :news="item"
      :categories-map="categoriesMap"
      :style="{ '--card-index': i }"
      @click="emit('news-click', $event)"
    />

    <!-- Последняя ячейка — плитка «Смотреть все новости» → /news.
         Заполняет 6-ю ячейку сетки 3×N, заменяет отдельную кнопку в шапке. -->
    <RouterLink
      to="/news"
      class="view-all-tile"
    >
      <span class="view-all-tile__icon">
        <n-icon :size="28"><ArrowForwardOutline /></n-icon>
      </span>
      <span class="view-all-tile__label">{{ t('home.viewAll') }}</span>
    </RouterLink>
  </div>
  <EmptyState
    v-else
    variant="news"
    :title="t('news.noNews')"
  />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { ArrowForwardOutline } from '@vicons/ionicons5'
import { RouterLink } from 'vue-router'
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
/* Сетка новостей 3×N. Единственный grid внутри main; правая колонка страницы —
   отдельный <aside>, в этой сетке не участвует. */
.news-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
/* Staggered fade-in при появлении карточек (п.7 UX-аудита). --card-index
   задаётся inline через :style, delay растёт на 50ms между карточками. */
.news-grid :deep(.news-card) {
  animation: news-card-in 0.4s ease both;
  animation-delay: calc(var(--card-index, 0) * 0.05s);
}
@keyframes news-card-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) {
  .news-grid :deep(.news-card) { animation: none; }
}
/* На ноутбуках (1366–1440) main ~770px → 3 колонки по ~228px узковаты,
   заголовок в 2 строки читается тяжело. Ниже 1400 — 2 колонки (~380px каждая). */
@media (max-width: 1400px) {
  .news-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  /* На узком main (мобильный/планшет после коллапса aside) — 2 колонки, потом 1 */
  .news-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .news-grid { grid-template-columns: 1fr; }
}

/* Плита «Смотреть все новости» — 6-я ячейка сетки.
   Спокойнее основных карточек: лёгкий navy-фон с прозрачностью + dashed-граница,
   чтобы новостные карточки оставались главным визуальным якорем. */
.view-all-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 150px;
  border-radius: var(--radius-card, var(--radius-lg));
  background: color-mix(in srgb, var(--color-mage-primary, #1f4e8c) 8%, var(--color-mage-card, transparent));
  border: 2px dashed color-mix(in srgb, var(--color-mage-secondary, #2f6cb5) 35%, transparent);
  color: var(--color-mage-primary, #1f4e8c);
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  transition: transform var(--t-base), border-color var(--t-base), background var(--t-base);
}
.view-all-tile:hover {
  transform: translateY(-2px);
  border-color: var(--color-mage-secondary, #2f6cb5);
  background: color-mix(in srgb, var(--color-mage-secondary, #2f6cb5) 12%, var(--color-mage-card, transparent));
}
.view-all-tile__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-mage-secondary, #2f6cb5) 15%, transparent);
}
/* Dark theme: цвет текста/иконок осветляется для контраста на тёмной карточке. */
[data-theme='dark'] .view-all-tile {
  color: var(--color-mage-secondary, #6faed8);
}
.view-all-tile:focus-visible {
  outline: 2px solid var(--color-mage-secondary, #2f6cb5);
  outline-offset: 3px;
}
.view-all-tile__label {
  text-align: center;
  padding: 0 12px;
}
</style>
