<template>
  <div class="branding-wrap">
    <div class="modules-hint">
      {{ t('admin.modules.tabHint') }}
    </div>

    <ModuleCard>
      <ModuleToggle
        :title="t('admin.modules.photos.title')"
        :hint="t('admin.modules.photos.hint')"
        :enabled="modulesForm.photos.enabled"
        :loading="photosToggling"
        :settings-label="t('admin.modules.openSettings')"
        @open-settings="goToPhotos"
        @update:enabled="onTogglePhotos"
      />
    </ModuleCard>

    <ModuleCard style="margin-top:16px">
      <ModuleToggle
        :title="t('admin.modules.meetings.title')"
        :hint="t('admin.modules.meetings.hint')"
        :enabled="modulesForm.meetings.enabled"
        :loading="meetingsToggling"
        :settings-label="t('admin.modules.openSettings')"
        @open-settings="goToMeetings"
        @update:enabled="onToggleMeetings"
      />
    </ModuleCard>

    <ModuleCard style="margin-top:16px">
      <ModuleToggle
        :title="t('admin.modules.nextcloud.title')"
        :hint="t('admin.modules.nextcloud.hint')"
        :enabled="modulesForm.nextcloud.enabled"
        @update:enabled="modulesForm.nextcloud.enabled = $event"
      />
      <ModuleSettingsDialog
        :enabled="modulesForm.nextcloud.enabled"
        :nc-form="ncForm"
        :nc-password-set="ncPasswordSet"
        :nc-testing="ncTesting"
        :nc-test-result="ncTestResult"
        :nc-dirty="ncDirty"
        :saving="nextcloudSaving"
        @test-connection="testNcConnection"
        @save="saveNextcloudAll"
      />
    </ModuleCard>

    <ModuleCard style="margin-top:16px">
      <ModuleToggle
        :title="t('admin.modules.onboarding.title')"
        :hint="t('admin.modules.onboarding.hint')"
        :enabled="onboardingSysData?.onboarding_enabled ?? true"
        :loading="onboardingToggling"
        :settings-label="t('admin.modules.openSettings')"
        @open-settings="openOnboardingDrawer"
        @update:enabled="onToggleOnboarding"
      />
    </ModuleCard>

    <n-drawer
      :show="manage.is('onboarding')"
      :width="520"
      @update:show="(v: boolean) => !v && manage.close()"
    >
      <n-drawer-content :title="t('admin.modules.onboarding.title')">
        <OnboardingModuleSettings />
      </n-drawer-content>
    </n-drawer>

    <ModuleCard style="margin-top:16px">
      <div class="branding-section__title">
        {{ t('admin.modules.videoGallery.title') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.modules.videoGallery.hint') }}
      </div>
      <div
        class="branding-fields"
        style="margin-top:16px"
      >
        <n-form-item
          :label="t('admin.system.videoGalleryUrl')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="videoGalleryUrl"
            :placeholder="t('admin.system.videoGalleryUrlPlaceholder')"
            clearable
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.system.videoGalleryUrlHint') }}
        </div>
      </div>
      <div
        class="email-actions"
        style="margin-top:16px"
      >
        <n-button
          type="primary"
          :loading="videoUrlSaving"
          @click="saveVideoUrl"
        >
          {{ t('common.save') }}
        </n-button>
      </div>
    </ModuleCard>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NFormItem, NDrawer, NDrawerContent } from 'naive-ui'
import ModuleCard from '../../../components/admin/modules/ModuleCard.vue'
import ModuleToggle from '../../../components/admin/modules/ModuleToggle.vue'
import ModuleSettingsDialog from '../../../components/admin/modules/ModuleSettingsDialog.vue'
import { useModulesState } from './composables/useModulesState'

const OnboardingModuleSettings = defineAsyncComponent(
  () => import('../../../components/admin/onboarding/OnboardingModuleSettings.vue'),
)

const { t } = useI18n()

const {
  modulesForm,
  ncForm,
  ncPasswordSet,
  videoGalleryUrl,
  nextcloudSaving,
  videoUrlSaving,
  photosToggling,
  meetingsToggling,
  ncTesting,
  ncTestResult,
  ncDirty,
  manage,
  onboardingToggling,
  onboardingSysData,
  saveNextcloudAll,
  saveVideoUrl,
  testNcConnection,
  onTogglePhotos,
  onToggleMeetings,
  onToggleOnboarding,
  openOnboardingDrawer,
  goToPhotos,
  goToMeetings,
} = useModulesState()
</script>

<style scoped>
@import '../admin-tabs.css';
.modules-hint {
  font-size: 13px;
  color: var(--color-text-muted, #999);
  margin-bottom: 16px;
}
</style>
