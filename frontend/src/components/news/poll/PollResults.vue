<template>
  <div class="news-poll__footer">
    <div class="news-poll__footer-left">
      <span
        v-if="!canSeeResults && isAuthenticated"
        class="news-poll__notice"
      >
        {{ resultsHiddenLabel }}
      </span>
      <span
        v-if="canSeeResults && poll.total_voters !== undefined && poll.total_voters !== null"
        class="news-poll__total"
      >
        {{ t('news.poll.voters', { count: poll.total_voters }) }}
      </span>
    </div>

    <div class="news-poll__footer-right">
      <n-button
        v-if="!isAuthenticated"
        type="primary"
        @click="$emit('login')"
      >
        {{ t('news.poll.noAuth') }}
      </n-button>
      <n-button
        v-else-if="!poll.is_closed && poll.can_vote && !hasVoted"
        type="primary"
        :disabled="!canSubmit || submitting"
        :loading="submitting"
        @click="$emit('submit-vote')"
      >
        {{ t('news.poll.vote') }}
      </n-button>
      <n-button
        v-else-if="!poll.is_closed && poll.allow_revote && hasVoted"
        type="tertiary"
        :loading="submitting"
        @click="$emit('revoke-vote')"
      >
        {{ t('news.poll.changeVote') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import type { NewsPollPublic } from '../../../api/news'

const { t } = useI18n()

defineProps<{
  poll: NewsPollPublic
  canSeeResults: boolean
  isAuthenticated: boolean
  resultsHiddenLabel: string
  hasVoted: boolean
  canSubmit: boolean
  submitting: boolean
}>()

defineEmits<{
  (e: 'submit-vote'): void
  (e: 'revoke-vote'): void
  (e: 'login'): void
}>()
</script>

<style scoped>
.news-poll__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.news-poll__notice {
  font-size: 13px;
  color: var(--color-text-muted);
}

.news-poll__total {
  font-size: 13px;
  color: var(--color-text);
}
</style>
