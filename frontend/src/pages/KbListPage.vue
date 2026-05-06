<template>
  <div class="kb-wrap">
      <div class="page-head">
        <div class="page-head__left">
          <h1 class="page-head__title">{{ t('kb.title') }}</h1>
          <div class="page-head__sub">{{ t('kb.pageSub') }}</div>
        </div>
        <div class="page-head__right">
          <n-button
            v-if="selectedSection"
            size="medium"
            @click="onExportSection"
          >
            ⬇ {{ t('kb.export.sectionZip') }}
          </n-button>
          <n-button size="medium" @click="showImportModal = true">
            ⬆ {{ t('kb.import.title') }}
          </n-button>
          <n-button type="primary" size="medium" @click="router.push('/kb/create')">
            + {{ t('kb.createArticle') }}
          </n-button>
        </div>
      </div>

      <div class="kb-layout">
        <!-- Sidebar: дерево разделов -->
        <aside class="kb-sidebar">
          <div class="kb-sidebar__header">
            <div class="kb-sidebar__title">{{ t('kb.sections') }}</div>
            <button
              class="sidebar-add-btn"
              :title="t('kb.create_root_section')"
              @click="openCreateSection(null)"
            >
              <svg width="14" height="14" viewBox="0 0 13 13" fill="none">
                <path d="M6.5 1v11M1 6.5h11" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
              </svg>
              {{ t('kb.new_section') }}
            </button>
          </div>
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
              :is-admin="auth.isAdmin"
              @select="selectedSection = $event"
              @add-child="openCreateSection"
              @manage-permissions="openSectionPermissions"
              @delete-section="confirmDeleteSection"
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
                    <span class="kb-card__status-dot" aria-hidden="true"></span>{{ t(`kb.status.${article.status}`, article.status) }}
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

    <!-- Модал прав раздела -->
    <KbPermissionsModal
      v-if="sectionPermsId"
      v-model="showSectionPermsModal"
      resource-type="section"
      :resource-id="sectionPermsId"
    />

    <!-- Модал создания раздела -->
    <n-modal v-model:show="showSectionModal" preset="card" title="Новый раздел" style="max-width:420px">
      <n-form @submit.prevent="submitCreateSection">
        <n-form-item label="Название" required>
          <n-input v-model:value="sectionForm.title" placeholder="Название раздела" />
        </n-form-item>
        <n-form-item label="Описание">
          <n-input v-model:value="sectionForm.description" type="textarea" :rows="2" placeholder="Необязательно" />
        </n-form-item>
        <div class="modal-actions">
          <n-button @click="showSectionModal = false">Отмена</n-button>
          <n-button
            type="primary"
            :loading="sectionSaving"
            :disabled="!sectionForm.title.trim()"
            attr-type="submit"
          >Создать</n-button>
        </div>
      </n-form>
    </n-modal>

    <KbImportModal
      v-model:show="showImportModal"
      @imported="onImported"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage, useDialog } from 'naive-ui'
import {
  NButton, NInput, NSelect, NPagination, NSkeleton, NIcon,
  NModal, NForm, NFormItem,
} from 'naive-ui'
import { SearchOutline as SearchIcon } from '@vicons/ionicons5'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import KbSectionTree from '../components/KbSectionTree.vue'
import KbPermissionsModal from '../components/KbPermissionsModal.vue'
import KbImportModal from '../components/KbImportModal.vue'
import { useAuthStore } from '../stores/auth'
import {
  fetchSections, fetchArticles, createSection, deleteSection,
  exportSectionZip,
  type KbSection, type KbArticleListItem, type KbTag,
} from '../api/kb'

const router = useRouter()
const auth = useAuthStore()
const { t, locale } = useI18n()
const message = useMessage()
const dialog = useDialog()
const queryClient = useQueryClient()

// ── Разделы ───────────────────────────────────────────────────────────────────
const sections = ref<KbSection[]>([])
const sectionsLoading = ref(true)
const selectedSection = ref<string | null>(null)

const showSectionModal = ref(false)
const sectionSaving = ref(false)
const sectionForm = ref({ title: '', description: '', parent_id: null as string | null })

const showSectionPermsModal = ref(false)
const sectionPermsId = ref<string | null>(null)

function openSectionPermissions(sectionId: string) {
  sectionPermsId.value = sectionId
  showSectionPermsModal.value = true
}

function openCreateSection(parentId: string | null) {
  sectionForm.value = { title: '', description: '', parent_id: parentId }
  showSectionModal.value = true
}

async function submitCreateSection() {
  if (!sectionForm.value.title.trim()) return
  sectionSaving.value = true
  try {
    await createSection({
      title: sectionForm.value.title.trim(),
      description: sectionForm.value.description || null,
      parent_id: sectionForm.value.parent_id,
    })
    showSectionModal.value = false
    await loadSections()
    queryClient.invalidateQueries({ queryKey: ['kb-articles'] })
    message.success('Раздел создан')
  } catch {
    message.error('Не удалось создать раздел')
  } finally {
    sectionSaving.value = false
  }
}

function confirmDeleteSection(sectionId: string) {
  dialog.warning({
    title: t('kb.section.delete'),
    content: t('kb.section.deleteConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await deleteSection(sectionId)
        if (selectedSection.value === sectionId) selectedSection.value = null
        await loadSections()
        message.success(t('kb.section.deleteSuccess'))
      } catch {
        message.error(t('kb.section.deleteError'))
      }
    },
  })
}

// ── Статьи ────────────────────────────────────────────────────────────────────
const page = ref(1)
const pageSize = 20
const searchQuery = ref('')
const debouncedQuery = ref('')
const statusFilter = ref<string | null>(null)
const tagFilter = ref<string | null>(null)

let searchTimer: ReturnType<typeof setTimeout> | null = null

const statusOptions = computed(() => [
  { label: t('kb.status.draft'), value: 'draft' },
  { label: t('kb.status.published'), value: 'published' },
  { label: t('kb.status.archived'), value: 'archived' },
])

const { data: articlesData, isLoading: loading } = useQuery({
  queryKey: computed(() => ['kb-articles', selectedSection.value, debouncedQuery.value, statusFilter.value, tagFilter.value, page.value]),
  queryFn: () => fetchArticles({
    section_id: selectedSection.value ?? undefined,
    q: debouncedQuery.value || undefined,
    status: statusFilter.value ?? undefined,
    tag: tagFilter.value ?? undefined,
    limit: pageSize,
    offset: (page.value - 1) * pageSize,
  }),
  staleTime: 60_000,
})

const articles = computed<KbArticleListItem[]>(() => articlesData.value?.items ?? [])
const total = computed(() => articlesData.value?.total ?? 0)
const tags = computed<KbTag[]>(() => {
  const allTags = new Map<string, KbTag>()
  articles.value.forEach((a) => a.tags.forEach((tag) => allTags.set(tag.id, tag)))
  return [...allTags.values()]
})

const tagOptions = computed(() =>
  tags.value.map((tg) => ({ label: tg.name, value: tg.slug })),
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
    debouncedQuery.value = searchQuery.value
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

// ── Импорт ────────────────────────────────────────────────────────────────────
const showImportModal = ref(false)

async function onImported() {
  await loadSections()
  queryClient.invalidateQueries({ queryKey: ['kb-articles'] })
}

function onExportSection() {
  if (selectedSection.value) exportSectionZip(selectedSection.value)
}

onMounted(async () => {
  await loadSections()
})
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
.kb-sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 8px;
}
.kb-sidebar__title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.sidebar-add-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--t-fast);
  font-family: inherit;
  white-space: nowrap;
}
.sidebar-add-btn:hover {
  border-color: var(--color-border-strong);
  background: var(--color-bg-muted);
  color: var(--color-text);
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
  padding: 14px 18px;
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
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
}
.kb-card__status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
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

.page-head__right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}


</style>
