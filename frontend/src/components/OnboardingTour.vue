<template>
  <Teleport to="body">
    <div
      v-if="active"
      class="tour-overlay"
      aria-modal="true"
      role="dialog"
      :aria-label="t('onboarding.stepOf', { step: currentIndex + 1, total: steps.length })"
    >
      <div
        class="tour-backdrop"
        aria-hidden="true"
      />

      <div
        v-if="highlight"
        class="tour-highlight"
        :style="{
          top: `${highlight.top - 6}px`,
          left: `${highlight.left - 6}px`,
          width: `${highlight.width + 12}px`,
          height: `${highlight.height + 12}px`,
        }"
      />

      <div
        class="tour-popover"
        :style="popoverStyle"
        role="tooltip"
      >
        <div class="tour-popover__header">
          <span class="tour-step-badge">{{ t('onboarding.stepOf', { step: currentIndex + 1, total: steps.length }) }}</span>
          <button
            class="tour-skip"
            type="button"
            @click="skip"
          >
            {{ t('onboarding.skip') }}
          </button>
        </div>
        <h3 class="tour-popover__title">
          {{ currentStep?.title }}
        </h3>
        <p class="tour-popover__body">
          {{ currentStep?.body }}
        </p>
        <div class="tour-popover__footer">
          <div class="tour-dots">
            <span
              v-for="(s, i) in steps"
              :key="s.id || i"
              class="tour-dot"
              :class="{ 'tour-dot--active': i === currentIndex }"
            />
          </div>
          <button
            class="tour-btn tour-btn--primary"
            type="button"
            @click="next"
          >
            {{ currentIndex < steps.length - 1 ? t('onboarding.next') : t('onboarding.finish') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useOnboardingSettingsStore, type OnboardingStep } from '../stores/onboarding'
import { patchMyPreferences } from '../api/users'

const { t } = useI18n()
const auth = useAuthStore()
const onboardingSettings = useOnboardingSettingsStore()

const LS_KEY = 'portal-onboarding-done'
const LS_RESET_KEY = 'portal-onboarding-reset-trigger'
const MAX_SEEN_STEP_IDS = 500

const active = ref(false)
const currentIndex = ref(0)
const isDeltaMode = ref(false)
const activeStepIds = ref<string[]>([])

const allSteps = computed<OnboardingStep[]>(() => onboardingSettings.onboardingSteps)
const steps = computed<OnboardingStep[]>(() => {
  if (!activeStepIds.value.length) return allSteps.value
  const idx = new Map(allSteps.value.map((s) => [s.id, s]))
  return activeStepIds.value
    .map((id) => idx.get(id))
    .filter((s): s is OnboardingStep => Boolean(s))
})

const currentStep = computed<OnboardingStep | undefined>(() => steps.value[currentIndex.value])

interface Rect { top: number; left: number; width: number; height: number }
const highlight = ref<Rect | null>(null)
const popoverStyle = ref<Record<string, string>>({})

function getTarget(): Element | null {
  const cs = currentStep.value
  if (!cs || !cs.selector) return null
  try {
    return document.querySelector(cs.selector)
  } catch {
    return null
  }
}

async function positionStep() {
  await nextTick()
  if (!currentStep.value) {
    highlight.value = null
    return
  }
  const target = getTarget()
  const GAP = 16
  if (!target) {
    highlight.value = null
    popoverStyle.value = { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
    return
  }

  const rect = target.getBoundingClientRect()
  highlight.value = { top: rect.top + window.scrollY, left: rect.left + window.scrollX, width: rect.width, height: rect.height }

  const popoverWidth = 300
  const vpW = window.innerWidth
  const vpH = window.innerHeight

  let top: number
  let left: number

  if (rect.left > popoverWidth + GAP * 2) {
    left = rect.left - popoverWidth - GAP
    top = rect.top + rect.height / 2 - 80
  } else {
    left = rect.right + GAP
    top = rect.top + rect.height / 2 - 80
  }

  top = Math.max(GAP, Math.min(top, vpH - 200 - GAP))
  left = Math.max(GAP, Math.min(left, vpW - popoverWidth - GAP))

  popoverStyle.value = {
    top: `${top + window.scrollY}px`,
    left: `${left}px`,
    width: `${popoverWidth}px`,
  }
}

function next() {
  if (currentIndex.value < steps.value.length - 1) {
    currentIndex.value++
    positionStep()
  } else {
    finish()
  }
}

async function finish() {
  active.value = false
  const wasDelta = isDeltaMode.value
  const shownIds = steps.value.map((s) => s.id).filter(Boolean)
  const allKnownIds = new Set(allSteps.value.map((s) => s.id).filter(Boolean))
  try {
    const prevSeenRaw = auth.user?.preferences?.onboarding_seen_step_ids
    const prevSeen: string[] = Array.isArray(prevSeenRaw) ? (prevSeenRaw as string[]) : []
    // dedup + prune orphan ids no longer known + cap length
    let mergedSeen = Array.from(new Set([...prevSeen, ...shownIds])).filter((id) =>
      allKnownIds.has(id),
    )
    if (mergedSeen.length > MAX_SEEN_STEP_IDS) {
      mergedSeen = mergedSeen.slice(-MAX_SEEN_STEP_IDS)
    }

    const patch = wasDelta
      ? { onboarding_seen_step_ids: mergedSeen }
      : { onboarding_completed: true, onboarding_seen_step_ids: mergedSeen }
    await patchMyPreferences(patch)

    if (auth.user) {
      auth.user = {
        ...auth.user,
        preferences: {
          ...(auth.user.preferences || {}),
          ...(wasDelta ? {} : { onboarding_completed: true }),
          onboarding_seen_step_ids: mergedSeen,
        },
      }
    }

    if (!wasDelta) {
      localStorage.setItem(LS_KEY, '1')
      localStorage.setItem(LS_RESET_KEY, onboardingSettings.onboardingResetTrigger || '')
    }
  } catch {
    // non-critical: retry on next login
  } finally {
    isDeltaMode.value = false
    activeStepIds.value = []
  }
}

function skip() {
  finish()
}

function startTour() {
  if (!allSteps.value.length) return
  isDeltaMode.value = false
  activeStepIds.value = []
  currentIndex.value = 0
  active.value = true
  positionStep()
}

function startDeltaTour(stepIds: string[]) {
  if (!stepIds.length) return
  isDeltaMode.value = true
  activeStepIds.value = [...stepIds]
  currentIndex.value = 0
  active.value = true
  positionStep()
}

defineExpose({ startTour, startDeltaTour })

watch(currentIndex, () => positionStep())

let onResize: (() => void) | null = null
function onWindowChange() {
  if (active.value) positionStep()
}
if (typeof window !== 'undefined') {
  onResize = onWindowChange
  window.addEventListener('resize', onResize, { passive: true })
  window.addEventListener('scroll', onResize, { passive: true, capture: true })
}
onBeforeUnmount(() => {
  if (onResize && typeof window !== 'undefined') {
    window.removeEventListener('resize', onResize)
    window.removeEventListener('scroll', onResize, { capture: true } as EventListenerOptions)
  }
})

let autoStartedFor: string | null = null
async function maybeAutoStart(user: typeof auth.user) {
  // Reset guard when user logs out so the next user gets evaluated fresh
  if (!user) {
    autoStartedFor = null
    active.value = false
    return
  }
  const uid = String(user.id ?? '')
  if (autoStartedFor === uid) return
  autoStartedFor = uid

  if (!onboardingSettings.loaded) {
    try {
      await onboardingSettings.load()
    } catch {
      // non-critical
    }
  }

  if (!onboardingSettings.onboardingEnabled) return
  if (!allSteps.value.length) return

  const serverTrigger = onboardingSettings.onboardingResetTrigger || ''
  const lsTrigger = localStorage.getItem(LS_RESET_KEY) || ''
  const triggerChanged = serverTrigger !== lsTrigger

  if (triggerChanged) {
    localStorage.removeItem(LS_KEY)
  }

  const lsDone = localStorage.getItem(LS_KEY) === '1'
  const prefsDone = user.preferences?.onboarding_completed === true

  if (!lsDone && !prefsDone) {
    setTimeout(() => {
      if (!allSteps.value.length) return
      isDeltaMode.value = false
      activeStepIds.value = []
      currentIndex.value = 0
      active.value = true
      positionStep()
    }, 800)
    return
  }

  const seenIds: string[] = Array.isArray(user.preferences?.onboarding_seen_step_ids)
    ? (user.preferences.onboarding_seen_step_ids as string[])
    : []
  const newSteps = allSteps.value.filter(
    (s) => s.is_new === true && s.id && !seenIds.includes(s.id),
  )
  if (!newSteps.length) return

  setTimeout(() => {
    startDeltaTour(newSteps.map((s) => s.id))
  }, 800)
}

watch(
  () => auth.user,
  (user) => {
    void maybeAutoStart(user)
  },
  { immediate: true },
)
</script>

<style scoped>
.tour-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  pointer-events: none;
}

.tour-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  pointer-events: all;
  cursor: default;
}

.tour-highlight {
  position: absolute;
  border-radius: 8px;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.45), 0 0 0 3px var(--color-brand-red);
  z-index: 1;
  pointer-events: none;
}

.tour-popover {
  position: absolute;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.22);
  padding: 16px 18px 14px;
  pointer-events: all;
  z-index: 2;
}

.tour-popover__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.tour-step-badge {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-subtle);
}

.tour-skip {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: var(--color-text-muted);
  padding: 0;
  font-family: inherit;
  transition: color var(--t-fast);
}
.tour-skip:hover { color: var(--color-text); }

.tour-popover__title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
}

.tour-popover__body {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--color-text-muted);
  line-height: 1.55;
}

.tour-popover__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tour-dots {
  display: flex;
  gap: 5px;
}

.tour-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-border);
  transition: background var(--t-fast);
}
.tour-dot--active { background: var(--color-brand-red); }

.tour-btn--primary {
  background: var(--color-brand-red);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: background var(--t-fast);
}
.tour-btn--primary:hover { background: var(--color-brand-red-hover); }
</style>
