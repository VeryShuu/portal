<template>
  <n-gi>
    <n-form-item :label="t('kb.form.status')">
      <n-select
        :value="status"
        :options="statusOptions"
        style="width:100%"
        @update:value="$emit('update:status', $event)"
      />
    </n-form-item>
  </n-gi>

  <n-gi v-if="isEdit">
    <n-form-item :label="t('kb.form.changeComment')">
      <n-input
        :value="changeComment"
        :placeholder="t('kb.form.changeCommentPlaceholder')"
        @update:value="$emit('update:changeComment', $event)"
      />
    </n-form-item>
  </n-gi>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem, NSelect, NInput, NGi, type SelectOption } from 'naive-ui'

defineProps<{
  status: 'draft' | 'published'
  changeComment: string
  isEdit: boolean
  statusOptions: SelectOption[]
}>()

defineEmits<{
  'update:status': [value: 'draft' | 'published']
  'update:changeComment': [value: string]
}>()

const { t } = useI18n()
</script>
