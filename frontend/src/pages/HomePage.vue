<template>
  <AppLayout>
    <template #header-title>
      <span>{{ t('home.welcome', { name: auth.user?.full_name ?? '' }) }}</span>
    </template>

    <div class="home-wrap">
      <div class="main-col">
        <div class="news-section">
          <div class="section-header">
            <h2>{{ t('nav.news') }}</h2>
            <n-button v-if="auth.isEditor" type="primary" size="small" @click="router.push('/news/create')">
              + {{ t('news.create.title') }}
            </n-button>
          </div>

          <n-spin v-if="loadingNews" />
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

            <div v-if="totalNews > pageSize" style="margin-top:16px;text-align:center">
              <n-button @click="router.push('/news')">{{ t('common.total', { count: totalNews }) }}</n-button>
            </div>
          </template>
        </div>
      </div>

      <aside class="side-col">
        <div class="bookmarks-section">
          <div class="section-header">
            <h3>{{ t('bookmarks.title') }}</h3>
            <n-button size="tiny" quaternary @click="showAddBookmark = true">+</n-button>
          </div>

          <n-spin v-if="linksStore.loadingBookmarks" size="small" />
          <template v-else>
            <div
              v-for="bm in linksStore.bookmarks"
              :key="bm.id"
              class="bookmark-row"
            >
              <a :href="bm.url" target="_blank" rel="noopener" class="bookmark-link">
                {{ bm.title }}
              </a>
              <n-button size="tiny" quaternary class="bm-del" @click.prevent="linksStore.removeBookmark(bm.id)">
                ×
              </n-button>
            </div>
            <n-empty v-if="!linksStore.bookmarks.length" size="small" :description="t('bookmarks.empty')" />
          </template>
        </div>

        <div class="quicklinks-section">
          <div class="section-header">
            <h3>{{ t('links.title') }}</h3>
            <n-button size="tiny" quaternary @click="router.push('/links')">{{ t('common.all') }}</n-button>
          </div>
          <div class="quick-links-list">
            <div
              v-for="link in topLinks"
              :key="link.id"
              class="quick-link-item"
              @click="linksStore.openLink(link)"
            >
              <img v-if="link.icon_url" :src="link.icon_url" class="ql-icon" :alt="link.title" />
              <span>{{ link.title }}</span>
            </div>
            <n-empty v-if="!topLinks.length" size="small" :description="t('links.empty')" />
          </div>
        </div>
      </aside>
    </div>

    <n-modal v-model:show="showAddBookmark" preset="dialog" :title="t('bookmarks.add')">
      <n-form @submit.prevent="submitBookmark">
        <n-form-item :label="t('bookmarks.titleField')">
          <n-input v-model:value="newBmTitle" :placeholder="t('bookmarks.titlePlaceholder')" />
        </n-form-item>
        <n-form-item label="URL">
          <n-input v-model:value="newBmUrl" placeholder="https://..." />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button @click="showAddBookmark = false">{{ t('common.cancel') }}</n-button>
        <n-button type="primary" :disabled="!newBmTitle || !newBmUrl" @click="submitBookmark">
          {{ t('common.save') }}
        </n-button>
      </template>
    </n-modal>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NButton, NSpin, NEmpty, NGrid, NGridItem, NModal, NForm, NFormItem, NInput,
} from 'naive-ui'
import AppLayout from '../components/AppLayout.vue'
import NewsCard from '../components/NewsCard.vue'
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
const pageSize = 10

const showAddBookmark = ref(false)
const newBmTitle = ref('')
const newBmUrl = ref('')

const pinned = computed(() => news.value.filter(n => n.is_pinned))
const regular = computed(() => news.value.filter(n => !n.is_pinned))
const topLinks = computed(() => linksStore.links.slice(0, 8))

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
</script>

<style scoped>
.home-wrap {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  gap: 24px;
  align-items: flex-start;
}
.main-col {
  flex: 1;
  min-width: 0;
}
.side-col {
  width: 260px;
  flex-shrink: 0;
}
.news-section,
.bookmarks-section,
.quicklinks-section {
  margin-bottom: 32px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-header h2,
.section-header h3 {
  margin: 0;
  font-size: 18px;
}
.section-header h3 {
  font-size: 15px;
}
.pinned-news {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}
.bookmark-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 4px 0;
  border-bottom: 1px solid var(--n-border-color, #eee);
}
.bookmark-link {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-decoration: none;
  color: var(--n-text-color, inherit);
}
.bookmark-link:hover {
  text-decoration: underline;
}
.bm-del {
  opacity: 0;
  flex-shrink: 0;
}
.bookmark-row:hover .bm-del {
  opacity: 1;
}
.quick-links-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.quick-link-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
}
.quick-link-item:hover {
  background: var(--n-color-hover, rgba(0,0,0,0.04));
}
.ql-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
}

@media (max-width: 768px) {
  .home-wrap {
    flex-direction: column;
  }
  .side-col {
    width: 100%;
  }
}
</style>
