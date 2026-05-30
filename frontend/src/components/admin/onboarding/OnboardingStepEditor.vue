<template>
  <div class="step-item">
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
          @click="$emit('move', -1)"
        >
          ↑
        </n-button>
        <n-button
          size="tiny"
          quaternary
          :disabled="isLast"
          :title="t('admin.modules.onboarding.stepMoveDown')"
          @click="$emit('move', 1)"
        >
          ↓
        </n-button>
        <n-button
          size="tiny"
          quaternary
          type="error"
          :title="t('admin.modules.onboarding.stepDelete')"
          @click="$emit('remove')"
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
        @positive-click="$emit('reset-views')"
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
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NCheckbox,
  NFormItem,
  NInput,
  NPopconfirm,
  NSelect,
  type SelectOption,
} from 'naive-ui'
import type { VNode } from 'vue'
import type { StepFormRow } from './composables/useOnboardingDraft'

const props = defineProps<{
  step: StepFormRow
  idx: number
  isLast: boolean
  resettingStepId: string
  targetOptions: SelectOption[]
  isKnownTarget: (selector: string) => boolean
  renderTargetLabel: (option: SelectOption) => VNode
  renderTargetTag: (opts: { option: SelectOption }) => VNode
}>()

defineEmits<{
  move: [delta: number]
  remove: []
  'reset-views': []
}>()

const { t } = useI18n()

void props
</script>

<style scoped>
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
