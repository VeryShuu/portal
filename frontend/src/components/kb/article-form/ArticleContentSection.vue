<template>
  <n-form-item
    :label="t('kb.form.body')"
    required
    class="content-item"
    :validation-status="error ? 'error' : undefined"
    :feedback="error ? errorText : undefined"
  >
    <RichEditor
      :model-value="modelValue"
      :placeholder="t('kb.form.bodyPlaceholder')"
      :upload-endpoint="uploadEndpoint"
      class="article-editor"
      @update:model-value="$emit('update:modelValue', $event)"
    />
  </n-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem } from 'naive-ui'
import RichEditor from '../../RichEditor.vue'

defineProps<{
  modelValue: string
  uploadEndpoint?: string
  error?: boolean
  errorText?: string
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()

const { t } = useI18n()
</script>

<style scoped>
.content-item :deep(.n-form-item-blank) {
  width: 100%;
}
.article-editor {
  width: 100%;
}
.article-editor :deep(.editor-content) {
  min-height: 460px;
}
</style>
