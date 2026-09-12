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

    <onboarding-steps-list
      :steps-form="stepsForm"
      :has-custom="hasCustom"
      :steps-dirty="stepsDirty"
      :steps-saving="stepsSaving"
      :resetting-step-id="resettingStepId"
      :target-options="targetOptions"
      :is-known-target="isKnownTarget"
      :render-target-label="renderTargetLabel"
      :render-target-tag="renderTargetTag"
      :seen-counts="stats?.seen_step_counts ?? null"
      :total-users="stats?.total_users ?? null"
      @add-step="addStep"
      @discard-steps="onDiscardSteps"
      @reset-steps="onResetSteps"
      @save-steps="onSaveSteps"
      @move-step="moveStep"
      @remove-step="removeStep"
      @reset-views="onResetStepViews"
    />

    <section class="settings-section">
      <h4 class="settings-section__title">
        {{ t('admin.modules.onboarding.stats.title') }}
      </h4>
      <div class="settings-section__hint">
        {{ t('admin.modules.onboarding.stats.hint') }}
      </div>
      <div
        v-if="stats"
        class="onboarding-stats"
      >
        <div class="onboarding-stats__row">
          <span>{{ t('admin.modules.onboarding.stats.total') }}</span>
          <b>{{ stats.total_users }}</b>
        </div>
        <div class="onboarding-stats__row">
          <span>{{ t('admin.modules.onboarding.stats.completed') }}</span>
          <b>{{ stats.completed }}</b>
        </div>
        <div class="onboarding-stats__row onboarding-stats__row--sub">
          <span>{{ t('admin.modules.onboarding.stats.viaFinished') }}</span>
          <b>{{ stats.completed_via_finished }}</b>
        </div>
        <div class="onboarding-stats__row onboarding-stats__row--sub">
          <span>{{ t('admin.modules.onboarding.stats.viaSkipped') }}</span>
          <b>{{ stats.completed_via_skipped }}</b>
        </div>
        <div class="onboarding-stats__row onboarding-stats__row--sub">
          <span>{{ t('admin.modules.onboarding.stats.viaUnknown') }}</span>
          <b>{{ statsViaUnknown }}</b>
        </div>
        <div class="onboarding-stats__row">
          <span>{{ t('admin.modules.onboarding.stats.notCompleted') }}</span>
          <b>{{ statsNotCompleted }}</b>
        </div>
      </div>
      <div
        v-else
        class="settings-section__meta"
      >
        {{ t('admin.modules.onboarding.stats.loading') }}
      </div>
      <div class="settings-actions">
        <n-button
          size="small"
          :loading="statsLoading"
          @click="loadStats"
        >
          {{ t('admin.modules.onboarding.stats.refresh') }}
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
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NFormItem, NPopconfirm, NSwitch } from 'naive-ui'
import OnboardingStepsList from './OnboardingStepsList.vue'
import { useOnboardingDraft } from './composables/useOnboardingDraft'

const { t } = useI18n()

const {
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
  stats,
  statsLoading,
  statsViaUnknown,
  statsNotCompleted,
  loadStats,
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
} = useOnboardingDraft()

onMounted(() => {
  void loadStats()
})
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
.onboarding-stats {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.onboarding-stats__row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.onboarding-stats__row--sub {
  padding-left: 14px;
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
