<template>
  <div class="kb-wrap">
    <div class="page-head u-page-head">
      <div class="page-head__left">
        <h1 class="u-page-head__title">
          {{ t('kb.title') }}
        </h1>
        <div class="u-page-head__sub">
          {{ t('kb.pageSub') }}
        </div>
      </div>
      <div class="page-head__right u-page-head__actions">
        <n-button
          v-if="auth.isAdmin"
          size="medium"
          quaternary
          circle
          :title="t('admin.tabs.kb')"
          @click="manage.open('kb')"
        >
          <template #icon>
            <n-icon :component="SettingsOutline" />
          </template>
        </n-button>
        <n-button
          v-if="auth.isAdmin"
          size="medium"
          quaternary
          :title="t('kb.trash.openTitle')"
          @click="router.push({ name: 'kb-trash' })"
        >
          <template #icon>
            <n-icon :component="TrashOutline" />
          </template>
          {{ t('kb.trash.short') }}
        </n-button>
        <n-button
          v-if="sectionsCtl.selectedSection.value"
          size="medium"
          @click="onExportSection"
        >
          ⬇ {{ t('kb.export.sectionZip') }}
        </n-button>
        <n-button
          v-if="auth.isEditor"
          size="medium"
          @click="showImportModal = true"
        >
          ⬆ {{ t('kb.import.title') }}
        </n-button>
        <n-button
          v-if="canCreateArticle"
          type="primary"
          size="medium"
          @click="router.push({ path: '/kb/create', query: sectionsCtl.selectedSection.value ? { section_id: sectionsCtl.selectedSection.value } : {} })"
        >
          + {{ t('kb.createArticle') }}
        </n-button>
      </div>
    </div>

    <div class="kb-layout">
      <aside class="kb-sidebar">
        <div class="kb-sidebar__header">
          <div class="kb-sidebar__title">
            {{ t('kb.sections') }}
          </div>
        </div>
        <button
          v-if="auth.isEditor"
          class="sidebar-add-btn"
          :title="t('kb.create_root_section')"
          @click="sectionsCtl.openCreateSection(null)"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 13 13"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M6.5 1v11M1 6.5h11"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            />
          </svg>
          <span>{{ t('kb.new_section') }}</span>
        </button>
        <div
          v-if="sectionsCtl.sectionsLoading.value"
          class="kb-sidebar__loading"
        >
          <SkeletonCard
            v-for="i in 6"
            :key="i"
            variant="folder-item"
          />
        </div>
        <div
          v-else
          class="kb-tree"
        >
          <button
            class="kb-tree__item"
            :class="{ 'kb-tree__item--active': !sectionsCtl.selectedSection.value }"
            @click="sectionsCtl.selectedSection.value = null"
          >
            {{ t('kb.allArticles') }}
          </button>
          <KbSectionTree
            v-for="section in sectionsCtl.sections.value"
            :key="section.id"
            :section="section"
            :active-id="sectionsCtl.selectedSection.value"
            :is-admin="auth.isAdmin"
            @select="sectionsCtl.selectedSection.value = $event"
            @add-child="sectionsCtl.openCreateSection"
            @rename-section="sectionsCtl.renameSection"
            @manage-permissions="sectionsCtl.openSectionPermissions"
            @move-section="sectionsCtl.openMoveSection"
            @delete-section="sectionsCtl.confirmDeleteSection"
          />
        </div>
      </aside>

      <main class="kb-main">
        <KbListToolbar
          v-model:search-query="listing.searchQuery.value"
          v-model:status-filter="listing.statusFilter.value"
          v-model:tag-filter="listing.tagFilter.value"
          :tag-options="listing.tagOptions.value"
          :view-mode="viewMode"
          @update:view-mode="onViewModeChange"
          @search-input="listing.onSearchInput"
        />

        <div
          v-if="listing.loading.value"
          :class="viewMode === 'grid' ? 'kb-grid' : 'kb-list'"
        >
          <SkeletonCard
            v-for="i in 6"
            :key="`sk-${i}`"
            :variant="viewMode === 'grid' ? 'article' : 'folder-item'"
          />
        </div>

        <template v-else>
          <div
            v-if="listing.articles.value.length && viewMode === 'grid'"
            class="kb-grid"
          >
            <KbArticleCard
              v-for="article in listing.articles.value"
              :key="article.id"
              :article="article"
              :active-tag="listing.tagFilter.value"
              @open="router.push(`/kb/articles/${$event.id}`)"
              @select-tag="listing.selectTag"
            />
          </div>

          <div
            v-else-if="listing.articles.value.length"
            class="kb-list"
          >
            <KbArticleListRow
              v-for="article in listing.articles.value"
              :key="article.id"
              :article="article"
              :active-tag="listing.tagFilter.value"
              @open="router.push(`/kb/articles/${$event.id}`)"
              @select-tag="listing.selectTag"
            />
          </div>

          <EmptyState
            v-else
            variant="default"
            :title="t('kb.noArticles')"
            :description="t('kb.noArticlesHint')"
          />

          <n-pagination
            v-if="listing.total.value > listing.pageSize"
            v-model:page="listing.page.value"
            :page-count="Math.ceil(listing.total.value / listing.pageSize)"
            style="margin-top:28px;justify-content:center"
          />
        </template>
      </main>
    </div>

    <KbPermissionsModal
      v-if="sectionsCtl.sectionPermsId.value"
      v-model="sectionsCtl.showSectionPermsModal.value"
      resource-type="section"
      :resource-id="sectionsCtl.sectionPermsId.value"
      :inherit-permissions="sectionsCtl.sectionPermsInherit.value"
      @inherit-changed="sectionsCtl.onSectionInheritChanged"
    />

    <KbSectionMoveModal
      :show="sectionsCtl.showMoveModal.value"
      :section-id="sectionsCtl.moveSectionId.value"
      :sections="sectionsCtl.sections.value"
      :saving="sectionsCtl.moveSaving.value"
      @update:show="sectionsCtl.showMoveModal.value = $event"
      @submit="sectionsCtl.submitMoveSection"
    />

    <KbSectionFormModal
      v-model:show="sectionsCtl.showSectionModal.value"
      :form="sectionsCtl.sectionForm.value"
      :saving="sectionsCtl.sectionSaving.value"
      @update:form="sectionsCtl.sectionForm.value = $event"
      @submit="sectionsCtl.submitCreateSection"
    />

    <KbImportModal
      v-model:show="showImportModal"
      @imported="onImported"
    />

    <n-drawer
      :show="manage.is('kb') && auth.isAdmin"
      :width="720"
      placement="right"
      :on-update:show="(v: boolean) => { if (!v) manage.close() }"
    >
      <n-drawer-content
        :title="t('admin.tabs.kb')"
        closable
      >
        <Suspense>
          <KbAdminTab />
        </Suspense>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NDrawer, NDrawerContent, NIcon, NPagination } from 'naive-ui'
import { SettingsOutline, TrashOutline } from '@vicons/ionicons5'
import { useManageDrawer } from '../composables/useManageDrawer'

const KbAdminTab = defineAsyncComponent(() => import('./admin/tabs/KbTab.vue'))
const manage = useManageDrawer(['kb'])
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import KbSectionTree from '../components/KbSectionTree.vue'
import KbPermissionsModal from '../components/KbPermissionsModal.vue'
import KbImportModal from '../components/KbImportModal.vue'
import KbArticleCard from '../components/KbArticleCard.vue'
import KbArticleListRow from '../components/KbArticleListRow.vue'
import KbListToolbar, { type KbViewMode } from '../components/KbListToolbar.vue'
import KbSectionFormModal from '../components/KbSectionFormModal.vue'
import KbSectionMoveModal from '../components/KbSectionMoveModal.vue'
import { useAuthStore } from '../stores/auth'
import { exportSectionZip } from '../api/kb'
import { useKbSections, findSectionRecursive } from '../composables/useKbSections'
import { useKbArticleListing } from '../composables/useKbArticleListing'
import type { KbSection } from '../api/kb'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

const sectionsCtl = useKbSections()
const listing = useKbArticleListing({ selectedSection: sectionsCtl.selectedSection })

const selectedSectionNode = computed<KbSection | null>(() => {
  const id = sectionsCtl.selectedSection.value
  if (!id) return null
  return findSectionRecursive(sectionsCtl.sections.value, id)
})

const canCreateArticle = computed(() => {
  if (auth.isEditor) return true
  const sec = selectedSectionNode.value
  if (!sec) return false
  return sec.user_permission === 'editor' || sec.user_permission === 'manager'
})

const showImportModal = ref(false)

const VIEW_MODE_KEY = 'kb:viewMode'
function readViewMode(): KbViewMode {
  if (typeof window === 'undefined') return 'list'
  const v = window.localStorage.getItem(VIEW_MODE_KEY)
  return v === 'grid' ? 'grid' : 'list'
}
const viewMode = ref<KbViewMode>(readViewMode())
function onViewModeChange(v: KbViewMode) {
  viewMode.value = v
  try {
    window.localStorage.setItem(VIEW_MODE_KEY, v)
  } catch {
    // ignore quota / privacy mode failures
  }
}

function onImported() {}

function onExportSection() {
  if (sectionsCtl.selectedSection.value) {
    exportSectionZip(sectionsCtl.selectedSection.value)
  }
}
</script>

<style scoped>
.kb-wrap {
  max-width: 1280px;
  margin: 0 auto;
}

.page-head {
  margin-bottom: 24px;
}

.kb-layout {
  display: grid;
  grid-template-columns: clamp(280px, 22vw, 340px) 1fr;
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
  margin-bottom: 10px;
  gap: 8px;
}

.kb-sidebar__title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

.sidebar-add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  min-height: 38px;
  padding: 8px 12px;
  margin-bottom: 14px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--t-fast);
  font-family: inherit;
  white-space: nowrap;
}
.sidebar-add-btn:hover {
  border-color: var(--color-brand-red);
  background: color-mix(in srgb, var(--color-brand-red) 8%, transparent);
  color: var(--color-brand-red);
}

.kb-tree__item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 9px 12px;
  min-height: 36px;
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

.kb-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 900px) {
  .kb-grid { grid-template-columns: 1fr; }
}

.kb-list {
  display: flex;
  flex-direction: column;
}

</style>
