<template>
  <div class="news-list-wrap u-page-wrap">
    <div class="page-head u-page-head">
      <div class="page-head__left">
        <h1 class="u-page-head__title">
          {{ t('news.title') }}
        </h1>
        <div class="u-page-head__sub">
          {{ t('news.pageSub') }}
        </div>
      </div>
      <div class="page-head__right u-page-head__actions">
        <n-button
          v-if="auth.isEditor"
          size="medium"
          quaternary
          circle
          :title="t('news.filters.trash')"
          :type="activeChip === 'trash' ? 'primary' : 'default'"
          @click="activeChip = activeChip === 'trash' ? 'all' : 'trash'"
        >
          <template #icon>
            <n-icon :component="TrashBinOutline" />
          </template>
        </n-button>
        <n-button
          v-if="auth.isEditor"
          size="medium"
          @click="manage.open('categories')"
        >
          <template #icon>
            <n-icon :component="PricetagsOutline" />
          </template>
          {{ t('admin.tabs.newsCategories') }}
        </n-button>
        <n-button
          v-if="auth.isEditor"
          type="primary"
          size="medium"
          @click="router.push('/news/create')"
        >
          + {{ t('news.create.title') }}
        </n-button>
      </div>
    </div>

    <div
      class="filters"
      role="toolbar"
      :aria-label="t('news.filters.aria')"
    >
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
        :key="cat.name"
        type="button"
        class="chip"
        :class="{ 'chip--active': activeChip === `cat:${cat.name}` }"
        :style="activeChip === `cat:${cat.name}` ? { background: cat.color, borderColor: cat.color, color: chipTextColor(cat.color) } : {}"
        @click="activeChip = `cat:${cat.name}`"
      >
        {{ cat.name }}
      </button>

      <n-select
        v-if="auth.isEditor && activeChip !== 'trash'"
        v-model:value="statusFilter"
        :options="statusOptions"
        size="small"
        style="width:160px;margin-left:auto"
        clearable
        :placeholder="t('news.filters.status')"
      />
    </div>


    <Suspense v-if="activeChip === 'trash' && auth.isEditor">
      <TrashNewsTab />
    </Suspense>

    <template v-else>
      <div
        v-if="loading"
        class="news-grid"
      >
        <SkeletonCard
          v-for="i in 6"
          :key="`sk-${i}`"
          variant="news"
        />
      </div>
      <template v-else>
        <div
          v-if="filtered.length"
          class="news-grid"
        >
          <NewsCard
            v-for="item in filtered"
            :key="item.id"
            :news="item"
            :categories-map="categoriesMap"
            @click="id => router.push(`/news/${id}`)"
          />
        </div>
        <EmptyState
          v-else
          variant="news"
          :title="t('news.noNews')"
          :description="t('news.noNewsHint')"
        />

        <div
          ref="sentinel"
          class="news-sentinel"
        />
        <div
          v-if="loadingMore"
          class="news-grid news-grid--more"
        >
          <SkeletonCard
            v-for="i in 3"
            :key="`sk-more-${i}`"
            variant="news"
          />
        </div>
      </template>
    </template>

    <n-drawer
      :show="manage.is('categories') && auth.isEditor"
      :width="640"
      placement="right"
      :on-update:show="(v: boolean) => { if (!v) manage.close() }"
    >
      <n-drawer-content
        :title="t('admin.tabs.newsCategories')"
        closable
      >
        <Suspense>
          <NewsCategoriesTab />
        </Suspense>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted, computed, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NSelect, NIcon, NDrawer, NDrawerContent } from 'naive-ui'
import { TrashBinOutline, PricetagsOutline } from '@vicons/ionicons5'
import NewsCard from '../components/news/NewsCard.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import { useAuthStore } from '../stores/auth'
import { fetchNewsList, type News } from '../api/news'
import { useNewsListQuery, useNewsCategoriesQuery } from '../queries/news'
import { useManageDrawer } from '../composables/useManageDrawer'

const TrashNewsTab = defineAsyncComponent(() => import('../components/trash/TrashNewsTab.vue'))
const NewsCategoriesTab = defineAsyncComponent(() => import('./admin/tabs/NewsCategoriesTab.vue'))
const manage = useManageDrawer(['categories'])

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

const { data: categoriesData } = useNewsCategoriesQuery()
const categories = computed(() => categoriesData.value ?? [])

const categoriesMap = computed<Record<string, string>>(() =>
  Object.fromEntries(categories.value.map(c => [c.name, c.color]))
)

function chipTextColor(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.55 ? '#1a1a1a' : '#ffffff'
}

const statusOptions = [
  { label: t('news.status.draft'), value: 'draft' },
  { label: t('news.status.published'), value: 'published' },
  { label: t('news.status.archived'), value: 'archived' },
]

const newsParams = computed(() => ({
  page: 1,
  page_size: pageSize,
  ...(statusFilter.value ? { status: statusFilter.value } : {}),
}))

const { data: newsPage, isLoading: loading } = useNewsListQuery(newsParams)

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
    return accumulatedNews.value.filter((n) => n.categories.some((c: string) => c.toLowerCase() === target))
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

onUnmounted(() => {
  if (observer) observer.disconnect()
})
</script>

<style scoped>
.page-head {
  margin-bottom: 20px;
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
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.news-sentinel {
  height: 1px;
  margin-top: 24px;
}

.news-grid--more {
  margin-top: 20px;
}
</style>
