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
      <KbListPageActions
        :is-admin="auth.isAdmin"
        :is-editor="auth.isEditor"
        :can-create-article="canCreateArticle"
        :selected-section="sectionsCtl.selectedSection.value"
        @manage="manage.open('kb')"
        @open-trash="openTrash"
        @export-section="onExportSection"
        @open-import="showImportModal = true"
        @create-article="openCreate(sectionsCtl.selectedSection.value)"
      />
    </div>

    <div class="kb-layout">
      <KbListSidebar
        :sections-ctl="sectionsCtl"
        :is-admin="auth.isAdmin"
        @select-section="sectionsCtl.selectedSection.value = $event"
      />

      <KbListArticles
        v-model:search-query="listing.searchQuery.value"
        v-model:status-filter="listing.statusFilter.value"
        v-model:tag-filter="listing.tagFilter.value"
        v-model:page="listing.page.value"
        :listing="listing"
        :view-mode="viewMode"
        @update:view-mode="onViewModeChange"
        @open-article="openArticle"
      />
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
import { defineAsyncComponent, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NDrawer, NDrawerContent } from 'naive-ui'
import { useManageDrawer } from '../composables/useManageDrawer'

const KbAdminTab = defineAsyncComponent(() => import('./admin/tabs/KbTab.vue'))
const manage = useManageDrawer(['kb'])
import KbPermissionsModal from '../components/KbPermissionsModal.vue'
import KbImportModal from '../components/KbImportModal.vue'
import KbSectionFormModal from '../components/KbSectionFormModal.vue'
import KbSectionMoveModal from '../components/KbSectionMoveModal.vue'
import KbListPageActions from '../components/KbListPageActions.vue'
import KbListSidebar from '../components/KbListSidebar.vue'
import KbListArticles from '../components/KbListArticles.vue'
import { useAuthStore } from '../stores/auth'
import { useKbSections } from '../composables/useKbSections'
import { useKbArticleListing } from '../composables/useKbArticleListing'
import { useKbListViewMode } from './composables/useKbListViewMode'
import { useKbListPagePermissions } from './composables/useKbListPagePermissions'
import { useKbListNavigation } from './composables/useKbListNavigation'
import { useKbSectionExport } from './composables/useKbSectionExport'

const auth = useAuthStore()
const { t } = useI18n()

const sectionsCtl = useKbSections()
const listing = useKbArticleListing({ selectedSection: sectionsCtl.selectedSection })

const { canCreateArticle } = useKbListPagePermissions({
  auth,
  sections: sectionsCtl.sections,
  selectedSection: sectionsCtl.selectedSection,
})

const { viewMode, onViewModeChange } = useKbListViewMode()
const { openTrash, openCreate, openArticle } = useKbListNavigation()
const { onExportSection } = useKbSectionExport(sectionsCtl.selectedSection)

const showImportModal = ref(false)

function onImported() {}
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
</style>
