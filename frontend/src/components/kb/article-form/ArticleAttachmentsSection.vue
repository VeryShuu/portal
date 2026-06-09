<template>
  <section
    v-if="isEdit && articleId"
    class="attachments-card"
  >
    <h2 class="attachments-card__title">
      {{ t('kb.files.title') }}
    </h2>
    <KbAttachmentsPanel
      :article-id="articleId"
      :can-upload="true"
    />
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import KbAttachmentsPanel from '../../KbAttachmentsPanel.vue'

defineProps<{
  articleId: string | undefined
  isEdit: boolean
}>()

const { t } = useI18n()
</script>

<style scoped>
.attachments-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 18px;
  box-shadow: var(--shadow-sm);
}

.attachments-card__title {
  margin: 0 0 14px;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-subtle);
}
</style>
