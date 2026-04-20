<template>
  <AppLayout>
    <template #header-title><span>{{ t('nav.links') }}</span></template>
    <n-empty :description="t('links.title') + ' — coming soon (Phase 2)'" style="margin-top:60px" />
  </AppLayout>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NEmpty } from 'naive-ui'
import AppLayout from '../components/AppLayout.vue'
const { t } = useI18n()
</script>
