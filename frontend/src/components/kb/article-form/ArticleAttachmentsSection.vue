<template>
  <n-gi
    v-if="isEdit && articleId"
    :span="2"
  >
    <n-form-item :label="t('kb.files.title')">
      <KbAttachmentsPanel
        :article-id="articleId"
        :can-upload="true"
        style="width:100%"
      />
    </n-form-item>
  </n-gi>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem, NGi } from 'naive-ui'
import KbAttachmentsPanel from '../../KbAttachmentsPanel.vue'

defineProps<{
  articleId: string | undefined
  isEdit: boolean
}>()

const { t } = useI18n()
</script>
