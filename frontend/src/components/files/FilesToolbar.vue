<template>
  <div class="files-toolbar">
    <div class="files-toolbar__left">
      <h1 class="files-title">{{ currentFolder?.name }}</h1>
      <n-tag v-if="currentFolder?.permission" size="small" :type="permTagType(currentFolder.permission)">
        {{ t(`files.permission.${currentFolder.permission}`) }}
      </n-tag>
      <n-tag v-if="currentFolder && !canEdit" size="small" type="info">
        {{ t('files.readonly') }}
      </n-tag>
    </div>
    <div class="files-toolbar__right">
      <n-button
        v-if="canUpload"
        size="small"
        type="primary"
        @click="$emit('upload-click')"
      >{{ t('files.upload') }}</n-button>
      <n-button
        v-if="canManage"
        size="small"
        @click="$emit('manage-click')"
      >{{ t('files.manage') }}</n-button>
    </div>
  </div>

  <div v-if="uploading" class="files-upload-progress">
    <n-progress
      type="line"
      :percentage="uploadProgress.total ? Math.round((uploadProgress.done / uploadProgress.total) * 100) : 0"
      :show-indicator="false"
      :height="6"
    />
    <span class="files-upload-progress__text">
      {{ t('files.uploadProgress', { done: uploadProgress.done, total: uploadProgress.total }) }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NProgress, NTag } from 'naive-ui'
import type { FileFolderPublic } from '../../api/files'

defineProps<{
  currentFolder: FileFolderPublic | null
  canUpload: boolean
  canManage: boolean
  canEdit: boolean
  uploading: boolean
  uploadProgress: { done: number; total: number; failed: number }
}>()

defineEmits<{
  'upload-click': []
  'manage-click': []
}>()

const { t } = useI18n()

function permTagType(perm: string) {
  if (perm === 'manager') return 'success'
  if (perm === 'editor') return 'info'
  return 'default'
}
</script>

<style scoped>
.files-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.files-toolbar__left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.files-toolbar__right {
  display: flex;
  gap: 8px;
}

.files-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}

.files-upload-progress {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.files-upload-progress__text {
  font-size: 12px;
  color: var(--n-text-color-3, #666);
}
</style>
