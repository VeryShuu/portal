<template>
  <n-modal
    :show="show"
    :mask-closable="canDismiss"
    :close-on-esc="canDismiss"
    @update:show="requestClose"
    @after-leave="emit('close')"
  >
    <section
      class="test-panel"
      :class="{ 'test-panel--passing': phase === 'passing' }"
      role="dialog"
      aria-modal="true"
      aria-labelledby="learning-test-title"
    >
      <div class="test-panel__head">
        <h2
          id="learning-test-title"
          class="test-panel__title"
        >
          {{ item.title }}
        </h2>
        <n-button
          quaternary
          size="small"
          :disabled="starting || submitting"
          @click="requestClose"
        >
          {{ t('common.close') }}
        </n-button>
      </div>
      <div
        ref="bodyEl"
        class="test-panel__body"
      >
        <p
          v-if="loading"
          class="hint"
          role="status"
        >
          {{ t('common.loading') }}
        </p>
        <n-alert
          v-else-if="historyError"
          type="error"
          class="test-history-error"
        >
          {{ t('learning.test.historyError') }}
          <n-button
            size="small"
            @click="loadHistory"
          >
            {{ t('learning.page.retry') }}
          </n-button>
        </n-alert>
        <template v-else-if="phase !== 'passing' && historyReady">
          <div
            v-if="displayResult"
            class="test-score"
            :class="{ 'test-score--passed': displayResult.passed }"
          >
            <p class="test-score__label">
              {{ t('learning.test.latestResult') }}
            </p>
            <p class="test-score__value">
              {{ displayResult.score === null ? '—' : `${displayResult.score}%` }}
            </p>
            <p class="test-score__status">
              {{ displayResult.passed ? t('learning.test.passed') : t('learning.test.failed') }}
            </p>
          </div>
          <p
            v-else
            class="test-intro"
          >
            {{ t('learning.test.startHint') }}
          </p>
          <p class="hint test-attempts">
            {{ t('learning.test.attemptsLeft', { left: leftLabel }) }}
          </p>
          <p
            v-if="remaining === 0 && !lastOpenId"
            class="hint"
          >
            {{ t('learning.test.noAttemptsLeft') }}
          </p>
          <div class="test-panel__actions">
            <n-button
              v-if="canStart"
              type="primary"
              :loading="starting"
              @click="start"
            >
              {{ lastOpenId ? t('learning.test.resume') : displayResult ? t('learning.test.repeat') : t('learning.test.start') }}
            </n-button>
            <n-button
              :disabled="starting"
              @click="requestClose"
            >
              {{ t('learning.test.backToCourse') }}
            </n-button>
          </div>
        </template>
        <template v-else-if="phase === 'passing' && attemptView">
          <div class="passing-head">
            <p class="passing-head__progress">
              {{ t('learning.test.questionProgress', { n: currentIndex + 1, total: attemptView.questions.length }) }}
            </p>
            <p
              v-if="timeLeftText"
              class="timer"
              :class="{ 'timer--expired': timerExpired }"
            >
              {{ timerExpired
                ? t('learning.test.timeExpired')
                : t('learning.test.timeLeft', { time: timeLeftText }) }}
            </p>
          </div>
          <n-progress
            type="line"
            :percentage="answeredPercent"
            :height="6"
            :show-indicator="false"
            class="passing-bar"
            :aria-label="t('learning.test.questionOf', { n: answeredCount, total: attemptView.questions.length })"
          />
          <!-- Навигатор: прыжок к любому вопросу; заливка = отвечен -->
          <div
            class="navigator"
            role="navigation"
            :aria-label="t('learning.test.questionNavigator')"
          >
            <button
              v-for="(q, i) in attemptView.questions"
              :key="q.id"
              type="button"
              class="navigator__dot"
              :class="{
                'navigator__dot--current': i === currentIndex,
                'navigator__dot--answered': isAnswered(q.id),
              }"
              :aria-label="t('learning.test.gotoQuestion', { n: i + 1 })"
              :aria-current="i === currentIndex ? 'true' : undefined"
              @click="goTo(i)"
            >
              {{ i + 1 }}
            </button>
          </div>
          <p class="hint">
            {{ t('learning.test.questionOf', { n: answeredCount, total: attemptView.questions.length }) }}
          </p>
          <div
            v-if="currentQuestion"
            class="question"
          >
            <div class="question__text">
              {{ currentQuestion.text }}
            </div>
            <n-checkbox-group
              v-if="currentQuestion.multi"
              v-model:value="answers[currentQuestion.id]"
            >
              <n-checkbox
                v-for="o in currentQuestion.options"
                :key="o.id"
                :value="o.id"
                :label="o.text"
              />
            </n-checkbox-group>
            <n-radio-group
              v-else
              :value="answers[currentQuestion.id]?.[0] ?? null"
              @update:value="setSingleAnswer"
            >
              <n-radio
                v-for="o in currentQuestion.options"
                :key="o.id"
                :value="o.id"
              >
                {{ o.text }}
              </n-radio>
            </n-radio-group>
          </div>
          <p
            v-if="!allAnswered"
            class="hint"
          >
            {{ t('learning.test.answerAll') }}
          </p>
          <p
            v-if="timerExpired"
            class="hint hint--expired"
          >
            {{ t('learning.test.timeExpired') }}
          </p>
          <div class="passing-nav">
            <n-button
              :disabled="currentIndex === 0"
              @click="goTo(currentIndex - 1)"
            >
              {{ t('learning.test.prev') }}
            </n-button>
            <n-button
              v-if="!onLastQuestion"
              type="primary"
              secondary
              @click="goTo(currentIndex + 1)"
            >
              {{ t('learning.test.next') }}
            </n-button>
            <n-button
              v-else
              type="primary"
              :loading="submitting"
              :disabled="!allAnswered || timerExpired"
              @click="submit"
            >
              {{ t('learning.test.submit') }}
            </n-button>
          </div>
        </template>
      </div>
    </section>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NModal,
  NCheckbox,
  NCheckboxGroup,
  NProgress,
  NRadio,
  NRadioGroup,
} from 'naive-ui'
import {
  fetchAttempt,
  fetchMyAttempts,
  startAttempt,
  type AttemptResult,
  type AttemptView,
  type MyCourseItem,
} from '../../api/learning'
import { useSubmitAttemptMutation } from '../../queries/learning'
import { parseApiError } from '../../utils/parseApiError'
import { useDialog, useMessage } from 'naive-ui'

const props = defineProps<{ item: MyCourseItem; slug: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = useI18n()
const message = useMessage()
const dialog = useDialog()
const show = ref(true)

const phase = ref<'idle' | 'passing' | 'result'>('idle')
const loading = ref(true)
const historyError = ref(false)
const historyReady = ref(false)
const starting = ref(false)
const submitting = ref(false)
const attemptView = ref<AttemptView | null>(null)
const result = ref<AttemptResult | null>(null)
const lastResult = ref<AttemptResult | null>(null)
const lastOpenId = ref<string | null>(null)
const remaining = ref<number | null>(null)
const answers = reactive<Record<string, string[]>>({})

const submitMut = useSubmitAttemptMutation()
const displayResult = computed(() => result.value ?? lastResult.value)
const canDismiss = computed(() => phase.value !== 'passing' && !starting.value && !submitting.value)
const canStart = computed(() => historyReady.value && !loading.value
  && !historyError.value && (!!lastOpenId.value || remaining.value !== 0))

function requestClose() {
  if (starting.value || submitting.value) return
  if (phase.value === 'passing') {
    dialog.warning({
      title: t('learning.test.closeTitle'),
      content: t('learning.test.closeWarning'),
      positiveText: t('learning.test.leaveTest'),
      negativeText: t('learning.test.stayInTest'),
      onPositiveClick: () => { show.value = false },
    })
    return
  }
  show.value = false
}

const answeredCount = computed(
  () => Object.values(answers).filter((a) => a && a.length > 0).length,
)

// ── прохождение по одному вопросу (ревью 2026-08-31): листание с навигатором ──
const currentIndex = ref(0)
const bodyEl = ref<HTMLElement | null>(null)

const currentQuestion = computed(() => attemptView.value?.questions[currentIndex.value] ?? null)
const onLastQuestion = computed(
  () => !!attemptView.value && currentIndex.value >= attemptView.value.questions.length - 1,
)
const answeredPercent = computed(() => {
  const total = attemptView.value?.questions.length ?? 0
  if (total === 0) return 0
  return Math.round((answeredCount.value * 100) / total)
})

function isAnswered(questionId: string): boolean {
  return (answers[questionId]?.length ?? 0) > 0
}

function setSingleAnswer(optionId: string | null) {
  const q = currentQuestion.value
  if (!q) return
  answers[q.id] = optionId ? [optionId] : []
}

async function goTo(index: number) {
  if (!attemptView.value) return
  if (index < 0 || index >= attemptView.value.questions.length) return
  currentIndex.value = index
  // новый вопрос — с начала, а не на прокрутке предыдущего
  await nextTick()
  if (bodyEl.value) bodyEl.value.scrollTop = 0
}

// Пропущенный вопрос засчитывается бэкендом как неверный И расходует попытку —
// не даём отправить, пока не отвечено всё (ревью инкремента 6, P2).
const allAnswered = computed(
  () =>
    attemptView.value !== null &&
    attemptView.value.questions.length > 0 &&
    answeredCount.value === attemptView.value.questions.length,
)

const leftLabel = computed(() =>
  remaining.value === null ? t('learning.test.unlimited') : String(remaining.value),
)

// ── таймер попытки (этап 2): обратный отсчёт до expires_at (сервер —
// источник истины: просроченный submit бэкенд отклонит 409) ──
const nowTick = ref(Date.now())
const timerHandle = ref<ReturnType<typeof setInterval> | null>(null)
const expiresAtMs = computed(() => {
  const iso = attemptView.value?.expires_at
  return iso ? Date.parse(iso) : null
})
const secondsLeft = computed(() => {
  if (expiresAtMs.value === null) return null
  return Math.max(0, Math.floor((expiresAtMs.value - nowTick.value) / 1000))
})
const timerExpired = computed(() => secondsLeft.value === 0)
const timeLeftText = computed(() => {
  const s = secondsLeft.value
  if (s === null) return null
  const mm = Math.floor(s / 60)
  const ss = String(s % 60).padStart(2, '0')
  return `${mm}:${ss}`
})
watch(expiresAtMs, (v) => {
  if (timerHandle.value !== null) {
    clearInterval(timerHandle.value)
    timerHandle.value = null
  }
  if (v !== null) {
    nowTick.value = Date.now()
    timerHandle.value = setInterval(() => {
      nowTick.value = Date.now()
    }, 1000)
  }
})
// Ревью 2026-08-30: по истечении таймер тикает вхолостую до размонтирования —
// гасим интервал сразу, текст «истекло» остаётся как подсказка начать заново.
watch(timerExpired, (expired) => {
  if (expired && timerHandle.value !== null) {
    clearInterval(timerHandle.value)
    timerHandle.value = null
  }
})
onBeforeUnmount(() => {
  if (timerHandle.value !== null) clearInterval(timerHandle.value)
})

async function loadHistory() {
  loading.value = true
  historyError.value = false
  try {
    const history = await fetchMyAttempts(props.item.id)
    remaining.value = history.remaining_attempts ?? null
    const open = history.attempts.find((a) => a.status === 'open')
    lastOpenId.value = open?.id ?? null
    const lastSubmitted = history.attempts.find((a) => a.status === 'submitted')
    lastResult.value = null
    if (lastSubmitted) {
      lastResult.value = {
        id: lastSubmitted.id,
        status: lastSubmitted.status,
        score: lastSubmitted.score ?? null,
        passed: lastSubmitted.passed ?? null,
        remaining_attempts: history.remaining_attempts ?? null,
        started_at: lastSubmitted.started_at,
        submitted_at: lastSubmitted.submitted_at ?? null,
      }
    }
    historyReady.value = true
  } catch {
    historyError.value = true
    historyReady.value = false
  } finally {
    loading.value = false
  }
}

void loadHistory()

async function start() {
  if (!canStart.value || starting.value) return
  starting.value = true
  try {
    if (lastOpenId.value) {
      // возобновление открытой попытки — тот же порядок вопросов (снапшот)
      const resumed = await fetchAttempt(lastOpenId.value)
      if ('questions' in resumed) {
        beginAttempt(resumed)
        return
      }
    }
    beginAttempt(await startAttempt(props.item.id))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    starting.value = false
  }
}

function beginAttempt(attempt: AttemptView) {
  for (const key of Object.keys(answers)) delete answers[key]
  for (const question of attempt.questions) answers[question.id] = []
  attemptView.value = attempt
  result.value = null
  currentIndex.value = 0
  phase.value = 'passing'
}

async function submit() {
  if (!allAnswered.value || submitting.value || timerExpired.value) return
  if (!attemptView.value) return
  submitting.value = true
  try {
    const submitted = await submitMut.mutateAsync({
      attemptId: attemptView.value.id,
      answers: { ...answers },
      testItemId: props.item.id,
      slug: props.slug,
    })
    result.value = submitted
    lastResult.value = submitted
    remaining.value = submitted.remaining_attempts ?? null
    lastOpenId.value = null
    phase.value = 'result'
    attemptView.value = null
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    submitting.value = false
  }
}

</script>

<style scoped>
/* Teleported dialog: all layout and readable colors belong to this component,
   not the public learn shell, which is no longer a DOM ancestor. */
.test-panel {
  width: min(560px, calc(100vw - 32px));
  max-height: calc(100dvh - 48px);
  display: flex;
  flex-direction: column;
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.test-panel--passing {
  width: min(720px, calc(100vw - 32px));
}

.test-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 24px;
  border-bottom: 1px solid var(--color-border);
}

.test-panel__title {
  margin: 0;
  min-width: 0;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.test-panel__head > .n-button { flex-shrink: 0; }

.test-panel__body {
  min-height: 0;
  padding: 24px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.test-score {
  margin-bottom: 24px;
  padding: 20px 24px;
  color: var(--color-text);
  background: var(--color-bg-muted);
  border-left: 4px solid var(--color-warning);
  border-radius: var(--radius-md);
}

.test-score--passed {
  background: color-mix(in srgb, var(--color-success) 7%, var(--color-surface));
  border-left-color: var(--color-success);
}

.test-score__label {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
}

.test-score__value {
  margin: 4px 0;
  font-size: 48px;
  font-weight: 750;
  line-height: 1.2;
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
}

.test-score__status { margin: 0; font-weight: 600; }

.test-intro { margin: 0 0 20px; line-height: 1.6; }

.hint {
  margin: 0 0 16px;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.test-panel__actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
.test-history-error .n-button { display: block; margin-top: 12px; }

.question {
  margin-bottom: 16px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: var(--color-bg-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.question__text { font-weight: 600; line-height: 1.6; overflow-wrap: anywhere; }

.question :deep(.n-checkbox-group),
.question :deep(.n-radio-group) { display: flex; flex-direction: column; gap: 12px; }

.question :deep(.n-checkbox),
.question :deep(.n-radio) { min-height: 32px; align-items: flex-start; }

/* ── прохождение по одному вопросу ── */
.passing-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.passing-head__progress {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.passing-bar {
  margin-bottom: 14px;
}

.navigator {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 14px;
}

.navigator__dot {
  width: 32px;
  height: 32px;
  padding: 0;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  background: var(--color-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  cursor: pointer;
}

.navigator__dot--answered {
  color: var(--color-text);
  background: color-mix(in srgb, var(--color-brand-sky) 16%, var(--color-surface));
  border-color: var(--color-brand-sky);
}

.navigator__dot--current {
  color: #fff;
  background: var(--color-brand-navy, var(--color-brand-sky));
  border-color: var(--color-brand-navy, var(--color-brand-sky));
  font-weight: 700;
}

.navigator__dot:focus-visible {
  outline: 2px solid var(--color-brand-sky);
  outline-offset: 2px;
}

.navigator__dot:disabled { cursor: default; }

.hint--expired {
  color: var(--color-danger);
  font-weight: 600;
}

.passing-nav {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.timer { font-weight: 600; font-variant-numeric: tabular-nums; }
.timer--expired { color: var(--color-danger); }

@media (max-width: 639px) {
  .test-panel__head, .test-panel__body { padding: 18px; }
  .test-panel__actions .n-button,
  .passing-nav .n-button { min-height: 36px; }
  .question { padding: 14px; }
}
</style>
