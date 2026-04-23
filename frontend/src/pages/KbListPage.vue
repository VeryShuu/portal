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
          <n-button v-if="auth.isEditor" size="medium" @click="showImportModal = true">
            ⬆ {{ t('kb.import.title') }}
          </n-button>
          <n-button v-if="auth.isEditor" type="primary" size="medium" @click="router.push('/kb/create')">
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
              v-if="auth.isEditor"
              class="sidebar-add-btn"
              title="Создать корневой раздел"
              @click="openCreateSection(null)"
            >
              <svg width="14" height="14" viewBox="0 0 13 13" fill="none">
                <path d="M6.5 1v11M1 6.5h11" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
              </svg>
              Новый раздел
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
              :is-editor="auth.isEditor"
              @select="selectedSection = $event"
              @add-child="openCreateSection"
              @manage-permissions="openSectionPermissions"
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

    <!-- Модал импорта -->
    <n-modal v-model:show="showImportModal" preset="card" :title="t('kb.import.title')" style="max-width:500px">
      <div class="import-wrap">
        <n-tabs v-model:value="importTab" type="line" size="small">
          <n-tab-pane name="md" :tab="t('kb.import.fromMd')">
            <div
              class="drop-zone"
              :class="{ 'drop-zone--over': mdDragOver }"
              @dragover.prevent="mdDragOver = true"
              @dragleave="mdDragOver = false"
              @drop.prevent="onDropMd"
              @click="mdFileRef?.click()"
            >
              <div v-if="mdFile">📄 {{ mdFile.name }}</div>
              <div v-else>{{ t('kb.import.fromMd') }} — перетащите или нажмите</div>
            </div>
            <input ref="mdFileRef" type="file" accept=".md" style="display:none" @change="onMdFileChange" />
          </n-tab-pane>

          <n-tab-pane name="vault" :tab="t('kb.import.fromVault')">
            <n-form-item :label="t('kb.import.strategy')">
              <n-select
                v-model:value="importStrategy"
                :options="strategyOptions"
                size="small"
                style="width:100%"
              />
            </n-form-item>
            <div
              class="drop-zone"
              :class="{ 'drop-zone--over': zipDragOver }"
              @dragover.prevent="zipDragOver = true"
              @dragleave="zipDragOver = false"
              @drop.prevent="onDropZip"
              @click="zipFileRef?.click()"
            >
              <div v-if="zipFile">📦 {{ zipFile.name }}</div>
              <div v-else>{{ t('kb.import.fromVault') }} — перетащите или нажмите</div>
            </div>
            <input ref="zipFileRef" type="file" accept=".zip" style="display:none" @change="onZipFileChange" />
          </n-tab-pane>
        </n-tabs>

        <div v-if="importResult" class="import-result">
          <div class="import-result__row import-result__created">✅ {{ t('kb.import.created') }}: {{ importResult.created }}</div>
          <div class="import-result__row import-result__updated">🔄 {{ t('kb.import.updated') }}: {{ importResult.updated }}</div>
          <div class="import-result__row import-result__skipped">⏭ {{ t('kb.import.skipped') }}: {{ importResult.skipped }}</div>
          <div v-if="importResult.errors.length" class="import-result__errors">
            <div class="import-result__row" style="color:var(--error-color)">❌ {{ t('kb.import.errors') }}:</div>
            <div v-for="e in importResult.errors" :key="e" class="import-result__error-item">{{ e }}</div>
          </div>
        </div>

        <div class="modal-actions" style="margin-top:16px">
          <n-button @click="closeImportModal">Закрыть</n-button>
          <n-button
            type="primary"
            :loading="importing"
            :disabled="importTab === 'md' ? !mdFile : !zipFile"
            @click="runImport"
          >Импортировать</n-button>
        </div>
      </div>
    </n-modal>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  NButton, NInput, NSelect, NPagination, NSkeleton, NIcon,
  NModal, NForm, NFormItem, NTabs, NTabPane,
} from 'naive-ui'
import { SearchOutline as SearchIcon } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import KbSectionTree from '../components/KbSectionTree.vue'
import KbPermissionsModal from '../components/KbPermissionsModal.vue'
import { useAuthStore } from '../stores/auth'
import {
  fetchSections, fetchArticles, createSection,
  importMarkdownFile, importVaultZip,
  type KbSection, type KbArticleListItem, type KbTag, type ImportResult,
} from '../api/kb'

const router = useRouter()
const auth = useAuthStore()
const { t, locale } = useI18n()
const message = useMessage()

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
    message.success('Раздел создан')
  } catch {
    message.error('Не удалось создать раздел')
  } finally {
    sectionSaving.value = false
  }
}

// ── Статьи ────────────────────────────────────────────────────────────────────
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

// ── Импорт ────────────────────────────────────────────────────────────────────
const showImportModal = ref(false)
const importTab = ref<'md' | 'vault'>('md')
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)

const mdFile = ref<File | null>(null)
const zipFile = ref<File | null>(null)
const mdDragOver = ref(false)
const zipDragOver = ref(false)
const mdFileRef = ref<HTMLInputElement | null>(null)
const zipFileRef = ref<HTMLInputElement | null>(null)

const importStrategy = ref<'skip' | 'overwrite' | 'create_new'>('skip')
const strategyOptions = computed(() => [
  { label: t('kb.import.skip'), value: 'skip' },
  { label: t('kb.import.overwrite'), value: 'overwrite' },
  { label: t('kb.import.createNew'), value: 'create_new' },
])

function onMdFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) mdFile.value = f
}
function onZipFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) zipFile.value = f
}
function onDropMd(e: DragEvent) {
  mdDragOver.value = false
  const f = e.dataTransfer?.files[0]
  if (f && f.name.endsWith('.md')) mdFile.value = f
}
function onDropZip(e: DragEvent) {
  zipDragOver.value = false
  const f = e.dataTransfer?.files[0]
  if (f && f.name.endsWith('.zip')) zipFile.value = f
}

function closeImportModal() {
  showImportModal.value = false
  mdFile.value = null
  zipFile.value = null
  importResult.value = null
}

async function runImport() {
  importing.value = true
  importResult.value = null
  try {
    if (importTab.value === 'md' && mdFile.value) {
      importResult.value = await importMarkdownFile(mdFile.value)
    } else if (importTab.value === 'vault' && zipFile.value) {
      importResult.value = await importVaultZip(zipFile.value, importStrategy.value)
    }
    await loadSections()
    await loadArticles()
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : 'Ошибка импорта')
  } finally {
    importing.value = false
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
  color: var(--color-brand-sky);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--t-fast);
  font-family: inherit;
  white-space: nowrap;
}
.sidebar-add-btn:hover {
  border-color: var(--color-brand-sky);
  background: color-mix(in srgb, var(--color-brand-sky) 8%, transparent);
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

.drop-zone {
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-lg);
  padding: 32px 16px;
  text-align: center;
  font-size: 14px;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--t-fast);
  margin-top: 8px;
}
.drop-zone:hover,
.drop-zone--over {
  border-color: var(--color-brand-sky);
  background: color-mix(in srgb, var(--color-brand-sky) 6%, transparent);
  color: var(--color-brand-sky);
}

.import-result {
  margin-top: 16px;
  padding: 12px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}
.import-result__row {
  font-size: 14px;
  margin-bottom: 4px;
}
.import-result__errors {
  margin-top: 8px;
}
.import-result__error-item {
  font-size: 12px;
  color: var(--error-color, #d32f2f);
  padding: 2px 0 2px 12px;
}
</style>
