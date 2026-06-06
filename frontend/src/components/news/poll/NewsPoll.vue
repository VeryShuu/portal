<template>
  <n-spin
    v-if="isLoading"
    style="margin: 20px auto; display: block"
  />
  <div
    v-else-if="poll"
    class="news-poll"
  >
    <div class="news-poll__header">
      <h3 class="news-poll__title">
        <n-icon class="news-poll__title-icon">
          <BarChartOutline />
        </n-icon>
        {{ t('news.poll.title') }}
      </h3>
      <div class="news-poll__badges">
        <n-tag
          :type="poll.is_anonymous ? 'default' : 'success'"
          size="small"
          round
        >
          {{ poll.is_anonymous ? t('news.poll.anonymous') : t('news.poll.nonAnonymous') }}
        </n-tag>
        <n-tag
          v-if="poll.is_closed"
          type="warning"
          size="small"
          round
        >
          {{ t('news.poll.closed') }}
        </n-tag>
        <n-tag
          v-else-if="poll.closes_at"
          type="info"
          size="small"
          round
        >
          {{ closesAtText }}
        </n-tag>
      </div>
    </div>

    <div class="news-poll__questions">
      <PollQuestion
        v-for="(q, qIdx) in sortedQuestions"
        :key="q.id"
        :question="q"
        :question-index="qIdx"
        :sorted-opts="sortedOptions(q)"
        :has-images="questionHasImages(q)"
        :selected-ids="selectedByQuestion[q.id] || []"
        :custom-text="customTexts[q.id] || ''"
        :custom-checked="!!customSelected[q.id]"
        :has-voted="hasVoted"
        :submitting="submitting"
        :can-vote="!poll.is_closed && poll.can_vote"
        :is-authenticated="auth.isAuthenticated"
        :can-see-results="poll.can_see_results"
        @opt-click="handleOptionClick"
        @opt-change="handleSelect"
        @custom-toggle="handleCustomToggle"
        @custom-input="onQuestionCustomInput"
      />
    </div>

    <PollResults
      :poll="poll"
      :can-see-results="poll.can_see_results"
      :is-authenticated="auth.isAuthenticated"
      :results-hidden-label="resultsHiddenLabel"
      :has-voted="hasVoted"
      :can-submit="canSubmit"
      :submitting="submitting"
      @submit-vote="submitVote"
      @revoke-vote="revokeVote"
      @login="redirectToLogin"
    />

    <div
      v-if="canManage"
      class="news-poll__admin-actions"
    >
      <span class="news-poll__admin-label">{{ t('news.poll.adminBlockLabel') }}</span>
      <n-space size="small">
        <n-button
          v-if="!poll.is_closed"
          size="small"
          type="warning"
          ghost
          :loading="adminSubmitting"
          @click="closePoll"
        >
          {{ t('news.poll.actions.close') }}
        </n-button>
        <n-button
          v-if="poll.is_closed && canReopen"
          size="small"
          type="info"
          ghost
          :loading="adminSubmitting"
          @click="reopenPoll"
        >
          {{ t('news.poll.actions.reopen') }}
        </n-button>
        <n-button
          size="small"
          @click="openVotersModal"
        >
          {{ t('news.poll.showVoters') }}
        </n-button>
        <n-button
          size="small"
          type="error"
          ghost
          :loading="adminSubmitting"
          @click="confirmDeletePoll"
        >
          {{ t('news.poll.actions.delete') }}
        </n-button>
      </n-space>
    </div>

    <n-modal
      v-model:show="votersModalOpen"
      preset="card"
      :title="t('news.poll.votersModalTitle')"
      style="max-width: 640px"
      :bordered="false"
      size="huge"
    >
      <n-spin v-if="votersLoading" />
      <n-empty
        v-else-if="!voters || voters.length === 0"
        :description="t('news.poll.votersEmpty')"
      />
      <ul
        v-else
        class="news-poll__voters-list"
      >
        <li
          v-for="v in voters"
          :key="v.user.id"
          class="news-poll__voter"
        >
          <div class="news-poll__voter-name">
            {{ v.user.full_name || v.user.email }}
          </div>
          <div
            v-for="ans in v.answers"
            :key="ans.question_id"
            class="news-poll__voter-answer"
          >
            <div class="news-poll__voter-question">
              {{ ans.question_text || '' }}
            </div>
            <div
              v-if="ans.choices.length"
              class="news-poll__voter-choices"
            >
              {{ t('news.poll.votersChoicesPrefix') }}{{ ans.choices.map(c => c.text || '—').join(', ') }}
            </div>
            <div
              v-if="ans.custom_text"
              class="news-poll__voter-custom"
            >
              {{ t('news.poll.votersCustomPrefix') }}«{{ ans.custom_text }}»
            </div>
          </div>
          <div class="news-poll__voter-date">
            {{ formatVotedAt(v.voted_at) }}
          </div>
        </li>
      </ul>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import { NIcon, NTag, NButton, NSpace, NSpin, NModal, NEmpty, useMessage } from 'naive-ui'
import { BarChartOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../../../stores/auth'
import { useConfirmDialog } from '../../../composables/useConfirmDialog'
import type { NewsPollQuestionPublic } from '../../../api/news'
import {
  useNewsPollQuery,
  useNewsPollVotersQuery,
  useCloseNewsPollMutation,
  useReopenNewsPollMutation,
  useDeleteNewsPollMutation,
} from '../../../queries/news'
import { usePollVoting } from './composables/usePollVoting'
import { usePollResults } from './composables/usePollResults'
import PollQuestion from './PollQuestion.vue'
import PollResults from './PollResults.vue'

const props = defineProps<{
  newsId: string
  newsAuthorId?: string | null
}>()

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const message = useMessage()
const { confirm } = useConfirmDialog()

const { data: poll, isLoading } = useNewsPollQuery(() => props.newsId)

const closeMutation = useCloseNewsPollMutation()
const reopenMutation = useReopenNewsPollMutation()
const deleteMutation = useDeleteNewsPollMutation()

const adminSubmitting = ref(false)

const {
  selectedByQuestion,
  customTexts,
  customSelected,
  submitting,
  hasVoted,
  handleOptionClick,
  handleSelect,
  handleCustomToggle,
  handleCustomInput,
  canSubmit,
  submitVote,
  revokeVote,
} = usePollVoting(poll, () => props.newsId)

const {
  sortedQuestions,
  sortedOptions,
  questionHasImages,
  canReopen,
  closesAtText,
  resultsHiddenLabel,
  formatVotedAt,
} = usePollResults(poll)

const canManage = computed(() => auth.isEditor)

const votersModalOpen = ref(false)
const votersEnabled = ref(false)
const { data: voters, isLoading: votersLoading } = useNewsPollVotersQuery(
  () => props.newsId,
  { enabled: votersEnabled },
)

function openVotersModal() {
  votersEnabled.value = true
  votersModalOpen.value = true
}

function onQuestionCustomInput(q: NewsPollQuestionPublic, text: string) {
  customTexts[q.id] = text
  handleCustomInput(q)
}

async function closePoll() {
  adminSubmitting.value = true
  try {
    await closeMutation.mutateAsync(props.newsId)
    message.success(t('common.success', 'Успешно'))
  } catch (err: unknown) {
    const e = err as { response?: { _data?: { detail?: string } }; message?: string }
    message.error(e?.response?._data?.detail || e?.message || 'Ошибка')
  } finally {
    adminSubmitting.value = false
  }
}

async function reopenPoll() {
  adminSubmitting.value = true
  try {
    await reopenMutation.mutateAsync(props.newsId)
    message.success(t('common.success', 'Успешно'))
  } catch (err: unknown) {
    const e = err as { response?: { _data?: { detail?: string } }; message?: string }
    message.error(e?.response?._data?.detail || e?.message || 'Ошибка')
  } finally {
    adminSubmitting.value = false
  }
}

async function confirmDeletePoll() {
  const ok = await confirm({
    title: t('news.poll.actions.delete'),
    content: t('news.poll.actions.deleteConfirm'),
    positiveText: t('common.delete', 'Удалить'),
    negativeText: t('common.cancel', 'Отмена'),
    type: 'error',
  })
  if (!ok) return
  adminSubmitting.value = true
  try {
    await deleteMutation.mutateAsync(props.newsId)
    message.success(t('common.success', 'Успешно'))
  } catch (err: unknown) {
    const e = err as { response?: { _data?: { detail?: string } }; message?: string }
    message.error(e?.response?._data?.detail || e?.message || 'Ошибка')
  } finally {
    adminSubmitting.value = false
  }
}

function redirectToLogin() {
  router.push({ path: '/login', query: { redirect: route.fullPath } })
}
</script>

<style scoped>
.news-poll {
  margin-top: 24px;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-card);
}

.news-poll__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.news-poll__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-text-muted);
  margin: 0;
}

.news-poll__title-icon {
  font-size: 18px;
}

.news-poll__badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.news-poll__questions {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.news-poll__admin-actions {
  margin-top: 16px;
  padding: 10px 12px;
  border: 1px dashed var(--color-warning, #f0a020);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.news-poll__admin-label {
  font-size: 13px;
  color: var(--color-warning, #f0a020);
  font-weight: 600;
}

.news-poll__voters-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.news-poll__voter {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 10px;
}

.news-poll__voter-name {
  font-weight: 600;
  font-size: 14px;
}

.news-poll__voter-answer {
  margin-top: 6px;
  padding-left: 8px;
}

.news-poll__voter-question {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.news-poll__voter-choices,
.news-poll__voter-custom {
  font-size: 13px;
  color: var(--color-text);
}

.news-poll__voter-date {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 4px;
}
</style>
