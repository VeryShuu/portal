<template>
  <div class="article-feedback">
    <span class="article-feedback__label">{{ t('kb.feedbackLabel') }}</span>
    <button
      class="feedback-btn"
      :class="{ 'feedback-btn--active': userFeedback === true }"
      @click="$emit('feedback', true)"
    >
      👍 {{ helpfulCount }}
    </button>
    <button
      class="feedback-btn"
      :class="{ 'feedback-btn--active': userFeedback === false }"
      @click="$emit('feedback', false)"
    >
      👎 {{ notHelpfulCount }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  helpfulCount: number
  notHelpfulCount: number
  userFeedback: boolean | null | undefined
}>()

defineEmits<{
  (e: 'feedback', isHelpful: boolean): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.article-feedback {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
  padding: 16px 20px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.article-feedback__label {
  font-size: 14px;
  color: var(--color-text-muted);
  margin-right: 4px;
}

.feedback-btn {
  font-size: 16px;
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: none;
  cursor: pointer;
  transition: all var(--t-fast);
  font-family: inherit;
}
.feedback-btn:hover { border-color: var(--color-brand-sky); }
.feedback-btn--active { background: var(--color-brand-sky); color: #fff; border-color: var(--color-brand-sky); }
</style>
