<template>
  <AppLayout>
    <template #header-title>
      <span>{{ t('home.welcome', { name: auth.user?.full_name ?? '' }) }}</span>
    </template>

    <div class="home-wrap">
      <div class="news-section">
        <div class="section-header">
          <h2>{{ t('nav.news') }}</h2>
          <n-button v-if="auth.isEditor" type="primary" size="small" @click="router.push('/news/create')">
            + {{ t('news.create.title') }}
          </n-button>
        </div>

        <n-spin v-if="loading" />
        <template v-else>
          <div v-if="pinned.length" class="pinned-news">
            <NewsCard v-for="item in pinned" :key="item.id" :news="item" @click="goToNews" />
          </div>
          <n-grid v-if="regular.length" :x-gap="16" :y-gap="16" :cols="2" responsive="screen" item-responsive>
            <n-grid-item v-for="item in regular" :key="item.id" span="2 s:1">
              <NewsCard :news="item" @click="goToNews" />
            </n-grid-item>
          </n-grid>
          <n-empty v-if="!pinned.length && !regular.length" :description="t('news.noNews')" />

          <div v-if="total > pageSize" style="margin-top:16px;text-align:center">
            <n-button @click="router.push('/news')">{{ t('common.total', { count: total }) }}</n-button>
          </div>
        </template>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NSpin, NEmpty, NGrid, NGridItem } from 'naive-ui'
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
const pageSize = 10

const pinned = computed(() => news.value.filter(n => n.is_pinned))
const regular = computed(() => news.value.filter(n => !n.is_pinned))

onMounted(async () => {
  try {
    const res = await fetchNewsList({ page: 1, page_size: pageSize })
    news.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
})

function goToNews(id: string) {
  router.push(`/news/${id}`)
}
</script>

<style scoped>
.home-wrap {
  max-width: 1200px;
  margin: 0 auto;
}
.news-section {
  margin-bottom: 32px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.section-header h2 {
  margin: 0;
  font-size: 20px;
}
.pinned-news {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
