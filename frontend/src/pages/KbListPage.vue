<template>
  <AppLayout>
    <template #header-title>
      <span>{{ t('kb.title') }}</span>
    </template>

    <div class="kb-wrap">
      <div class="page-head">
        <div class="page-head__left">
          <h1 class="page-head__title">{{ t('kb.title') }}</h1>
          <div class="page-head__sub">{{ t('kb.pageSub') }}</div>
        </div>
        <div class="page-head__right">
          <n-button v-if="auth.isEditor" type="primary" size="medium" @click="router.push('/kb/create')">
            + {{ t('kb.createArticle') }}
          </n-button>
        </div>
      </div>

      <div class="kb-layout">
        <!-- Sidebar: дерево разделов -->
        <aside class="kb-sidebar">
          <div class="kb-sidebar__title">{{ t('kb.sections') }}</div>
          <div v-if="sectionsLoading" class="kb-sidebar__loading">
            <n-skeleton v-for="i in 4" :key="i" text style="margin-bottom:8px" />
          </div>
          <div v-else class="kb-tree">
            <button
              class="kb-tree__item"
              :class="{ 'kb-tree__item--active': !selectedSection }"
              @click="selectedSection = null"
            >
              {{ t('kb.allArticles') }}
            </button>
            <KbSectionTree
              v-for="section in sections"
              :key="section.id"
              :section="section"
              :active-id="selectedSection"
              @select="selectedSection = $event"
            />
          </div>
        </aside>

        <!-- Main: список статей -->
        <main class="kb-main">
          <div class="kb-toolbar">
            <n-input
              v-model:value="searchQuery"
              :placeholder="t('kb.searchPlaceholder')"
              clearable
              size="medium"
              style="flex:1;max-width:400px"
              @input="onSearchInput"
            >
              <template #prefix>
                <n-icon><SearchIcon /></n-icon>
              </template>
            </n-input>

            <n-select
              v-if="auth.isEditor"
              v-model:value="statusFilter"
              :options="statusOptions"
              size="medium"
              clearable
              :placeholder="t('kb.filterStatus')"
              style="width:160px"
            />

            <n-select
              v-if="tags.length"
              v-model:value="tagFilter"
              :options="tagOptions"
              size="medium"
              clearable
              :placeholder="t('kb.filterTag')"
              style="width:160px"
            />
          </div>

          <div v-if="loading" class="kb-grid">
            <SkeletonCard v-for="i in 6" :key="`sk-${i}`" variant="news" />
          </div>

          <template v-else>
            <div v-if="articles.length" class="kb-grid">
              <div
                v-for="article in articles"
                :key="article.id"
                class="kb-card"
                @click="router.push(`/kb/articles/${article.id}`)"
              >
                <div class="kb-card__top">
                  <span class="kb-card__status" :class="`kb-card__status--${article.status}`">
                    {{ t(`kb.status.${article.status}`) }}
                  </span>
                  <span class="kb-card__views">👁 {{ article.view_count }}</span>
                </div>
                <h3 class="kb-card__title">{{ article.title }}</h3>
                <div class="kb-card__tags">
                  <span v-for="tag in article.tags.slice(0, 3)" :key="tag.id" class="kb-tag">
                    {{ tag.name }}
                  </span>
                </div>
                <div class="kb-card__meta">
                  <span v-if="article.created_by">{{ article.created_by.full_name }}</span>
                  <span>{{ formatDate(article.updated_at) }}</span>
                </div>
              </div>
            </div>

            <EmptyState
              v-else
              variant="default"
              :title="t('kb.noArticles')"
              :description="t('kb.noArticlesHint')"
            />

            <n-pagination
              v-if="total > pageSize"
              v-model:page="page"
              :page-count="Math.ceil(total / pageSize)"
              style="margin-top:28px;justify-content:center"
            />
          </template>
        </main>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NSelect, NPagination, NSkeleton, NIcon } from 'naive-ui'
import { SearchOutline as SearchIcon } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import KbSectionTree from '../components/KbSectionTree.vue'
import { useAuthStore } from '../stores/auth'
import { fetchSections, fetchArticles, type KbSection, type KbArticleListItem, type KbTag } from '../api/kb'

const router = useRouter()
const auth = useAuthStore()
const { t, locale } = useI18n()

const sections = ref<KbSection[]>([])
const sectionsLoading = ref(true)
const selectedSection = ref<string | null>(null)

const articles = ref<KbArticleListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const searchQuery = ref('')
const statusFilter = ref<string | null>(null)
const tagFilter = ref<string | null>(null)
const tags = ref<KbTag[]>([])

let searchTimer: ReturnType<typeof setTimeout> | null = null

const statusOptions = computed(() => [
  { label: t('kb.status.draft'), value: 'draft' },
  { label: t('kb.status.published'), value: 'published' },
  { label: t('kb.status.archived'), value: 'archived' },
])

const tagOptions = computed(() =>
  tags.value.map((t) => ({ label: t.name, value: t.slug })),
)

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(locale.value === 'ru' ? 'ru-RU' : 'en-US', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadArticles()
  }, 400)
}

async function loadSections() {
  sectionsLoading.value = true
  try {
    const res = await fetchSections()
    sections.value = res.items
  } finally {
    sectionsLoading.value = false
  }
}

async function loadArticles() {
  loading.value = true
  try {
    const res = await fetchArticles({
      section_id: selectedSection.value ?? undefined,
      q: searchQuery.value || undefined,
      status: statusFilter.value ?? undefined,
      tag: tagFilter.value ?? undefined,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    articles.value = res.items
    total.value = res.total

    const allTags = new Map<string, KbTag>()
    res.items.forEach((a) => a.tags.forEach((tag) => allTags.set(tag.id, tag)))
    tags.value = [...allTags.values()]
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadSections()
  await loadArticles()
})

watch([selectedSection, statusFilter, tagFilter, page], () => loadArticles())
</script>

<style scoped>
.kb-wrap {
  max-width: 1280px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 24px;
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

.kb-layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 24px;
  align-items: start;
}

@media (max-width: 860px) {
  .kb-layout { grid-template-columns: 1fr; }
  .kb-sidebar { display: none; }
}

.kb-sidebar {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px;
  position: sticky;
  top: 80px;
}
.kb-sidebar__title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  margin-bottom: 12px;
}

.kb-tree__item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 7px 10px;
  border-radius: var(--radius-md);
  border: none;
  background: none;
  font-size: 14px;
  color: var(--color-text);
  cursor: pointer;
  transition: all var(--t-fast);
  font-family: inherit;
}
.kb-tree__item:hover { background: var(--color-border); }
.kb-tree__item--active {
  background: var(--color-brand-red);
  color: #fff;
  font-weight: 600;
}

.kb-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.kb-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 900px) {
  .kb-grid { grid-template-columns: 1fr; }
}

.kb-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px;
  cursor: pointer;
  transition: all var(--t-fast);
}
.kb-card:hover {
  border-color: var(--color-brand-sky);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.kb-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.kb-card__status {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
}
.kb-card__status--published { background: #e8f5e9; color: #2e7d32; }
.kb-card__status--draft { background: #fff3e0; color: #e65100; }
.kb-card__status--archived { background: var(--color-border); color: var(--color-text-muted); }

.kb-card__views {
  font-size: 12px;
  color: var(--color-text-muted);
}

.kb-card__title {
  margin: 0 0 10px;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.kb-card__tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.kb-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--color-brand-sky) 12%, transparent);
  color: var(--color-brand-sky);
}

.kb-card__meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
