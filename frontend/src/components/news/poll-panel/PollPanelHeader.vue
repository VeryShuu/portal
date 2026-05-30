<template>
  <div class="u-panel__title-row">
    <div class="u-panel__title">
      {{ t('news.poll.editor.title') }}
    </div>
    <n-button
      v-if="showDelete"
      size="tiny"
      type="error"
      ghost
      :loading="deleting"
      @click="$emit('delete')"
    >
      {{ t('news.poll.editor.removePoll') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'

defineProps<{
  showDelete: boolean
  deleting: boolean
}>()

defineEmits<{
  delete: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.u-panel__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
</style>
