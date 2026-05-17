<template>
  <div class="files-bulk-bar">
    <span class="files-bulk-bar__count">{{ t('files.bulk.selected', { n: count }) }}</span>
    <n-tooltip
      v-if="count > downloadLimit"
      trigger="hover"
    >
      <template #trigger>
        <span>
          <n-button
            size="small"
            disabled
          >{{ t('files.bulk.download') }}</n-button>
        </span>
      </template>
      {{ t('files.bulk.downloadLimit') }}
    </n-tooltip>
    <n-button
      v-else
      size="small"
      @click="$emit('download')"
    >
      {{ t('files.bulk.download') }}
    </n-button>
    <n-button
      size="small"
      :disabled="!canUpload || bulkBusy"
      :loading="bulkBusy"
      @click="$emit('move')"
    >
      {{ t('files.bulk.move') }}
    </n-button>
    <n-button
      size="small"
      type="error"
      ghost
      :disabled="!canUpload || bulkBusy"
      :loading="bulkBusy"
      @click="$emit('delete')"
    >
      {{ t('files.bulk.delete') }}
    </n-button>
    <n-button
      size="small"
      text
      @click="$emit('clear')"
    >
      {{ t('files.bulk.clear') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NTooltip } from 'naive-ui'

defineProps<{
  count: number
  canUpload: boolean
  bulkBusy: boolean
  downloadLimit: number
}>()

defineEmits<{
  download: []
  move: []
  delete: []
  clear: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.files-bulk-bar {
  position: sticky;
  top: 0;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: var(--n-color, #fff);
  border: 1px solid var(--n-border-color, #e0e0e0);
  border-radius: 6px;
  margin-bottom: 12px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
  z-index: 5;
}

.files-bulk-bar__count {
  font-weight: 500;
  margin-right: 8px;
}
</style>
