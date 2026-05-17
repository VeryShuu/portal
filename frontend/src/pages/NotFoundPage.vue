<template>
  <div style="display:flex;align-items:center;justify-content:center;min-height:60vh">
    <n-result
      status="404"
      :title="t('errors.notFound.title')"
      :description="t('errors.notFound.description')"
    >
      <template #footer>
        <n-button @click="router.push('/')">
          {{ t('errors.notFound.back') }}
        </n-button>
        <n-button
          style="margin-left:8px"
          @click="router.back()"
        >
          {{ t('errors.notFound.goBack') }}
        </n-button>
      </template>
    </n-result>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NResult, NButton } from 'naive-ui'
const router = useRouter()
const { t } = useI18n()
</script>
