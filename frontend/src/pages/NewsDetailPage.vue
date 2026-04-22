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
        <article class="article">
          <header class="article__head" :style="coverStyle">
            <div class="article__head-overlay" />
            <div class="article__head-inner">
              <div class="article__badges">
                <span v-if="news.is_pinned" class="badge badge--pinned">
                  <n-icon size="12"><StarOutline /></n-icon>
                  {{ t('news.pinned') }}
                </span>
                <span v-if="news.category" class="badge" :class="categoryClass">
                  {{ news.category }}
                </span>
                <span v-if="news.status !== 'published'" class="badge badge--draft">
                  {{ t(`news.status.${news.status}`) }}
                </span>
              </div>
              <h1 class="article__title">{{ news.title }}</h1>
              <div class="article__meta">
                <span>{{ formattedDate }}</span>
                <span class="article__views">
                  <n-icon size="14"><EyeOutline /></n-icon>
                  {{ news.view_count }}
                </span>
              </div>
            </div>
          </header>

          <div class="article__actions">
            <n-button size="small" tertiary @click="copyLink">
              <template #icon>
                <n-icon><LinkOutline /></n-icon>
              </template>
              {{ copied ? t('common.copied') : t('common.copyLink') }}
            </n-button>
            <n-button v-if="auth.isEditor" size="small" type="primary" ghost @click="router.push(`/news/${news.id}/edit`)">
              <template #icon>
                <n-icon><CreateOutline /></n-icon>
              </template>
              {{ t('common.edit') }}
            </n-button>
          </div>

          <div class="news-body" v-html="renderedBody" />
        </article>
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
import { NSpin, NButton, NBreadcrumb, NBreadcrumbItem, NResult, NIcon, useMessage } from 'naive-ui'
import { EyeOutline, StarOutline, LinkOutline, CreateOutline } from '@vicons/ionicons5'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import AppLayout from '../components/AppLayout.vue'
import { useAuthStore } from '../stores/auth'
import { fetchNewsById, type News } from '../api/news'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { t, locale } = useI18n()
const message = useMessage()
const md = new MarkdownIt({ html: false, linkify: true, typographer: true })

const loading = ref(true)
const news = ref<News | null>(null)
const copied = ref(false)

const renderedBody = computed(() => {
  if (!news.value) return ''
  const body = news.value.body
  const raw = body.trimStart().startsWith('<') ? body : md.render(body)
  return DOMPurify.sanitize(raw, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'style'],
  })
})

const formattedDate = computed(() => {
  if (!news.value) return ''
  const d = news.value.published_at ?? news.value.created_at
  const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
  return new Date(d).toLocaleDateString(lang, { day: 'numeric', month: 'long', year: 'numeric' })
})

const coverStyle = computed(() => {
  const palette = [
    'linear-gradient(135deg, #0b2a4a 0%, #143a66 100%)',
    'linear-gradient(135deg, #143a66 0%, #4a90c4 100%)',
    'linear-gradient(135deg, #4a1820 0%, #d8262c 100%)',
    'linear-gradient(135deg, #1f4e85 0%, #6faed8 100%)',
    'linear-gradient(135deg, #0b2a4a 0%, #4a90c4 100%)',
  ]
  const id = news.value?.id ?? ''
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash + id.charCodeAt(i)) % palette.length
  return { background: palette[hash] }
})

const categoryClass = computed(() => {
  const c = (news.value?.category ?? '').toLowerCase()
  if (c.includes('hr') || c.includes('кадр')) return 'badge--hr'
  if (c.includes('it') || c.includes('ит') || c.includes('техн')) return 'badge--it'
  if (c.includes('fin') || c.includes('фин')) return 'badge--finance'
  return 'badge--general'
})

async function copyLink() {
  try {
    await navigator.clipboard.writeText(window.location.href)
    copied.value = true
    message.success(t('common.copied'))
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    message.error(t('common.copyFailed'))
  }
}

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
.detail-wrap {
  max-width: 860px;
  margin: 0 auto;
}

.article__head {
  position: relative;
  min-height: 280px;
  border-radius: var(--radius-xl);
  overflow: hidden;
  padding: 28px 32px 28px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  color: #fff;
  margin-bottom: 16px;
  background-size: cover;
  background-position: center;
}
.article__head-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(11,42,74,0) 0%, rgba(11,42,74,0.7) 100%);
}
.article__head-inner {
  position: relative;
  z-index: 1;
}
.article__badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.article__title {
  margin: 0 0 12px;
  font-size: 30px;
  font-weight: 800;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: #fff;
  text-shadow: 0 2px 12px rgba(0,0,0,0.35);
}
.article__meta {
  display: flex;
  gap: 16px;
  align-items: center;
  font-size: 13px;
  color: rgba(255,255,255,0.88);
}
.article__views {
  display: flex;
  align-items: center;
  gap: 4px;
}

.article__actions {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.9);
  color: var(--color-brand-navy);
}
.badge--pinned { background: var(--color-brand-red); color: #fff; }
.badge--draft  { background: rgba(255,255,255,0.22); color: #fff; border: 1px solid rgba(255,255,255,0.35); }
.badge--hr       { background: var(--badge-hr-bg); color: var(--badge-hr-fg); }
.badge--it       { background: var(--badge-it-bg); color: var(--badge-it-fg); }
.badge--finance  { background: var(--badge-finance-bg); color: var(--badge-finance-fg); }
.badge--general  { background: var(--badge-general-bg); color: var(--badge-general-fg); }

.news-body {
  font-size: 16px;
  line-height: 1.75;
  color: var(--color-text);
}
.news-body :deep(h1),
.news-body :deep(h2),
.news-body :deep(h3) {
  letter-spacing: -0.01em;
  color: var(--color-text);
  margin-top: 1.6em;
  margin-bottom: 0.5em;
}
.news-body :deep(img) { max-width: 100%; border-radius: var(--radius-md); }
.news-body :deep(a) { color: var(--color-brand-sky); }
.news-body :deep(a:hover) { color: var(--color-brand-navy); }
.news-body :deep(pre) {
  background: var(--color-bg-muted);
  padding: 14px 16px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  border: 1px solid var(--color-border);
}
.news-body :deep(blockquote) {
  border-left: 3px solid var(--color-brand-red);
  padding-left: 16px;
  margin-left: 0;
  color: var(--color-text-muted);
  font-style: italic;
}

@media (max-width: 720px) {
  .article__head { padding: 20px; min-height: 200px; }
  .article__title { font-size: 24px; }
}
</style>
