<template>
  <div class="signature-actions">
    <n-button
      type="primary"
      :disabled="!canGenerate"
      :loading="generating"
      @click="emit('generate')"
    >
      {{ generated ? t('signature.actions.update') : t('signature.actions.generate') }}
    </n-button>
    <n-button
      :disabled="!hasResult"
      @click="emit('copy')"
    >
      {{ t('signature.actions.copy') }}
    </n-button>
    <n-button
      :disabled="!hasResult"
      @click="emit('download')"
    >
      {{ t('signature.actions.download') }}
    </n-button>
    <a
      v-if="mailtoSupport"
      class="signature-actions__support"
      :href="mailtoSupport"
    >
      {{ t('signature.actions.support', { email: supportEmail }) }}
    </a>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'

defineProps<{
  canGenerate: boolean
  generating: boolean
  generated: boolean
  hasResult: boolean
  mailtoSupport: string
  supportEmail: string
}>()

const emit = defineEmits<{
  generate: []
  copy: []
  download: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.signature-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.signature-actions__support {
  font-size: 12px;
  color: var(--color-text-secondary, #666);
  text-decoration: none;
  margin-left: auto;
}
.signature-actions__support:hover {
  text-decoration: underline;
}
</style>
