<template>
  <AppLayout>
    <template #header-title>
      <n-breadcrumb>
        <n-breadcrumb-item @click="router.push('/news')">{{ t('nav.news') }}</n-breadcrumb-item>
        <n-breadcrumb-item>{{ news?.title ?? '...' }}</n-breadcrumb-item>
      </n-breadcrumb>
    </template>

    <div class="detail-wrap">
      <n-spin v-if="loading" style="margin:40px auto;display:block" />

      <template v-else-if="news">
        <div class="detail-header">
          <div class="tags">
            <n-tag v-if="news.is_pinned" type="warning" size="small" round>{{ t('news.pinned') }}</n-tag>
            <n-tag v-if="news.category" size="small" round>{{ news.category }}</n-tag>
            <span class="status-badge" :class="news.status">{{ t(`news.status.${news.status}`) }}</span>
          </div>
          <h1>{{ news.title }}</h1>
          <div class="meta">
            <span>{{ formattedDate }}</span>
            <span class="views">
              <n-icon size="14"><EyeOutline /></n-icon>
              {{ news.view_count }}
            </span>
            <n-button v-if="auth.isEditor" size="small" @click="router.push(`/news/${news.id}/edit`)">
              {{ t('common.edit') }}
            </n-button>
          </div>
        </div>

        <n-divider />

        <div class="news-body" v-html="renderedBody" />
      </template>

      <n-result v-else status="404" :title="t('errors.notFound.title')" :description="t('errors.notFound.description')">
        <template #footer>
          <n-button @click="router.push('/news')">{{ t('common.back') }}</n-button>
        </template>
      </n-result>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NTag, NSpin, NButton, NBreadcrumb, NBreadcrumbItem, NDivider, NResult, NIcon } from 'naive-ui'
import { EyeOutline } from '@vicons/ionicons5'
import MarkdownIt from 'markdown-it'
import AppLayout from '../components/AppLayout.vue'
import { useAuthStore } from '../stores/auth'
import { fetchNewsById, type News } from '../api/news'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()
const md = new MarkdownIt({ html: false, linkify: true, typographer: true })

const loading = ref(true)
const news = ref<News | null>(null)

const renderedBody = computed(() => {
  if (!news.value) return ''
  const body = news.value.body
  return body.startsWith('<') ? body : md.render(body)
})

const formattedDate = computed(() => {
  if (!news.value) return ''
  const d = news.value.published_at ?? news.value.created_at
  return new Date(d).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
})

onMounted(async () => {
  try {
    news.value = await fetchNewsById(route.params.id as string)
  } catch {
    news.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.detail-wrap { max-width: 860px; margin: 0 auto; }
.detail-header { margin-bottom: 8px; }
.detail-header h1 { margin: 8px 0; font-size: 26px; line-height: 1.3; }
.tags { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; }
.status-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
}
.status-badge.published { background: #18a05820; color: #18a058; }
.status-badge.draft     { background: #88888820; color: #888; }
.status-badge.archived  { background: #d0302030; color: #d03020; }
.meta { display: flex; gap: 16px; align-items: center; font-size: 13px; color: #999; }
.views { display: flex; align-items: center; gap: 4px; }
.news-body { font-size: 15px; line-height: 1.7; }
.news-body :deep(img) { max-width: 100%; border-radius: 8px; }
.news-body :deep(a) { color: #18a058; }
.news-body :deep(pre) { background: #f5f5f5; padding: 12px; border-radius: 6px; overflow-x: auto; }
</style>
