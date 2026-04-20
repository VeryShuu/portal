<template>
  <n-result status="404" :title="t('errors.notFound.title')" :description="t('errors.notFound.description')">
    <template #footer>
      <n-button @click="router.push('/')">{{ t('errors.notFound.back') }}</n-button>
    </template>
  </n-result>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NResult, NButton } from 'naive-ui'

const router = useRouter()
const { t } = useI18n()
</script>
