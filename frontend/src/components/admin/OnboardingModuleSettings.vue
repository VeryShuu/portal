<template>
  <div class="onboarding-module-settings">
    <section class="settings-section">
      <h4 class="settings-section__title">
        {{ t('admin.modules.onboarding.title') }}
      </h4>
      <div class="settings-section__hint">
        {{ t('admin.modules.onboarding.hint') }}
      </div>
      <div
        class="branding-fields"
        style="margin-top:12px"
      >
        <n-form-item
          :label="t('admin.modules.onboarding.enabled')"
          style="margin-bottom:0"
        >
          <n-switch v-model:value="form.onboarding_enabled" />
        </n-form-item>
      </div>
      <div class="settings-actions">
        <n-button
          type="primary"
          :loading="saving"
          @click="onSave"
        >
          {{ t('common.save') }}
        </n-button>
      </div>
    </section>

    <section class="settings-section">
      <h4 class="settings-section__title">
        {{ t('admin.modules.onboarding.stepsTitle') }}
      </h4>
      <div class="settings-section__hint">
        {{ t('admin.modules.onboarding.stepsHint') }}
      </div>

      <div
        v-if="!hasCustom"
        class="settings-section__meta"
      >
        {{ t('admin.modules.onboarding.stepsUsingDefaults') }}
      </div>

      <div class="steps-list">
        <div
          v-for="(step, idx) in stepsForm"
          :key="step._key"
          class="step-item"
        >
          <div class="step-item__header">
            <span class="step-item__badge">
              #{{ idx + 1 }}
              <span
                v-if="step.id"
                class="step-item__id"
                :title="t('admin.modules.onboarding.stepIdHint')"
              >
                · {{ step.id }}
              </span>
            </span>
            <div class="step-item__controls">
              <n-button
                size="tiny"
                quaternary
                :disabled="idx === 0"
                :title="t('admin.modules.onboarding.stepMoveUp')"
                @click="moveStep(idx, -1)"
              >
                ↑
              </n-button>
              <n-button
                size="tiny"
                quaternary
                :disabled="idx === stepsForm.length - 1"
                :title="t('admin.modules.onboarding.stepMoveDown')"
                @click="moveStep(idx, 1)"
              >
                ↓
              </n-button>
              <n-button
                size="tiny"
                quaternary
                type="error"
                :title="t('admin.modules.onboarding.stepDelete')"
                @click="removeStep(idx)"
              >
                ✕
              </n-button>
            </div>
          </div>
          <n-form-item
            :label="t('admin.modules.onboarding.stepSelector')"
            style="margin-bottom:6px"
          >
            <n-select
              v-model:value="step.selector"
              filterable
              tag
              clearable
              :options="targetOptions"
              :placeholder="t('admin.modules.onboarding.stepSelectorPlaceholder')"
              :render-label="renderTargetLabel"
              :render-tag="renderTargetTag"
            />
            <template v-if="!isKnownTarget(step.selector) && step.selector">
              <div class="step-item__custom-hint">
                {{ t('admin.modules.onboarding.stepSelectorCustom') }}
              </div>
              <div
                v-if="step.selector.includes(':has(')"
                class="step-item__custom-hint"
              >
                {{ t('admin.modules.onboarding.stepSelectorBrowserHint') }}
              </div>
            </template>
          </n-form-item>
          <n-form-item
            :label="t('admin.modules.onboarding.stepTitle')"
            style="margin-bottom:6px"
          >
            <n-input v-model:value="step.title" />
          </n-form-item>
          <n-form-item
            :label="t('admin.modules.onboarding.stepBody')"
            style="margin-bottom:6px"
          >
            <n-input
              v-model:value="step.body"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
            />
          </n-form-item>
          <div class="step-item__footer">
            <n-checkbox v-model:checked="step.is_new">
              {{ t('admin.modules.onboarding.stepIsNew') }}
            </n-checkbox>
            <n-popconfirm
              :positive-text="t('common.confirm')"
              :negative-text="t('common.cancel')"
              @positive-click="onResetStepViews(step)"
            >
              <template #trigger>
                <n-button
                  size="tiny"
                  :disabled="!step.id || resettingStepId === step.id"
                  :loading="resettingStepId === step.id"
                >
                  {{ t('admin.modules.onboarding.stepResetViewsButton') }}
                </n-button>
              </template>
              {{ t('admin.modules.onboarding.stepResetViewsConfirm') }}
            </n-popconfirm>
          </div>
          <div
            v-if="step.is_new"
            class="step-item__new-hint"
          >
            {{ t('admin.modules.onboarding.stepIsNewHint') }}
          </div>
        </div>
      </div>

      <div class="settings-actions">
        <n-button
          size="small"
          @click="addStep"
        >
          + {{ t('admin.modules.onboarding.stepAdd') }}
        </n-button>
        <n-button
          size="small"
          :disabled="!stepsDirty || stepsSaving"
          @click="onDiscardSteps"
        >
          {{ t('common.cancel') }}
        </n-button>
        <n-popconfirm
          :positive-text="t('common.confirm')"
          :negative-text="t('common.cancel')"
          @positive-click="onResetSteps"
        >
          <template #trigger>
            <n-button
              size="small"
              :disabled="!hasCustom || stepsSaving"
            >
              {{ t('admin.modules.onboarding.stepsResetToDefaults') }}
            </n-button>
          </template>
          {{ t('admin.modules.onboarding.stepsResetConfirm') }}
        </n-popconfirm>
        <n-button
          type="primary"
          :loading="stepsSaving"
          :disabled="!stepsDirty"
          @click="onSaveSteps"
        >
          {{ t('common.save') }}
        </n-button>
      </div>
    </section>

    <section class="settings-section">
      <h4 class="settings-section__title">
        {{ t('admin.modules.onboarding.resetTitle') }}
      </h4>
      <div class="settings-section__hint">
        {{ t('admin.modules.onboarding.resetDescription') }}
      </div>
      <div
        v-if="lastResetTrigger"
        class="settings-section__meta"
      >
        {{ t('admin.modules.onboarding.lastReset', { date: formattedLastReset }) }}
      </div>
      <div class="settings-actions">
        <n-popconfirm
          :positive-text="t('common.confirm')"
          :negative-text="t('common.cancel')"
          @positive-click="onReset"
        >
          <template #trigger>
            <n-button
              type="warning"
              :loading="resetting"
            >
              {{ t('admin.modules.onboarding.resetButton') }}
            </n-button>
          </template>
          {{ t('admin.modules.onboarding.resetConfirm') }}
        </n-popconfirm>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NCheckbox,
  NFormItem,
  NInput,
  NPopconfirm,
  NSelect,
  NSwitch,
  type SelectOption,
  useMessage,
} from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '../../api'
import { useSystemSettingsQuery, type AdminSystemSettings } from '../../queries/admin'
import { queryKeys } from '../../queries/keys'
import {
  defaultOnboardingSteps,
  useOnboardingSettingsStore,
  type OnboardingStep,
} from '../../stores/onboarding'
import { getTourTargetOptions, tourTargetLabelFor } from '../../utils/tourTargets'

const { t, locale } = useI18n()
const message = useMessage()
const qc = useQueryClient()
const onboardingStore = useOnboardingSettingsStore()

const { data: settingsData } = useSystemSettingsQuery()

interface StepFormRow extends OnboardingStep {
  _key: string
}
let _keySeq = 0
function makeKey(): string {
  _keySeq += 1
  return `row-${Date.now().toString(36)}-${_keySeq}`
}
function toFormRow(s: OnboardingStep): StepFormRow {
  return {
    id: s.id ?? '',
    selector: s.selector,
    title: s.title,
    body: s.body ?? '',
    is_new: s.is_new === true,
    _key: makeKey(),
  }
}

const form = reactive({
  onboarding_enabled: true,
})
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
    // Only sync from the server when there are no unsaved local edits — this
    // prevents query invalidation (after a sibling PATCH) from clobbering the
    // admin's in-progress changes.
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
</script>

<style scoped>
.onboarding-module-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.settings-section {
  border: 1px solid var(--n-border-color, #eaeaea);
  border-radius: 10px;
  padding: 16px;
}
.settings-section__title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}
.settings-section__hint {
  font-size: 13px;
  color: var(--color-text-muted);
  line-height: 1.5;
}
.settings-section__meta {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-text-subtle);
}
.branding-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.settings-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}
.steps-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}
.step-item {
  border: 1px solid var(--n-border-color, #eaeaea);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--color-surface-alt, transparent);
}
.step-item__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.step-item__badge {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-subtle);
}
.step-item__controls {
  display: flex;
  gap: 4px;
}
.step-item__custom-hint {
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-subtle);
}
.step-item__id {
  margin-left: 6px;
  font-family: monospace;
  font-weight: 400;
  color: var(--color-text-subtle);
}
.step-item__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.step-item__new-hint {
  margin-top: 6px;
  font-size: 11px;
  color: var(--color-text-subtle);
}
</style>
