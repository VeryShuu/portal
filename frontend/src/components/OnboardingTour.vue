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
        ref="popoverRef"
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
          <div class="tour-popover__actions">
            <button
              v-if="isDeltaMode"
              class="tour-btn tour-btn--ghost"
              type="button"
              @click="snooze"
            >
              {{ t('onboarding.later') }}
            </button>
            <button
              ref="primaryBtnRef"
              class="tour-btn tour-btn--primary"
              type="button"
              @click="next"
            >
              {{ currentIndex < steps.length - 1 ? t('onboarding.next') : t('onboarding.finish') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useOnboardingSettingsStore, type OnboardingStep } from '../stores/onboarding'
import { patchMyPreferences } from '../api/users'

const { t } = useI18n()
const auth = useAuthStore()
const onboardingSettings = useOnboardingSettingsStore()

// LS-ключи привязаны к id пользователя: на общем компьютере метка «пройдено»
// одного сотрудника не должна глушить тур для другого. *_LEGACY — ключи старого
// формата (без суффикса), вычищаются при входе.
const LS_DONE_KEY_LEGACY = 'portal-onboarding-done'
const LS_RESET_KEY_LEGACY = 'portal-onboarding-reset-trigger'
const MAX_SEEN_STEP_IDS = 500

function lsDoneKey(uid: string): string {
  return `${LS_DONE_KEY_LEGACY}:${uid}`
}

function lsResetKey(uid: string): string {
  return `${LS_RESET_KEY_LEGACY}:${uid}`
}

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
const primaryBtnRef = ref<HTMLButtonElement | null>(null)
const popoverRef = ref<HTMLElement | null>(null)

// Тот же порог, что в useBreakpoints (BP_MD).
const MOBILE_BP = 768

// Стандартные цели меню хранятся селектором `.n-menu-item:has([data-tour-id="x"])`,
// но вычислять :has() нельзя — резолвим через data-tour-id + closest(): работает
// в браузерах без поддержки :has() (см. docs/onboarding.md §6.2).
const MENU_TARGET_RE = /^\.n-menu-item:has\(\[data-tour-id="([\w-]+)"\]\)$/

let restoreFocusEl: HTMLElement | null = null

function findStepTarget(selector: string): Element | null {
  const menuMatch = MENU_TARGET_RE.exec(selector)
  if (menuMatch) {
    const anchor = document.querySelector(`[data-tour-id="${menuMatch[1]}"]`)
    return anchor?.closest('.n-menu-item') ?? anchor ?? null
  }
  try {
    return document.querySelector(selector)
  } catch {
    return null
  }
}

function getTarget(): Element | null {
  const cs = currentStep.value
  if (!cs || !cs.selector) return null
  return findStepTarget(cs.selector)
}

function hasTarget(step: OnboardingStep): boolean {
  if (!step.selector) return false
  return findStepTarget(step.selector) !== null
}

function captureFocus() {
  if (!active.value && document.activeElement instanceof HTMLElement) {
    restoreFocusEl = document.activeElement
  }
}

function focusPrimary() {
  void nextTick(() => primaryBtnRef.value?.focus())
}

function restoreFocus() {
  restoreFocusEl?.focus()
  restoreFocusEl = null
}

let positioning = false
async function positionStep() {
  await nextTick()
  if (positioning) return
  positioning = true
  try {
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

    // Цель может быть за пределами экрана (низкое окно, длинное меню) —
    // сначала прокручиваем её в центр видимости, иначе подсветка уйдёт за край.
    if (typeof target.scrollIntoView === 'function') {
      target.scrollIntoView({ block: 'center', inline: 'nearest' })
    }

    // Оверлей position:fixed ⇒ координаты viewport'а; getBoundingClientRect уже
    // viewport-relative, прибавлять scrollY/scrollX нельзя.
    const rect = target.getBoundingClientRect()
    highlight.value = { top: rect.top, left: rect.left, width: rect.width, height: rect.height }

    // Мобильная раскладка: карточка-«шторка» у нижнего края, подсветка остаётся.
    if (window.innerWidth < MOBILE_BP) {
      popoverStyle.value = {
        top: 'auto',
        left: `${GAP}px`,
        right: `${GAP}px`,
        bottom: `${GAP}px`,
        width: 'auto',
        transform: 'none',
      }
      return
    }

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
      top: `${top}px`,
      left: `${left}px`,
      width: `${popoverWidth}px`,
    }
  } finally {
    positioning = false
  }
}

function next() {
  if (currentIndex.value < steps.value.length - 1) {
    currentIndex.value++
    positionStep()
    focusPrimary()
  } else {
    finish('finished')
  }
}

async function finish(via: 'finished' | 'skipped' = 'finished') {
  active.value = false
  const wasDelta = isDeltaMode.value
  // Засчитываются только реально показанные шаги: «Пропустить» в середине тура
  // не помечает непоказанные просмотренными — их ещё предложат в следующий раз.
  const shownIds = steps.value.slice(0, currentIndex.value + 1).map((s) => s.id).filter(Boolean)
  const allKnownIds = new Set(allSteps.value.map((s) => s.id).filter(Boolean))
  const uid = String(auth.user?.id ?? '')
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
      : {
          onboarding_completed: true,
          onboarding_completed_via: via,
          onboarding_seen_step_ids: mergedSeen,
        }
    await patchMyPreferences(patch)

    if (auth.user) {
      auth.user = {
        ...auth.user,
        preferences: {
          ...(auth.user.preferences || {}),
          ...(wasDelta
            ? {}
            : { onboarding_completed: true, onboarding_completed_via: via }),
          onboarding_seen_step_ids: mergedSeen,
        },
      }
    }

    if (!wasDelta && uid) {
      localStorage.setItem(lsDoneKey(uid), '1')
      localStorage.setItem(lsResetKey(uid), onboardingSettings.onboardingResetTrigger || '')
    }
  } catch {
    // non-critical: retry on next login
  } finally {
    isDeltaMode.value = false
    activeStepIds.value = []
    restoreFocus()
  }
}

function skip() {
  finish('skipped')
}

// «Напомнить позже» (только delta-режим): закрыть без записи просмотров —
// все новинки этого мини-тура предложатся снова при следующем входе.
function snooze() {
  if (!isDeltaMode.value) return
  active.value = false
  isDeltaMode.value = false
  activeStepIds.value = []
  restoreFocus()
}

function startTour() {
  // Ручной перезапуск из меню пользователя уважает выключенный модуль.
  if (!onboardingSettings.onboardingEnabled) return
  // Шаги без цели в DOM (выключенный модуль, чужой пункт меню) не показываются.
  const playable = allSteps.value.filter(hasTarget)
  if (!playable.length) return
  captureFocus()
  isDeltaMode.value = false
  activeStepIds.value = playable.map((s) => s.id).filter(Boolean)
  currentIndex.value = 0
  active.value = true
  positionStep()
  focusPrimary()
}

function startDeltaTour(stepIds: string[]) {
  if (!stepIds.length) return
  const idx = new Map(allSteps.value.map((s) => [s.id, s]))
  const playable = stepIds
    .map((id) => idx.get(id))
    .filter((s): s is OnboardingStep => Boolean(s && hasTarget(s)))
  if (!playable.length) return
  captureFocus()
  isDeltaMode.value = true
  activeStepIds.value = playable.map((s) => s.id).filter(Boolean)
  currentIndex.value = 0
  active.value = true
  positionStep()
  focusPrimary()
}

defineExpose({ startTour, startDeltaTour })

watch(currentIndex, () => positionStep())

let onResize: (() => void) | null = null
function onWindowChange() {
  if (active.value) positionStep()
}
function onKeydown(e: KeyboardEvent) {
  if (!active.value) return
  if (e.key === 'Escape') {
    skip()
    return
  }
  // Фокус-трап: Tab не уходит под затемнение — цикл внутри карточки.
  if (e.key === 'Tab') {
    const pop = popoverRef.value
    if (!pop) return
    const focusables = Array.from(
      pop.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    )
    if (!focusables.length) return
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    const current = document.activeElement
    if (!pop.contains(current)) {
      e.preventDefault()
      first.focus()
    } else if (e.shiftKey && current === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && current === last) {
      e.preventDefault()
      first.focus()
    }
  }
}
onMounted(() => {
  if (typeof window !== 'undefined') {
    onResize = onWindowChange
    window.addEventListener('resize', onResize, { passive: true })
    window.addEventListener('scroll', onWindowChange, { passive: true, capture: true })
    window.addEventListener('keydown', onKeydown)
  }
})
onBeforeUnmount(() => {
  if (onResize && typeof window !== 'undefined') {
    window.removeEventListener('resize', onResize)
    window.removeEventListener('scroll', onWindowChange, { capture: true } as EventListenerOptions)
    window.removeEventListener('keydown', onKeydown)
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

  // Вычистить ключи старого формата (до привязки LS к пользователю).
  localStorage.removeItem(LS_DONE_KEY_LEGACY)
  localStorage.removeItem(LS_RESET_KEY_LEGACY)

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
  const lsTrigger = localStorage.getItem(lsResetKey(uid)) || ''
  const triggerChanged = serverTrigger !== lsTrigger

  if (triggerChanged) {
    localStorage.removeItem(lsDoneKey(uid))
  }

  const lsDone = localStorage.getItem(lsDoneKey(uid)) === '1'
  const prefsDone = user.preferences?.onboarding_completed === true

  if (!lsDone && !prefsDone) {
    setTimeout(() => {
      if (auth.user) startTour()
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
    if (auth.user) startDeltaTour(newSteps.map((s) => s.id))
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
  box-sizing: border-box;
  max-width: calc(100vw - 32px);
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
  flex-wrap: wrap;
  gap: 10px;
}

.tour-popover__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
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

.tour-btn--ghost {
  background: transparent;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 5px 12px;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: color var(--t-fast), border-color var(--t-fast);
}
.tour-btn--ghost:hover { color: var(--color-text); border-color: var(--color-text-muted); }

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
