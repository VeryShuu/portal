<template>
  <n-empty :description="t('kb.title') + ' — coming soon (Phase 3)'" style="margin-top:60px" />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NEmpty } from 'naive-ui'
const { t } = useI18n()
</script>
