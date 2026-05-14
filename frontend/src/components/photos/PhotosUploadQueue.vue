<template>
  <div v-if="queue.length" class="upload-queue">
    <div class="upload-queue__header">
      <span>{{ t('photos.upload.progress', { done: doneCount, total: queue.length }) }}</span>
      <n-button
        v-if="active && !aborted"
        size="tiny"
        type="error"
        ghost
        @click="$emit('abort')"
      >{{ t('photos.upload.cancel') }}</n-button>
      <n-button
        v-if="!active"
        size="tiny"
        @click="$emit('close')"
      >{{ t('common.close') }}</n-button>
    </div>
    <n-progress
      v-if="active"
      type="line"
      :percentage="totalProgress"
      :show-indicator="true"
      :height="6"
      style="margin-bottom: 8px"
    />
    <ul class="upload-queue__list">
      <li v-for="(item, i) in queue" :key="i" class="upload-queue__item">
        <span class="upload-queue__status">
          <template v-if="item.status === 'pending'">⏳</template>
          <template v-else-if="item.status === 'uploading'">🔄</template>
          <template v-else-if="item.status === 'done'">✓</template>
          <template v-else>✗</template>
        </span>
        <span class="upload-queue__name">{{ item.file.name }}</span>
        <span v-if="item.status === 'uploading'" class="upload-queue__pct">{{ item.progress }}%</span>
        <span v-if="item.error" class="upload-queue__error">{{ item.error }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NProgress } from 'naive-ui'
import type { UploadQueueItem } from '@/composables/usePhotoUpload'

defineProps<{
  queue: UploadQueueItem[]
  active: boolean
  aborted: boolean
  doneCount: number
  totalProgress: number
}>()

defineEmits<{
  abort: []
  close: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.upload-queue {
  background: var(--color-bg-muted);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.upload-queue__header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 6px;
}
.upload-queue__list { list-style: none; margin: 0; padding: 0; max-height: 160px; overflow-y: auto; }
.upload-queue__item {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 0; border-bottom: 1px solid var(--color-border);
}
.upload-queue__item:last-child { border-bottom: 0; }
.upload-queue__status { flex-shrink: 0; font-size: 14px; }
.upload-queue__name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.upload-queue__pct { font-size: 11px; color: var(--color-text-muted, #888); flex-shrink: 0; min-width: 32px; text-align: right; }
.upload-queue__error { font-size: 11px; color: var(--color-error, #e53e3e); flex-shrink: 0; }
</style>
