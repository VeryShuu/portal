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
          v-for="chip in chips"
          :key="chip.key"
          type="button"
          class="chip"
          :class="{ 'chip--active': activeChip === chip.key }"
          @click="activeChip = chip.key"
        >
          {{ chip.label }}
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

        <n-pagination
          v-if="total > pageSize"
          v-model:page="page"
          :page-count="Math.ceil(total / pageSize)"
          :page-size="pageSize"
          style="margin-top:28px;justify-content:center"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NPagination, NSelect } from 'naive-ui'
import NewsCard from '../components/NewsCard.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import { useAuthStore } from '../stores/auth'
import { fetchNewsList, type News } from '../api/news'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

const loading = ref(true)
const news = ref<News[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 24
const statusFilter = ref<string | null>(null)
const activeChip = ref<string>('all')

const chips = computed(() => [
  { key: 'all', label: t('news.filters.all') },
  { key: 'pinned', label: t('news.filters.pinned') },
  { key: 'hr', label: 'HR' },
  { key: 'it', label: 'IT' },
  { key: 'finance', label: t('news.filters.finance') },
  { key: 'general', label: t('news.filters.general') },
])

const statusOptions = [
  { label: t('news.status.draft'), value: 'draft' },
  { label: t('news.status.published'), value: 'published' },
  { label: t('news.status.archived'), value: 'archived' },
]

const filtered = computed(() => {
  if (activeChip.value === 'all') return news.value
  if (activeChip.value === 'pinned') return news.value.filter((n) => n.is_pinned)
  return news.value.filter((n) => {
    const c = (n.category ?? '').toLowerCase()
    if (activeChip.value === 'hr') return c.includes('hr') || c.includes('кадр')
    if (activeChip.value === 'it') return c.includes('it') || c.includes('ит') || c.includes('техн')
    if (activeChip.value === 'finance') return c.includes('fin') || c.includes('фин')
    if (activeChip.value === 'general') return !c || c.includes('общ') || c.includes('general')
    return true
  })
})

async function load() {
  loading.value = true
  try {
    const res = await fetchNewsList({
      page: page.value,
      page_size: pageSize,
      ...(statusFilter.value ? { status: statusFilter.value } : {}),
    })
    news.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([page, statusFilter], () => load())
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
</style>
