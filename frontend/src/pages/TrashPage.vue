<template>
  <div class="trash-wrap">
    <header class="page-head">
      <h1 class="page-head__title">{{ t('trash.title') }}</h1>
    </header>

    <n-tabs type="line" animated display-directive="if">
      <n-tab-pane name="news" :tab="t('trash.tabs.news')">
        <Suspense><TrashNewsTab /></Suspense>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { NTabs, NTabPane } from 'naive-ui'

const { t } = useI18n()

const TrashNewsTab = defineAsyncComponent(
  () => import('../components/trash/TrashNewsTab.vue'),
)
</script>
