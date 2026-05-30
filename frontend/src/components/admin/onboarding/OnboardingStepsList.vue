<template>
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
      <onboarding-step-editor
        v-for="(step, idx) in stepsForm"
        :key="step._key"
        :step="step"
        :idx="idx"
        :is-last="idx === stepsForm.length - 1"
        :resetting-step-id="resettingStepId"
        :target-options="targetOptions"
        :is-known-target="isKnownTarget"
        :render-target-label="renderTargetLabel"
        :render-target-tag="renderTargetTag"
        @move="(delta) => $emit('move-step', idx, delta)"
        @remove="$emit('remove-step', idx)"
        @reset-views="$emit('reset-views', step)"
      />
    </div>

    <div class="settings-actions">
      <n-button
        size="small"
        @click="$emit('add-step')"
      >
        + {{ t('admin.modules.onboarding.stepAdd') }}
      </n-button>
      <n-button
        size="small"
        :disabled="!stepsDirty || stepsSaving"
        @click="$emit('discard-steps')"
      >
        {{ t('common.cancel') }}
      </n-button>
      <n-popconfirm
        :positive-text="t('common.confirm')"
        :negative-text="t('common.cancel')"
        @positive-click="$emit('reset-steps')"
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
        @click="$emit('save-steps')"
      >
        {{ t('common.save') }}
      </n-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NPopconfirm, type SelectOption } from 'naive-ui'
import type { VNode } from 'vue'
import OnboardingStepEditor from './OnboardingStepEditor.vue'
import type { StepFormRow } from './composables/useOnboardingDraft'

defineProps<{
  stepsForm: StepFormRow[]
  hasCustom: boolean
  stepsDirty: boolean
  stepsSaving: boolean
  resettingStepId: string
  targetOptions: SelectOption[]
  isKnownTarget: (selector: string) => boolean
  renderTargetLabel: (option: SelectOption) => VNode
  renderTargetTag: (opts: { option: SelectOption }) => VNode
}>()

defineEmits<{
  'add-step': []
  'discard-steps': []
  'reset-steps': []
  'save-steps': []
  'move-step': [idx: number, delta: number]
  'remove-step': [idx: number]
  'reset-views': [step: StepFormRow]
}>()

const { t } = useI18n()
</script>

<style scoped>
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
</style>
