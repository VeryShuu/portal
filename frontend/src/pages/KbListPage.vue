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
          v-if="sectionsCtl.selectedSection.value"
          size="medium"
          @click="onExportSection"
        >
          ⬇ {{ t('kb.export.sectionZip') }}
        </n-button>
        <n-button
          size="medium"
          @click="showImportModal = true"
        >
          ⬆ {{ t('kb.import.title') }}
        </n-button>
        <n-button
          type="primary"
          size="medium"
          @click="router.push('/kb/create')"
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
          <button
            class="sidebar-add-btn"
            :title="t('kb.create_root_section')"
            @click="sectionsCtl.openCreateSection(null)"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 13 13"
              fill="none"
            >
              <path
                d="M6.5 1v11M1 6.5h11"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              />
            </svg>
            {{ t('kb.new_section') }}
          </button>
        </div>
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
            @manage-permissions="sectionsCtl.openSectionPermissions"
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
          @search-input="listing.onSearchInput"
        />

        <div
          v-if="listing.loading.value"
          class="kb-grid"
        >
          <SkeletonCard
            v-for="i in 6"
            :key="`sk-${i}`"
            variant="article"
          />
        </div>

        <template v-else>
          <div
            v-if="listing.articles.value.length"
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
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NPagination } from 'naive-ui'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import KbSectionTree from '../components/KbSectionTree.vue'
import KbPermissionsModal from '../components/KbPermissionsModal.vue'
import KbImportModal from '../components/KbImportModal.vue'
import KbArticleCard from '../components/KbArticleCard.vue'
import KbListToolbar from '../components/KbListToolbar.vue'
import KbSectionFormModal from '../components/KbSectionFormModal.vue'
import { useAuthStore } from '../stores/auth'
import { exportSectionZip } from '../api/kb'
import { useKbSections } from '../composables/useKbSections'
import { useKbArticleListing } from '../composables/useKbArticleListing'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

const sectionsCtl = useKbSections()
const listing = useKbArticleListing({ selectedSection: sectionsCtl.selectedSection })

const showImportModal = ref(false)

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

.kb-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 900px) {
  .kb-grid { grid-template-columns: 1fr; }
}

</style>
