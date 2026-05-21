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
      <fieldset
        v-for="(q, qIdx) in sortedQuestions"
        :key="q.id"
        class="news-poll__question-block"
        :disabled="submitting"
      >
        <legend class="news-poll__question">
          <span class="news-poll__question-number">{{ qIdx + 1 }}.</span>
          {{ q.text }}
          <n-tag
            v-if="!q.is_required"
            size="tiny"
            round
            type="default"
            class="news-poll__question-tag"
          >
            {{ t('news.poll.optional') }}
          </n-tag>
          <n-tag
            v-else
            size="tiny"
            round
            type="error"
            class="news-poll__question-tag"
          >
            {{ t('news.poll.required') }}
          </n-tag>
        </legend>

        <p
          v-if="q.is_multiple && !poll.is_closed && poll.can_vote && auth.isAuthenticated && q.max_choices"
          class="news-poll__info"
        >
          {{ t('news.poll.maxChoices', { count: q.max_choices }) }}
        </p>

        <div :class="['news-poll__options', { 'news-poll__options--grid': questionHasImages(q) }]">
          <div
            v-for="opt in sortedOptions(q)"
            :key="opt.id"
            :class="[
              'news-poll__option',
              { 'news-poll__option--selected': isSelected(q.id, opt.id) },
              { 'news-poll__option--voted': hasVoted },
              { 'news-poll__option--grid-item': questionHasImages(q) }
            ]"
            @click="handleOptionClick(q, opt.id)"
          >
            <template v-if="questionHasImages(q)">
              <div
                v-if="opt.image_url"
                class="news-poll__option-img-wrap"
              >
                <img
                  :src="opt.image_url"
                  :alt="opt.text || ''"
                  class="news-poll__option-img"
                >
              </div>
              <div class="news-poll__option-grid-content">
                <div class="news-poll__option-main">
                  <input
                    v-if="!poll.is_closed && poll.can_vote && auth.isAuthenticated"
                    :type="q.is_multiple ? 'checkbox' : 'radio'"
                    :name="'poll-' + q.id"
                    :value="opt.id"
                    :checked="isSelected(q.id, opt.id)"
                    class="news-poll__input"
                    @change="handleSelect(q, opt.id)"
                    @click.stop
                  >
                  <span class="news-poll__option-text">{{ opt.text || '' }}</span>
                </div>
                <div
                  v-if="poll.can_see_results && opt.votes_percent !== undefined && opt.votes_percent !== null"
                  class="news-poll__option-results"
                >
                  <div
                    class="news-poll__progress-bg"
                    :style="{ width: opt.votes_percent + '%' }"
                  />
                  <span class="news-poll__percent">{{ opt.votes_percent.toFixed(1) }}%</span>
                  <span class="news-poll__votes-count">({{ opt.votes_count }})</span>
                </div>
              </div>
            </template>

            <template v-else>
              <div class="news-poll__option-row">
                <div class="news-poll__option-main">
                  <input
                    v-if="!poll.is_closed && poll.can_vote && auth.isAuthenticated"
                    :type="q.is_multiple ? 'checkbox' : 'radio'"
                    :name="'poll-' + q.id"
                    :value="opt.id"
                    :checked="isSelected(q.id, opt.id)"
                    class="news-poll__input"
                    @change="handleSelect(q, opt.id)"
                    @click.stop
                  >
                  <span class="news-poll__option-text">{{ opt.text || '' }}</span>
                </div>
                <span
                  v-if="poll.can_see_results && opt.votes_percent !== undefined && opt.votes_percent !== null"
                  class="news-poll__percent"
                >
                  {{ opt.votes_percent.toFixed(1) }}%
                </span>
              </div>
              <div
                v-if="poll.can_see_results && opt.votes_percent !== undefined && opt.votes_percent !== null"
                class="news-poll__progressbar-wrap"
              >
                <div
                  class="news-poll__progressbar"
                  role="progressbar"
                  :aria-valuenow="opt.votes_percent"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  :style="{ width: opt.votes_percent + '%' }"
                />
              </div>
              <span
                v-if="poll.can_see_results && opt.votes_count !== undefined && opt.votes_count !== null"
                class="news-poll__votes-count-inline"
              >
                {{ opt.votes_count }} {{ t('news.poll.voters', { count: opt.votes_count }) }}
              </span>
            </template>
          </div>

          <!-- Custom answer row -->
          <div
            v-if="q.allow_custom_answer"
            class="news-poll__option news-poll__option--custom"
          >
            <div class="news-poll__option-row">
              <div class="news-poll__option-main news-poll__option-main--custom">
                <input
                  v-if="!poll.is_closed && poll.can_vote && auth.isAuthenticated"
                  :type="q.is_multiple ? 'checkbox' : 'radio'"
                  :name="'poll-' + q.id"
                  :checked="hasCustomSelected(q.id)"
                  class="news-poll__input"
                  @change="handleCustomToggle(q)"
                  @click.stop
                >
                <n-input
                  v-model:value="customTexts[q.id]"
                  :placeholder="t('news.poll.customPlaceholder')"
                  maxlength="500"
                  :disabled="poll.is_closed || !poll.can_vote || !auth.isAuthenticated"
                  size="small"
                  @input="handleCustomInput(q)"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Aggregated custom answers (visible to those who can see results) -->
        <div
          v-if="poll.can_see_results && q.custom_answers && q.custom_answers.length"
          class="news-poll__custom-answers"
        >
          <div class="news-poll__custom-answers-title">
            {{ t('news.poll.customAnswersTitle') }}
          </div>
          <ul class="news-poll__custom-answers-list">
            <li
              v-for="(ca, ci) in q.custom_answers"
              :key="ci"
              class="news-poll__custom-answer"
            >
              <span class="news-poll__custom-answer-text">«{{ ca.text }}»</span>
              <span
                v-if="ca.voter_name"
                class="news-poll__custom-answer-author"
              >
                — {{ ca.voter_name }}
              </span>
            </li>
          </ul>
        </div>
      </fieldset>
    </div>

    <div class="news-poll__footer">
      <div class="news-poll__footer-left">
        <span
          v-if="!poll.can_see_results && auth.isAuthenticated"
          class="news-poll__notice"
        >
          {{ resultsHiddenLabel }}
        </span>
        <span
          v-if="poll.can_see_results && poll.total_voters !== undefined && poll.total_voters !== null"
          class="news-poll__total"
        >
          {{ t('news.poll.voters', { count: poll.total_voters }) }}
        </span>
      </div>

      <div class="news-poll__footer-right">
        <n-button
          v-if="!auth.isAuthenticated"
          type="primary"
          @click="redirectToLogin"
        >
          {{ t('news.poll.noAuth') }}
        </n-button>
        <n-button
          v-else-if="!poll.is_closed && poll.can_vote && !hasVoted"
          type="primary"
          :disabled="!canSubmit || submitting"
          :loading="submitting"
          @click="submitVote"
        >
          {{ t('news.poll.vote') }}
        </n-button>
        <n-button
          v-else-if="!poll.is_closed && poll.allow_revote && hasVoted"
          type="tertiary"
          :loading="submitting"
          @click="revokeVote"
        >
          {{ t('news.poll.changeVote') }}
        </n-button>
      </div>
    </div>

    <!-- ADMIN CONTROLS -->
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
          type="primary"
          ghost
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
import { ref, computed, watch, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import { NIcon, NTag, NButton, NSpace, NSpin, NModal, NEmpty, NInput, useMessage } from 'naive-ui'
import { BarChartOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import type { NewsPollQuestionPublic, NewsPollOptionPublic, NewsPollAnswer } from '../api/news'
import {
  useNewsPollQuery,
  useNewsPollVotersQuery,
  useVoteNewsPollMutation,
  useRevokeNewsPollVoteMutation,
  useCloseNewsPollMutation,
  useReopenNewsPollMutation,
  useDeleteNewsPollMutation,
} from '../queries/news'

const props = defineProps<{
  newsId: string
  newsAuthorId?: string | null
}>()

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const message = useMessage()
const { confirm } = useConfirmDialog()

const { data: poll, isLoading } = useNewsPollQuery(() => props.newsId)

const voteMutation = useVoteNewsPollMutation()
const revokeMutation = useRevokeNewsPollVoteMutation()
const closeMutation = useCloseNewsPollMutation()
const reopenMutation = useReopenNewsPollMutation()
const deleteMutation = useDeleteNewsPollMutation()

// State: per-question selected option IDs and per-question custom texts
const selectedByQuestion = reactive<Record<string, string[]>>({})
const customTexts = reactive<Record<string, string>>({})
const customSelected = reactive<Record<string, boolean>>({})

const submitting = ref(false)
const adminSubmitting = ref(false)

function resetSelectionFromPoll() {
  for (const k of Object.keys(selectedByQuestion)) delete selectedByQuestion[k]
  for (const k of Object.keys(customTexts)) delete customTexts[k]
  for (const k of Object.keys(customSelected)) delete customSelected[k]
  if (!poll.value) return
  const myAnswers = poll.value.my_vote?.answers ?? []
  for (const q of poll.value.questions) {
    const a = myAnswers.find(x => x.question_id === q.id)
    selectedByQuestion[q.id] = a ? [...a.option_ids] : []
    customTexts[q.id] = a?.custom_text || ''
    customSelected[q.id] = !!(a?.custom_text && a.custom_text.length > 0)
  }
}

watch(poll, () => {
  resetSelectionFromPoll()
}, { immediate: true })

const sortedQuestions = computed<NewsPollQuestionPublic[]>(() => {
  if (!poll.value?.questions) return []
  return [...poll.value.questions].sort((a, b) => a.sort_order - b.sort_order)
})

function sortedOptions(q: NewsPollQuestionPublic): NewsPollOptionPublic[] {
  return [...q.options].sort((a, b) => a.sort_order - b.sort_order)
}

function questionHasImages(q: NewsPollQuestionPublic): boolean {
  return q.options.some(o => !!o.image_url)
}

const hasVoted = computed(() => !!poll.value?.my_vote)

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

function formatVotedAt(value: string): string {
  if (!value) return ''
  const date = new Date(value)
  const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
  return date.toLocaleString(lang, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

const canReopen = computed(() => {
  if (!poll.value?.closes_at) return true
  return new Date(poll.value.closes_at) > new Date()
})

const closesAtText = computed(() => {
  if (!poll.value?.closes_at) return ''
  const date = new Date(poll.value.closes_at)
  const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
  return date.toLocaleString(lang, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
})

const resultsHiddenLabel = computed(() => {
  if (!poll.value) return ''
  const vis = poll.value.results_visibility
  if (vis === 'after_vote') return t('news.poll.resultsAfterVote')
  if (vis === 'after_close') return t('news.poll.resultsAfterClose')
  if (vis === 'only_admin_editor') return t('news.poll.resultsAdminOnly')
  return ''
})

function isSelected(qid: string, optId: string): boolean {
  return (selectedByQuestion[qid] || []).includes(optId)
}

function hasCustomSelected(qid: string): boolean {
  return !!customSelected[qid]
}

function totalPicks(q: NewsPollQuestionPublic): number {
  return (selectedByQuestion[q.id]?.length || 0) + (customSelected[q.id] ? 1 : 0)
}

function handleOptionClick(q: NewsPollQuestionPublic, optId: string) {
  if (poll.value?.is_closed || !poll.value?.can_vote || !auth.isAuthenticated || hasVoted.value) return
  handleSelect(q, optId)
}

function handleSelect(q: NewsPollQuestionPublic, optId: string) {
  if (!poll.value) return
  const list = selectedByQuestion[q.id] || []
  if (q.is_multiple) {
    const idx = list.indexOf(optId)
    if (idx > -1) {
      list.splice(idx, 1)
    } else {
      const max = q.max_choices
      if (!max || totalPicks(q) < max) {
        list.push(optId)
      } else {
        message.warning(t('news.poll.maxChoices', { count: max }))
        return
      }
    }
    selectedByQuestion[q.id] = list
  } else {
    selectedByQuestion[q.id] = [optId]
    customSelected[q.id] = false
  }
}

function handleCustomToggle(q: NewsPollQuestionPublic) {
  if (q.is_multiple) {
    const next = !customSelected[q.id]
    if (next) {
      const max = q.max_choices
      if (max && totalPicks(q) >= max) {
        message.warning(t('news.poll.maxChoices', { count: max }))
        return
      }
    }
    customSelected[q.id] = next
  } else {
    customSelected[q.id] = true
    selectedByQuestion[q.id] = []
  }
}

function handleCustomInput(q: NewsPollQuestionPublic) {
  const v = (customTexts[q.id] || '').trim()
  if (v.length > 0 && !customSelected[q.id]) {
    handleCustomToggle(q)
  }
}

const canSubmit = computed(() => {
  if (!poll.value) return false
  for (const q of poll.value.questions) {
    const picks = totalPicks(q)
    if (q.is_required && picks === 0) return false
    if (customSelected[q.id] && !(customTexts[q.id] || '').trim()) return false
  }
  // require at least one answer overall
  return poll.value.questions.some(q => totalPicks(q) > 0)
})

function buildAnswers(): NewsPollAnswer[] {
  if (!poll.value) return []
  const out: NewsPollAnswer[] = []
  for (const q of poll.value.questions) {
    const opts = selectedByQuestion[q.id] || []
    const custom = customSelected[q.id] ? (customTexts[q.id] || '').trim() : ''
    if (opts.length === 0 && !custom) {
      if (!q.is_required) continue
    }
    out.push({ question_id: q.id, option_ids: opts, custom_text: custom || null })
  }
  return out
}

async function submitVote() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    await voteMutation.mutateAsync({
      newsId: props.newsId,
      dto: { answers: buildAnswers() },
    })
    message.success(t('common.success', 'Успешно'))
  } catch (err: unknown) {
    const e = err as { response?: { _data?: { detail?: string } }; message?: string }
    message.error(e?.response?._data?.detail || e?.message || 'Ошибка')
  } finally {
    submitting.value = false
  }
}

async function revokeVote() {
  submitting.value = true
  try {
    await revokeMutation.mutateAsync(props.newsId)
    resetSelectionFromPoll()
    message.success(t('common.success', 'Успешно'))
  } catch (err: unknown) {
    const e = err as { response?: { _data?: { detail?: string } }; message?: string }
    message.error(e?.response?._data?.detail || e?.message || 'Ошибка')
  } finally {
    submitting.value = false
  }
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

.news-poll__question-block {
  border: none;
  padding: 0;
  margin: 0;
}

.news-poll__question {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.news-poll__question-number {
  color: var(--color-text-muted);
}

.news-poll__question-tag {
  margin-left: 6px;
}

.news-poll__info {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-bottom: 8px;
}

.news-poll__options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.news-poll__options--grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.news-poll__option {
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  cursor: pointer;
  background: var(--color-bg);
  transition: background 0.15s ease;
}

.news-poll__option:hover {
  background: var(--color-bg-hover, rgba(0, 0, 0, 0.03));
}

.news-poll__option--selected {
  border-color: var(--color-primary, #2080f0);
  background: rgba(32, 128, 240, 0.06);
}

.news-poll__option--voted {
  cursor: default;
}

.news-poll__option--custom {
  background: var(--color-bg);
  border-style: dashed;
}

.news-poll__option-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.news-poll__option-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.news-poll__option-main--custom {
  width: 100%;
}

.news-poll__option-text {
  font-size: 14px;
}

.news-poll__progressbar-wrap {
  margin-top: 6px;
  height: 4px;
  background: var(--color-border);
  border-radius: 2px;
  overflow: hidden;
}

.news-poll__progressbar {
  height: 100%;
  background: var(--color-primary, #2080f0);
  transition: width 0.4s ease;
}

.news-poll__votes-count-inline {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 4px;
  display: inline-block;
}

.news-poll__percent {
  font-weight: 600;
  font-size: 14px;
}

.news-poll__custom-answers {
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--color-bg);
  border-radius: var(--radius-sm);
}

.news-poll__custom-answers-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
  margin-bottom: 6px;
}

.news-poll__custom-answers-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.news-poll__custom-answer-text {
  font-size: 13px;
}

.news-poll__custom-answer-author {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-left: 4px;
}

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

.news-poll__option-img-wrap {
  width: 100%;
  aspect-ratio: 16 / 10;
  overflow: hidden;
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
}

.news-poll__option-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.news-poll__option-results {
  position: relative;
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.news-poll__progress-bg {
  position: absolute;
  inset: 0;
  background: rgba(32, 128, 240, 0.08);
  z-index: 0;
}
</style>
