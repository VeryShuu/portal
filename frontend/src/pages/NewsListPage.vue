<template>
  <AppLayout>
    <template #header-title>
      <span>{{ t('news.title') }}</span>
    </template>

    <div class="news-list-wrap">
      <div class="toolbar">
        <n-select
          v-if="auth.isEditor"
          v-model:value="statusFilter"
          :options="statusOptions"
          size="small"
          style="width:140px"
          clearable
          :placeholder="t('common.filter')"
        />
        <n-button v-if="auth.isEditor" type="primary" @click="router.push('/news/create')">
          + {{ t('news.create.title') }}
        </n-button>
      </div>

      <n-spin v-if="loading" />
      <template v-else>
        <n-grid v-if="news.length" :x-gap="16" :y-gap="16" :cols="3" responsive="screen" item-responsive>
          <n-grid-item v-for="item in news" :key="item.id" span="3 m:1">
            <NewsCard :news="item" @click="id => router.push(`/news/${id}`)" />
          </n-grid-item>
        </n-grid>
        <n-empty v-else :description="t('news.noNews')" />

        <n-pagination
          v-if="total > pageSize"
          v-model:page="page"
          :page-count="Math.ceil(total / pageSize)"
          :page-size="pageSize"
          style="margin-top:24px;justify-content:center"
        />
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NSpin, NEmpty, NGrid, NGridItem, NPagination, NSelect } from 'naive-ui'
import AppLayout from '../components/AppLayout.vue'
import NewsCard from '../components/NewsCard.vue'
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

const statusOptions = [
  { label: t('news.status.draft'), value: 'draft' },
  { label: t('news.status.published'), value: 'published' },
  { label: t('news.status.archived'), value: 'archived' },
]

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
.news-list-wrap { max-width: 1200px; margin: 0 auto; }
.toolbar { display: flex; gap: 12px; align-items: center; justify-content: flex-end; margin-bottom: 16px; }
</style>
