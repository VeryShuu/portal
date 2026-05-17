<template>
  <div class="admin-wrap">
    <header class="page-head">
      <h1 class="u-page-head__title">
        {{ t('settings.title') }}
      </h1>
    </header>

    <n-tabs
      v-model:value="activeTab"
      type="line"
      animated
      display-directive="if"
    >
      <n-tab-pane
        name="links"
        :tab="t('admin.tabs.links')"
      >
        <Suspense><LinksTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane
        name="branding"
        :tab="t('admin.tabs.branding')"
      >
        <Suspense><BrandingTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane
        name="news-categories"
        :tab="t('admin.tabs.newsCategories')"
      >
        <Suspense><NewsCategoriesTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane
        name="world-clock"
        :tab="t('admin.tabs.worldClock')"
      >
        <Suspense><WorldClockTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane
        name="kb"
        :tab="t('admin.tabs.kb')"
      >
        <Suspense><KbTab /></Suspense>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { NTabs, NTabPane } from 'naive-ui'

const { t } = useI18n()
const activeTab = ref('links')

const LinksTab = defineAsyncComponent(() => import('./admin/tabs/LinksTab.vue'))
const BrandingTab = defineAsyncComponent(() => import('./admin/tabs/BrandingTab.vue'))
const NewsCategoriesTab = defineAsyncComponent(() => import('./admin/tabs/NewsCategoriesTab.vue'))
const WorldClockTab = defineAsyncComponent(() => import('./admin/tabs/WorldClockTab.vue'))
const KbTab = defineAsyncComponent(() => import('./admin/tabs/KbTab.vue'))
</script>

<style scoped>
.admin-wrap {
  max-width: 1280px;
  margin: 0 auto;
}

.page-head {
  margin-bottom: 20px;
}
</style>
