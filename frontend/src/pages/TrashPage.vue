<template>
  <div class="trash-wrap">
    <header class="page-head">
      <h1 class="page-head__title">
        {{ t('trash.title') }}
      </h1>
    </header>

    <n-tabs
      type="line"
      animated
      display-directive="if"
    >
      <n-tab-pane
        name="news"
        :tab="t('trash.tabs.news')"
      >
        <Suspense><TrashNewsTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane
        name="photos"
        :tab="t('trash.tabs.photos')"
      >
        <Suspense>
          <PhotoTrashView
            :is-admin="auth.isAdmin"
            embedded
          />
        </Suspense>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { NTabs, NTabPane } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()

const TrashNewsTab = defineAsyncComponent(
  () => import('../components/trash/TrashNewsTab.vue'),
)
const PhotoTrashView = defineAsyncComponent(
  () => import('../components/photos/PhotoTrashView.vue'),
)
</script>
