<template>
  <main class="kb-main">
    <KbListToolbar
      v-model:search-query="searchQuery"
      v-model:status-filter="statusFilter"
      v-model:tag-filter="tagFilter"
      :tag-options="listing.tagOptions.value"
      :view-mode="viewMode"
      @update:view-mode="emit('update:view-mode', $event)"
      @search-input="listing.onSearchInput"
    />

    <div
      v-if="listing.loading.value"
      :class="viewMode === 'grid' ? 'kb-grid' : 'kb-list'"
    >
      <SkeletonCard
        v-for="i in 6"
        :key="`sk-${i}`"
        :variant="viewMode === 'grid' ? 'article' : 'folder-item'"
      />
    </div>

    <template v-else>
      <div
        v-if="listing.articles.value.length && viewMode === 'grid'"
        class="kb-grid"
      >
        <KbArticleCard
          v-for="article in listing.articles.value"
          :key="article.id"
          :article="article"
          :active-tag="listing.tagFilter.value"
          @open="emit('open-article', $event.id)"
          @select-tag="listing.selectTag"
        />
      </div>

      <div
        v-else-if="listing.articles.value.length"
        class="kb-list"
      >
        <KbArticleListRow
          v-for="article in listing.articles.value"
          :key="article.id"
          :article="article"
          :active-tag="listing.tagFilter.value"
          @open="emit('open-article', $event.id)"
          @select-tag="listing.selectTag"
        />
      </div>

      <EmptyState
        v-else
        variant="default"
        :title="t('kb.noArticles')"
        :description="t('kb.noArticlesHint')"
      />

      <n-pagination
        v-if="listing.total.value > listing.pageSize"
        v-model:page="page"
        :page-count="Math.ceil(listing.total.value / listing.pageSize)"
        style="margin-top:28px;justify-content:center"
      />
    </template>
  </main>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NPagination } from 'naive-ui'
import SkeletonCard from './SkeletonCard.vue'
import EmptyState from './EmptyState.vue'
import KbArticleCard from './KbArticleCard.vue'
import KbArticleListRow from './KbArticleListRow.vue'
import KbListToolbar, { type KbViewMode } from './KbListToolbar.vue'
import type { useKbArticleListing } from '../composables/useKbArticleListing'

defineProps<{
  listing: ReturnType<typeof useKbArticleListing>
  viewMode: KbViewMode
}>()

const emit = defineEmits<{
  (e: 'update:view-mode', value: KbViewMode): void
  (e: 'open-article', id: string): void
}>()

const searchQuery = defineModel<string>('searchQuery', { required: true })
const statusFilter = defineModel<string | null>('statusFilter', { required: true })
const tagFilter = defineModel<string | null>('tagFilter', { required: true })
const page = defineModel<number>('page', { required: true })

const { t } = useI18n()
</script>

<style scoped>
.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.kb-list {
  display: flex;
  flex-direction: column;
}
</style>
