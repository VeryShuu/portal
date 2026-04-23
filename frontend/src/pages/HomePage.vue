<template>
  <AppLayout>
    <template #header-title>
      <span>{{ t('nav.home') }}</span>
    </template>

    <div class="home">
      <HeroBlock />

      <div class="home__grid">
        <!-- Main column -->
        <div class="home__main">
          <!-- Featured (pinned) news -->
          <section v-if="pinned.length || loadingNews" class="section">
            <div class="section__header">
              <h2 class="section__title">{{ t('home.sections.featured') }}</h2>
            </div>

            <div v-if="loadingNews" class="featured-skeleton">
              <SkeletonCard variant="news" />
            </div>
            <template v-else>
              <NewsCard
                v-for="item in pinned"
                :key="item.id"
                :news="item"
                featured
                class="featured-card"
                @click="goToNews"
              />
            </template>
          </section>

          <!-- Latest news -->
          <section class="section">
            <div class="section__header">
              <h2 class="section__title">{{ t('home.sections.latest') }}</h2>
              <div class="section__actions">
                <n-button
                  v-if="auth.isEditor"
                  type="primary"
                  size="small"
                  @click="router.push('/news/create')"
                >
                  + {{ t('news.create.title') }}
                </n-button>
                <n-button
                  text
                  type="primary"
                  size="small"
                  @click="router.push('/news')"
                >
                  {{ t('home.viewAll') }}
                  <template #icon>
                    <n-icon><ChevronForwardOutline /></n-icon>
                  </template>
                </n-button>
              </div>
            </div>

            <div v-if="loadingNews" class="news-grid">
              <SkeletonCard variant="news" v-for="i in 4" :key="`sk-${i}`" />
            </div>
            <div v-else-if="regular.length" class="news-grid">
              <NewsCard v-for="item in regular" :key="item.id" :news="item" @click="goToNews" />
            </div>
            <EmptyState
              v-else
              variant="news"
              :title="t('news.noNews')"
            />
          </section>
        </div>

        <!-- Side column -->
        <aside class="home__side">
          <section class="widget">
            <div class="widget__header">
              <h3 class="widget__title">{{ t('home.sections.services') }}</h3>
              <n-button text size="tiny" @click="router.push('/links')">
                {{ t('common.all') }}
              </n-button>
            </div>
            <div v-if="linksStore.loadingLinks" class="widget__body widget__body--loading">
              <div class="quick-skeleton" v-for="i in 6" :key="`qsk-${i}`" />
            </div>
            <div v-else-if="topLinks.length" class="quick-grid">
              <button
                v-for="link in topLinks"
                :key="link.id"
                class="quick-tile"
                type="button"
                :title="link.title"
                @click="linksStore.openLink(link)"
              >
                <div class="quick-tile__icon">
                  <img v-if="link.icon_url" :src="link.icon_url" :alt="link.title" />
                  <span v-else class="quick-tile__letter">{{ link.title.charAt(0).toUpperCase() }}</span>
                </div>
                <span class="quick-tile__name">{{ link.title }}</span>
              </button>
            </div>
            <EmptyState
              v-else
              compact
              variant="default"
              :title="t('links.empty')"
            />
          </section>

          <section class="widget">
            <div class="widget__header">
              <h3 class="widget__title">{{ t('home.sections.bookmarks') }}</h3>
              <n-button text size="tiny" @click="showAddBookmark = true">
                + {{ t('bookmarks.add') }}
              </n-button>
            </div>
            <div v-if="linksStore.loadingBookmarks" class="widget__body widget__body--loading">
              <div class="bookmark-skeleton" v-for="i in 3" :key="`bsk-${i}`" />
            </div>
            <ul v-else-if="linksStore.bookmarks.length" class="bookmarks-list">
              <li
                v-for="bm in linksStore.bookmarks"
                :key="bm.id"
                class="bookmark-row"
              >
                <img
                  class="bookmark-row__favicon"
                  :src="faviconUrl(bm.url)"
                  alt=""
                  loading="lazy"
                  @error="onFaviconError"
                />
                <a :href="bm.url" target="_blank" rel="noopener" class="bookmark-row__link">
                  {{ bm.title }}
                </a>
                <button
                  class="bookmark-row__del"
                  type="button"
                  :aria-label="t('bookmarks.remove')"
                  @click.prevent="linksStore.removeBookmark(bm.id)"
                >
                  ×
                </button>
              </li>
            </ul>
            <EmptyState
              v-else
              compact
              variant="bookmark"
              :title="t('bookmarks.empty')"
            >
              <template #action>
                <n-button size="small" type="primary" ghost @click="showAddBookmark = true">
                  + {{ t('home.createFirstBookmark') }}
                </n-button>
              </template>
            </EmptyState>
          </section>
        </aside>
      </div>
    </div>

    <!-- Add bookmark modal -->
    <n-modal v-model:show="showAddBookmark" preset="dialog" :title="t('bookmarks.add')" :positive-text="t('common.save')" :negative-text="t('common.cancel')" @positive-click="submitBookmark" @negative-click="showAddBookmark = false">
      <n-form>
        <n-form-item :label="t('bookmarks.titleField')">
          <n-input v-model:value="newBmTitle" :placeholder="t('bookmarks.titlePlaceholder')" />
        </n-form-item>
        <n-form-item label="URL">
          <n-input v-model:value="newBmUrl" placeholder="https://..." />
        </n-form-item>
      </n-form>
    </n-modal>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NButton, NModal, NForm, NFormItem, NInput, NIcon,
} from 'naive-ui'
import { ChevronForwardOutline } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import HeroBlock from '../components/HeroBlock.vue'
import NewsCard from '../components/NewsCard.vue'
import EmptyState from '../components/EmptyState.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import { useAuthStore } from '../stores/auth'
import { useLinksStore } from '../stores/links'
import { fetchNewsList, type News } from '../api/news'

const router = useRouter()
const auth = useAuthStore()
const linksStore = useLinksStore()
const { t } = useI18n()

const loadingNews = ref(true)
const news = ref<News[]>([])
const totalNews = ref(0)
const pageSize = 9

const showAddBookmark = ref(false)
const newBmTitle = ref('')
const newBmUrl = ref('')

const pinned = computed(() => news.value.filter(n => n.is_pinned).slice(0, 1))
const regular = computed(() => news.value.filter(n => !n.is_pinned))
const topLinks = computed(() => linksStore.links.slice(0, 9))



onMounted(async () => {
  try {
    const res = await fetchNewsList({ page: 1, page_size: pageSize })
    news.value = res.items
    totalNews.value = res.total
  } finally {
    loadingNews.value = false
  }
  linksStore.loadLinks()
  linksStore.loadBookmarks()
})

function goToNews(id: string) {
  router.push(`/news/${id}`)
}

async function submitBookmark() {
  if (!newBmTitle.value || !newBmUrl.value) return
  await linksStore.addBookmark({ title: newBmTitle.value, url: newBmUrl.value })
  newBmTitle.value = ''
  newBmUrl.value = ''
  showAddBookmark.value = false
}

function faviconUrl(url: string): string {
  try {
    const u = new URL(url)
    return `${u.origin}/favicon.ico`
  } catch {
    return ''
  }
}

function onFaviconError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.visibility = 'hidden'
}
</script>

<style scoped>
.home {
  max-width: 1280px;
  margin: 0 auto;
}
.home__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 24px;
  align-items: flex-start;
}
.home__main { min-width: 0; }
.home__side {
  display: flex;
  flex-direction: column;
  gap: 20px;
  position: sticky;
  top: 16px;
}

/* === Section === */
.section { margin-bottom: 32px; }
.section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  gap: 12px;
  flex-wrap: wrap;
}
.section__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--color-text);
}
.section__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* === News grid === */
.news-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.featured-card,
.featured-skeleton { margin-bottom: 4px; }

/* === Widgets === */
.widget {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px 18px 12px;
  box-shadow: var(--shadow-sm);
}
.widget__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.widget__title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}
.widget__body--loading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Quick services grid */
.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.quick-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 10px 6px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: inherit;
  transition: background var(--t-fast), border-color var(--t-fast), transform var(--t-fast);
}
.quick-tile:hover {
  background: var(--color-bg-muted);
  border-color: var(--color-border);
  transform: translateY(-1px);
}
.quick-tile__icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--color-brand-ice);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.quick-tile__icon img { width: 26px; height: 26px; object-fit: contain; }
.quick-tile__letter {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-brand-navy);
}
.quick-tile__name {
  font-size: 11px;
  text-align: center;
  color: var(--color-text);
  line-height: 1.2;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 80px;
}
.quick-skeleton {
  height: 68px;
  border-radius: var(--radius-md);
  background: var(--color-bg-muted);
  animation: pulse 1.4s ease-in-out infinite;
}

/* Bookmarks */
.bookmarks-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.bookmark-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  border-radius: var(--radius-sm);
  transition: background var(--t-fast);
}
.bookmark-row:hover { background: var(--color-bg-muted); }
.bookmark-row__favicon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  border-radius: 3px;
  background: var(--color-bg-muted);
}
.bookmark-row__link {
  flex: 1;
  font-size: 13px;
  color: var(--color-text);
  text-decoration: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bookmark-row__link:hover {
  color: var(--color-brand-sky);
  text-decoration: underline;
}
.bookmark-row__del {
  background: transparent;
  border: none;
  color: var(--color-text-subtle);
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  opacity: 0;
  transition: opacity var(--t-fast), color var(--t-fast), background var(--t-fast);
}
.bookmark-row:hover .bookmark-row__del { opacity: 1; }
.bookmark-row__del:hover { color: var(--color-brand-red); background: var(--color-brand-red-soft); }
.bookmark-skeleton {
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-muted);
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* === Responsive === */
@media (max-width: 1100px) {
  .home__grid { grid-template-columns: 1fr; }
  .home__side { position: static; }
}
@media (max-width: 720px) {
  .news-grid { grid-template-columns: 1fr; }
}
</style>
