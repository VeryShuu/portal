import { computed, h, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { type SelectOption, useMessage } from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '../../../../api'
import { useSystemSettingsQuery, type AdminSystemSettings } from '../../../../queries/admin'
import { queryKeys } from '../../../../queries/keys'
import {
  defaultOnboardingSteps,
  useOnboardingSettingsStore,
  type OnboardingStep,
} from '../../../../stores/onboarding'
import { getTourTargetOptions, tourTargetLabelFor } from '../../../../utils/tourTargets'

export interface StepFormRow extends OnboardingStep {
  _key: string
}

let _keySeq = 0

export function makeKey(): string {
  _keySeq += 1
  return `row-${Date.now().toString(36)}-${_keySeq}`
}

export function toFormRow(s: OnboardingStep): StepFormRow {
  return {
    id: s.id ?? '',
    selector: s.selector,
    title: s.title,
    body: s.body ?? '',
    is_new: s.is_new === true,
    _key: makeKey(),
  }
}

export function useOnboardingDraft() {
  const { t, locale } = useI18n()
  const message = useMessage()
  const qc = useQueryClient()
  const onboardingStore = useOnboardingSettingsStore()
  const { data: settingsData } = useSystemSettingsQuery()

  const form = reactive({ onboarding_enabled: true })
  const saving = ref(false)
  const resetting = ref(false)
  const stepsSaving = ref(false)
  const resettingStepId = ref<string>('')
  const lastResetTrigger = ref<string>('')
  const stepsForm = ref<StepFormRow[]>([])
  const hasCustom = ref(false)
  const stepsDirty = ref(false)

  function syncFromServer(data: AdminSystemSettings | null | undefined) {
    if (!data) return
    form.onboarding_enabled = data.onboarding_enabled
    lastResetTrigger.value = data.onboarding_reset_trigger || ''
    const override = data.onboarding_steps
    if (Array.isArray(override) && override.length > 0) {
      stepsForm.value = override.map(toFormRow)
      hasCustom.value = true
    } else {
      stepsForm.value = defaultOnboardingSteps().map(toFormRow)
      hasCustom.value = false
    }
    stepsDirty.value = false
  }

  watch(
    settingsData,
    (data) => {
      if (stepsDirty.value) return
      syncFromServer(data)
    },
    { immediate: true },
  )

  watch(
    stepsForm,
    () => {
      stepsDirty.value = true
    },
    { deep: true },
  )

  const formattedLastReset = computed(() => {
    if (!lastResetTrigger.value) return ''
    try {
      return new Date(lastResetTrigger.value).toLocaleString(locale.value === 'ru' ? 'ru-RU' : 'en-US')
    } catch {
      return lastResetTrigger.value
    }
  })

  const targetOptions = computed<SelectOption[]>(() => {
    void locale.value
    const opts = getTourTargetOptions()
    const groups = new Map<string, SelectOption[]>()
    for (const o of opts) {
      if (!groups.has(o.group)) groups.set(o.group, [])
      groups.get(o.group)!.push({ label: o.label, value: o.value })
    }
    const result: SelectOption[] = []
    for (const [group, children] of groups) {
      result.push({ type: 'group', label: group, key: group, children })
    }
    return result
  })

  function isKnownTarget(selector: string): boolean {
    return tourTargetLabelFor(selector) !== null
  }

  function renderTargetLabel(option: SelectOption) {
    return h(
      'div',
      { style: 'display:flex;flex-direction:column;gap:2px;padding:2px 0' },
      [
        h('span', { style: 'font-weight:500' }, String(option.label ?? '')),
        h(
          'span',
          { style: 'font-size:11px;color:var(--color-text-subtle);font-family:monospace' },
          String(option.value ?? ''),
        ),
      ],
    )
  }

  function renderTargetTag({ option }: { option: SelectOption }) {
    const value = String(option.value ?? '')
    const label = tourTargetLabelFor(value)
    if (label) {
      return h('span', null, [
        h('span', { style: 'font-weight:500' }, label),
        h(
          'span',
          { style: 'margin-left:8px;color:var(--color-text-subtle);font-family:monospace;font-size:12px' },
          value,
        ),
      ])
    }
    return h('span', { style: 'font-family:monospace' }, value)
  }

  function addStep() {
    stepsForm.value.push({
      id: '',
      selector: '',
      title: '',
      body: '',
      is_new: false,
      _key: makeKey(),
    })
  }

  function removeStep(idx: number) {
    stepsForm.value.splice(idx, 1)
  }

  function onDiscardSteps() {
    syncFromServer(settingsData.value)
  }

  function moveStep(idx: number, delta: number) {
    const newIdx = idx + delta
    if (newIdx < 0 || newIdx >= stepsForm.value.length) return
    const [item] = stepsForm.value.splice(idx, 1)
    stepsForm.value.splice(newIdx, 0, item)
  }

  async function onSave() {
    saving.value = true
    try {
      const updated = await api<AdminSystemSettings>('/admin/system/settings', {
        method: 'PATCH',
        body: { onboarding_enabled: form.onboarding_enabled },
      })
      qc.invalidateQueries({ queryKey: queryKeys.admin.systemSettings() })
      onboardingStore.setSettings({
        onboarding_enabled: updated.onboarding_enabled,
        onboarding_reset_trigger: updated.onboarding_reset_trigger,
      })
      message.success(t('admin.modules.saved'))
    } catch {
      message.error(t('errors.generic'))
    } finally {
      saving.value = false
    }
  }

  async function onSaveSteps() {
    for (const s of stepsForm.value) {
      if (!s.selector.trim() || !s.title.trim()) {
        message.error(t('admin.modules.onboarding.stepsValidationError'))
        return
      }
    }
    stepsSaving.value = true
    try {
      const payload = stepsForm.value.map((s) => ({
        id: (s.id ?? '').trim(),
        selector: s.selector.trim(),
        title: s.title.trim(),
        body: s.body ?? '',
        is_new: s.is_new === true,
      }))
      const updated = await api<AdminSystemSettings>('/admin/system/settings', {
        method: 'PATCH',
        body: { onboarding_steps: payload },
      })
      qc.invalidateQueries({ queryKey: queryKeys.admin.systemSettings() })
      onboardingStore.setSettings({
        onboarding_enabled: updated.onboarding_enabled,
        onboarding_reset_trigger: updated.onboarding_reset_trigger,
        onboarding_steps: updated.onboarding_steps ?? null,
      })
      if (Array.isArray(updated.onboarding_steps)) {
        stepsForm.value = updated.onboarding_steps.map(toFormRow)
      }
      hasCustom.value = true
      stepsDirty.value = false
      message.success(t('admin.modules.saved'))
    } catch {
      message.error(t('errors.generic'))
    } finally {
      stepsSaving.value = false
    }
  }

  async function onResetStepViews(step: OnboardingStep) {
    if (!step.id) {
      message.error(t('admin.modules.onboarding.stepResetViewsNoId'))
      return
    }
    resettingStepId.value = step.id
    try {
      const res = await api<{ updated: number; step_id: string }>(
        '/admin/system/settings/onboarding/steps/reset-views',
        { method: 'POST', body: { step_id: step.id } },
      )
      message.success(t('admin.modules.onboarding.stepResetViewsSuccess', { count: res.updated }))
    } catch {
      message.error(t('errors.generic'))
    } finally {
      resettingStepId.value = ''
    }
  }

  async function onResetSteps() {
    stepsSaving.value = true
    try {
      const updated = await api<AdminSystemSettings>('/admin/system/settings', {
        method: 'PATCH',
        body: { onboarding_steps: null },
      })
      qc.invalidateQueries({ queryKey: queryKeys.admin.systemSettings() })
      onboardingStore.setSettings({
        onboarding_enabled: updated.onboarding_enabled,
        onboarding_reset_trigger: updated.onboarding_reset_trigger,
        onboarding_steps: null,
      })
      stepsForm.value = defaultOnboardingSteps().map(toFormRow)
      hasCustom.value = false
      stepsDirty.value = false
      message.success(t('admin.modules.saved'))
    } catch {
      message.error(t('errors.generic'))
    } finally {
      stepsSaving.value = false
    }
  }

  async function onReset() {
    resetting.value = true
    try {
      const res = await api<{ updated: number; reset_trigger: string }>(
        '/admin/system/settings/onboarding/reset',
        { method: 'POST' },
      )
      lastResetTrigger.value = res.reset_trigger
      qc.invalidateQueries({ queryKey: queryKeys.admin.systemSettings() })
      onboardingStore.setSettings({
        onboarding_enabled: settingsData.value?.onboarding_enabled ?? onboardingStore.onboardingEnabled,
        onboarding_reset_trigger: res.reset_trigger,
      })
      message.success(t('admin.modules.onboarding.resetSuccess', { count: res.updated }))
    } catch {
      message.error(t('errors.generic'))
    } finally {
      resetting.value = false
    }
  }

  return {
    form,
    saving,
    resetting,
    stepsSaving,
    resettingStepId,
    lastResetTrigger,
    formattedLastReset,
    stepsForm,
    hasCustom,
    stepsDirty,
    targetOptions,
    isKnownTarget,
    renderTargetLabel,
    renderTargetTag,
    addStep,
    removeStep,
    moveStep,
    onDiscardSteps,
    onSave,
    onSaveSteps,
    onResetStepViews,
    onResetSteps,
    onReset,
  }
}
