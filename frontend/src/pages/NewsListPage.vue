<template>
  <div class="news-list-wrap">
      <div class="page-head">
        <div class="page-head__left">
          <h1 class="page-head__title">{{ t('news.title') }}</h1>
          <div class="page-head__sub">{{ t('news.pageSub') }}</div>
        </div>
        <div class="page-head__right">
          <n-button v-if="auth.isEditor" type="primary" size="medium" @click="router.push('/news/create')">
            + {{ t('news.create.title') }}
          </n-button>
        </div>
      </div>

      <div class="filters" role="toolbar" :aria-label="t('news.filters.aria')">
        <button
          type="button"
          class="chip"
          :class="{ 'chip--active': activeChip === 'all' }"
          @click="activeChip = 'all'"
        >
          {{ t('news.filters.all') }}
        </button>
        <button
          type="button"
          class="chip"
          :class="{ 'chip--active': activeChip === 'pinned' }"
          @click="activeChip = 'pinned'"
        >
          {{ t('news.filters.pinned') }}
        </button>

        <button
          v-for="cat in categories"
          :key="cat"
          type="button"
          class="chip"
          :class="{ 'chip--active': activeChip === `cat:${cat}` }"
          @click="activeChip = `cat:${cat}`"
        >
          {{ cat }}
        </button>

        <n-select
          v-if="auth.isEditor"
          v-model:value="statusFilter"
          :options="statusOptions"
          size="small"
          style="width:160px;margin-left:auto"
          clearable
          :placeholder="t('news.filters.status')"
        />
      </div>


      <div v-if="loading" class="news-grid">
        <SkeletonCard variant="news" v-for="i in 6" :key="`sk-${i}`" />
      </div>
      <template v-else>
        <div v-if="filtered.length" class="news-grid">
          <NewsCard
            v-for="item in filtered"
            :key="item.id"
            :news="item"
            @click="id => router.push(`/news/${id}`)"
          />
        </div>
        <EmptyState
          v-else
          variant="news"
          :title="t('news.noNews')"
          :description="t('news.noNewsHint')"
        />

        <div ref="sentinel" class="news-sentinel" />
        <div v-if="loadingMore" class="news-grid news-grid--more">
          <SkeletonCard variant="news" v-for="i in 3" :key="`sk-more-${i}`" />
        </div>
      </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NSelect } from 'naive-ui'
import { useQuery } from '@tanstack/vue-query'
import NewsCard from '../components/NewsCard.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import { useAuthStore } from '../stores/auth'
import {
  fetchNewsList,
  fetchNewsCategories,
  type News,
} from '../api/news'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

const loadingMore = ref(false)
const accumulatedNews = ref<News[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 24
const statusFilter = ref<string | null>(null)
const activeChip = ref<string>('all')
const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

const categories = ref<string[]>([])

const statusOptions = [
  { label: t('news.status.draft'), value: 'draft' },
  { label: t('news.status.published'), value: 'published' },
  { label: t('news.status.archived'), value: 'archived' },
]

const { data: newsPage, isLoading: loading } = useQuery({
  queryKey: computed(() => ['news-list', statusFilter.value]),
  queryFn: () => fetchNewsList({
    page: 1,
    page_size: pageSize,
    ...(statusFilter.value ? { status: statusFilter.value } : {}),
  }),
  staleTime: 60_000,
})

watch(newsPage, (data) => {
  if (data) {
    accumulatedNews.value = data.items
    total.value = data.total
    page.value = 1
    setupObserver()
  }
}, { immediate: true })

const filtered = computed(() => {
  if (activeChip.value === 'all') return accumulatedNews.value
  if (activeChip.value === 'pinned') return accumulatedNews.value.filter((n) => n.is_pinned)
  if (activeChip.value.startsWith('cat:')) {
    const target = activeChip.value.slice(4).toLowerCase()
    return accumulatedNews.value.filter((n) => n.categories.some((c) => c.toLowerCase() === target))
  }
  return accumulatedNews.value
})

const hasMore = computed(() => accumulatedNews.value.length < total.value)

async function loadMore() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  try {
    const nextPage = page.value + 1
    const res = await fetchNewsList({
      page: nextPage,
      page_size: pageSize,
      ...(statusFilter.value ? { status: statusFilter.value } : {}),
    })
    accumulatedNews.value = [...accumulatedNews.value, ...res.items]
    total.value = res.total
    page.value = nextPage
  } finally {
    loadingMore.value = false
  }
}

function setupObserver() {
  if (observer) observer.disconnect()
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) loadMore()
    },
    { rootMargin: '200px' },
  )
  if (sentinel.value) observer.observe(sentinel.value)
}

async function loadCategories() {
  try {
    categories.value = await fetchNewsCategories()
  } catch {
    categories.value = []
  }
}


onMounted(() => {
  loadCategories()
})

onUnmounted(() => {
  if (observer) observer.disconnect()
})
</script>

<style scoped>
.news-list-wrap {
  max-width: 1280px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.page-head__title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-text);
}
.page-head__sub {
  margin-top: 4px;
  color: var(--color-text-muted);
  font-size: 14px;
}

.filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  padding: 10px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  margin-bottom: 20px;
}
.chip {
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  transition: all var(--t-fast);
}
.chip:hover {
  border-color: var(--color-brand-sky);
  color: var(--color-brand-sky);
}
.chip--active {
  background: var(--color-brand-red);
  border-color: var(--color-brand-red);
  color: #fff;
}
.chip--active:hover {
  background: var(--color-brand-red-hover);
  border-color: var(--color-brand-red-hover);
  color: #fff;
}


.news-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
}

@media (max-width: 1100px) {
  .news-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .news-grid { grid-template-columns: 1fr; }
}

.news-sentinel {
  height: 1px;
  margin-top: 24px;
}

.news-grid--more {
  margin-top: 20px;
}
</style>
