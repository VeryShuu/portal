<template>
  <div class="detail-wrap">
      <n-spin v-if="loading" style="margin:40px auto;display:block" />

      <template v-else-if="news">
        <article class="article">
          <header class="article__head" :class="{ 'article__head--gradient': !news.cover_image_url }" :style="headFallbackStyle">
            <img
              v-if="news.cover_image_url"
              :src="news.cover_image_url"
              :alt="news.title"
              class="article__head-img"
              :style="{ objectPosition: focalObjectPosition }"
            />
            <div class="article__head-overlay" />
            <div class="article__head-inner">
              <div class="article__badges">
                <span v-if="news.is_pinned" class="badge badge--pinned">
                  <n-icon size="12"><StarOutline /></n-icon>
                  {{ t('news.pinned') }}
                </span>
                <span v-for="cat in news.categories" :key="cat" class="badge" :class="categoryClassFor(cat)">
                  {{ cat }}
                </span>
                <span v-if="news.status !== 'published'" class="badge badge--draft">
                  {{ t(`news.status.${news.status}`, news.status) }}
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
              <template #icon><n-icon><LinkOutline /></n-icon></template>
              {{ copied ? t('common.copied') : t('common.copyLink') }}
            </n-button>

            <n-dropdown
              trigger="click"
              :options="exportOptions"
              @select="handleExport"
            >
              <n-button size="small" tertiary>
                <template #icon><n-icon><DownloadOutline /></n-icon></template>
                {{ t('news.export.button') }}
              </n-button>
            </n-dropdown>

            <n-button v-if="auth.isEditor" size="small" type="primary" ghost @click="router.push(`/news/${news.id}/edit`)">
              <template #icon><n-icon><CreateOutline /></n-icon></template>
              {{ t('common.edit') }}
            </n-button>

            <n-button v-if="auth.isEditor" size="small" type="error" ghost :loading="deleting" @click="confirmDelete">
              <template #icon><n-icon><TrashOutline /></n-icon></template>
              {{ t('common.delete') }}
            </n-button>
          </div>

          <div class="news-body" v-html="renderedBody" />

          <NewsGalleryViewer :images="gallery ?? []" />
          <NewsAttachmentsViewer :attachments="attachments ?? []" />
        </article>
      </template>

      <n-result v-else status="404" :title="t('errors.notFound.title')" :description="t('errors.notFound.description')">
        <template #footer>
          <n-button @click="router.push('/news')">{{ t('common.back') }}</n-button>
        </template>
      </n-result>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NSpin, NButton, NDropdown, NResult, NIcon, useMessage } from 'naive-ui'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import { EyeOutline, StarOutline, LinkOutline, CreateOutline, DownloadOutline, TrashOutline } from '@vicons/ionicons5'
import { mdUnsafe as md } from '@/utils/markdown'
import { sanitizeHtmlAllowIframe } from '@/utils/sanitize'
import { useBrandingStore } from '../stores/branding'
import { useLayoutHeader } from '../composables/useLayoutHeader'
import NewsGalleryViewer from '../components/NewsGalleryViewer.vue'
import NewsAttachmentsViewer from '../components/NewsAttachmentsViewer.vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useAuthStore } from '../stores/auth'
import { deleteNews } from '../api/news'
import { useNewsDetailQuery, useNewsGalleryQuery, useNewsAttachmentsQuery } from '../queries/news'
import { queryKeys } from '../queries/keys'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const brandingStore = useBrandingStore()
const { t, locale } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()
const { setHeader, clearHeader } = useLayoutHeader()
const queryClient = useQueryClient()

const newsId = computed(() => route.params.id as string)

const { data: news, isLoading: loading } = useNewsDetailQuery(newsId)

const { data: gallery } = useNewsGalleryQuery(newsId)

const { data: attachments } = useNewsAttachmentsQuery(newsId)

watch(news, (n) => {
  if (n) setHeader(n.title)
})

const copied = ref(false)
const deleting = ref(false)

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

const exportOptions = computed(() => [
  { label: t('news.export.markdown'), key: 'markdown' },
  { label: t('news.export.html'), key: 'html' },
  { label: t('news.export.pdf'), key: 'pdf' },
])

const renderedBody = computed(() => {
  if (!news.value) return ''
  const raw = md.render(news.value.body)
  const allowedOrigins: string[] = brandingStore.settings.allowed_iframe_origins ?? []
  return sanitizeHtmlAllowIframe(raw, allowedOrigins)
})

const formattedDate = computed(() => {
  if (!news.value) return ''
  const d = news.value.published_at ?? news.value.created_at
  const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
  return new Date(d).toLocaleDateString(lang, { day: 'numeric', month: 'long', year: 'numeric' })
})

const gradientPalette = [
  'linear-gradient(135deg, #0b2a4a 0%, #143a66 100%)',
  'linear-gradient(135deg, #143a66 0%, #4a90c4 100%)',
  'linear-gradient(135deg, #4a1820 0%, #d8262c 100%)',
  'linear-gradient(135deg, #1f4e85 0%, #6faed8 100%)',
  'linear-gradient(135deg, #0b2a4a 0%, #4a90c4 100%)',
]

const headFallbackStyle = computed(() => {
  if (news.value?.cover_image_url) return {}
  const id = news.value?.id ?? ''
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash + id.charCodeAt(i)) % gradientPalette.length
  return { background: gradientPalette[hash] }
})

const focalObjectPosition = computed(() => {
  const fp = news.value?.cover_focal_point
  if (fp === 'top') return '50% 0%'
  if (fp === 'bottom') return '50% 100%'
  return '50% 50%'
})

function categoryClassFor(cat: string): string {
  const c = cat.toLowerCase()
  if (c.includes('hr') || c.includes('кадр')) return 'badge--hr'
  if (c.includes('it') || c.includes('ит') || c.includes('техн')) return 'badge--it'
  if (c.includes('fin') || c.includes('фин')) return 'badge--finance'
  return 'badge--general'
}

function handleExport(key: string) {
  if (!news.value) return
  const id = news.value.id
  const url = `${BASE_URL}/news/${id}/export/${key}`
  const a = document.createElement('a')
  a.href = url
  a.target = '_blank'
  a.rel = 'noopener noreferrer'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

async function confirmDelete() {
  if (!news.value) return
  const ok = await confirm({
    title: t('news.delete.confirmTitle'),
    content: t('news.delete.confirmText', { title: news.value.title }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (ok) await handleDelete()
}

async function handleDelete() {
  if (!news.value) return
  deleting.value = true
  const id = news.value.id
  try {
    await deleteNews(id)
    queryClient.removeQueries({ queryKey: queryKeys.news.detail(id) })
    queryClient.removeQueries({ queryKey: queryKeys.news.gallery(id) })
    queryClient.removeQueries({ queryKey: queryKeys.news.attachments(id) })
    queryClient.invalidateQueries({ queryKey: queryKeys.news.all })
    message.success(t('news.delete.success'))
    router.push('/news')
  } catch {
    message.error(t('errors.generic'))
  } finally {
    deleting.value = false
  }
}

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

onBeforeUnmount(() => {
  clearHeader()
})
</script>

<style scoped>
.detail-wrap {
  max-width: 860px;
  margin: 0 auto;
}

.article__head {
  position: relative;
  height: clamp(220px, 28vw, 340px);
  border-radius: var(--radius-xl);
  overflow: hidden;
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  color: #fff;
  margin-bottom: 16px;
}
.article__head-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
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
.news-body :deep(.iframe-wrapper) {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  margin: 16px 0;
  border-radius: var(--radius-md);
  overflow: hidden;
}
.news-body :deep(.iframe-wrapper iframe) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: none;
}
.news-body :deep(blockquote) {
  border-left: 3px solid var(--color-brand-red);
  padding-left: 16px;
  margin-left: 0;
  color: var(--color-text-muted);
  font-style: italic;
}

@media (max-width: 720px) {
  .article__head { padding: 20px; height: clamp(180px, 48vw, 240px); }
  .article__title { font-size: 24px; }
}
</style>
