<template>
  <n-modal
    :show="show"
    preset="dialog"
    :title="t('editor.details.insert')"
    style="max-width: 480px"
    @update:show="$emit('update:show', $event)"
  >
    <n-input
      :value="summary"
      :placeholder="t('editor.details.summaryPlaceholder')"
      clearable
      @update:value="$emit('update:summary', $event)"
    />
    <template #action>
      <n-button
        size="small"
        @click="$emit('update:show', false)"
      >
        {{ t('common.cancel') }}
      </n-button>
      <n-button
        size="small"
        type="primary"
        @click="$emit('insert')"
      >
        {{ t('editor.insert') }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { NButton, NInput, NModal } from 'naive-ui'
import { useI18n } from 'vue-i18n'

defineProps<{
  show: boolean
  summary: string
}>()

defineEmits<{
  'update:show': [value: boolean]
  'update:summary': [value: string]
  insert: []
}>()

const { t } = useI18n()
</script>
