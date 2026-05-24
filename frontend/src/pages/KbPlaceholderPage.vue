<template>
  <n-empty
    :description="t('kb.title') + ' — ' + t('kb.comingSoon')"
    style="margin-top:60px"
  />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NEmpty } from 'naive-ui'
const { t } = useI18n()
</script>
