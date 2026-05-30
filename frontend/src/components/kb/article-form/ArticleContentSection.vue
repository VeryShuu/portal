<template>
  <n-gi :span="2">
    <n-form-item
      :label="t('kb.form.body')"
      required
    >
      <RichEditor
        :model-value="modelValue"
        :placeholder="t('kb.form.bodyPlaceholder')"
        :upload-endpoint="uploadEndpoint"
        style="width:100%"
        @update:model-value="$emit('update:modelValue', $event)"
      />
    </n-form-item>
  </n-gi>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem, NGi } from 'naive-ui'
import RichEditor from '../../RichEditor.vue'

defineProps<{
  modelValue: string
  uploadEndpoint?: string
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()

const { t } = useI18n()
</script>
