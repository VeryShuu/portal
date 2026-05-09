<template>
  <div v-if="active" class="files-dropzone-overlay">
    <span>{{ t('files.dropzone.hint') }}</span>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  active: boolean
}>()

const { t } = useI18n()
</script>

<style scoped>
.files-dropzone-overlay {
  position: absolute;
  inset: 0;
  background: rgba(24, 160, 88, 0.08);
  border: 2px dashed var(--n-primary-color, #18a058);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 500;
  color: var(--n-primary-color, #18a058);
  pointer-events: none;
  z-index: 10;
}
</style>
