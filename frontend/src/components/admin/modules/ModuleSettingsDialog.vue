<template>
  <template v-if="enabled">
    <n-form
      :model="ncForm"
      label-placement="top"
      style="margin-top:16px"
    >
      <div class="branding-fields">
        <n-form-item
          :label="t('admin.system.nextcloudUrl')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="ncForm.nextcloud_url"
            :placeholder="t('admin.system.nextcloudUrlPlaceholder')"
          />
        </n-form-item>
        <div class="email-row-2">
          <n-form-item
            :label="t('admin.system.ncServiceUsername')"
            style="margin-bottom:0;flex:1"
          >
            <n-input
              v-model:value="ncForm.nc_service_username"
              :placeholder="t('admin.system.ncServiceUsernamePlaceholder')"
            />
          </n-form-item>
          <n-form-item
            :label="t('admin.system.ncFilesRoot')"
            style="margin-bottom:0;flex:1"
          >
            <n-input
              v-model:value="ncForm.nc_files_root"
              :placeholder="t('admin.system.ncFilesRootPlaceholder')"
            />
          </n-form-item>
        </div>
        <div class="email-row-2">
          <n-form-item
            :label="t('admin.system.ncUserIdField')"
            style="margin-bottom:0;flex:1"
          >
            <n-input
              v-model:value="ncForm.nc_user_id_field"
              :placeholder="t('admin.system.ncUserIdFieldPlaceholder')"
              :input-props="{ autocomplete: 'username' }"
            />
          </n-form-item>
          <n-form-item
            :label="t('admin.system.ncServicePassword')"
            style="margin-bottom:0;flex:1"
          >
            <n-input
              v-model:value="ncForm.nc_service_password"
              type="password"
              show-password-on="click"
              :placeholder="ncPasswordSet ? t('admin.system.ncServicePasswordKeep') : t('admin.system.ncServicePasswordPlaceholder')"
              :input-props="{ autocomplete: 'new-password' }"
            />
          </n-form-item>
        </div>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.system.ncUserIdFieldHint') }}
        </div>
        <div
          class="email-actions"
          style="margin-top:8px"
        >
          <n-button
            :loading="ncTesting"
            :disabled="ncDirty"
            @click="$emit('testConnection')"
          >
            {{ t('admin.system.ncTestConnection') }}
          </n-button>
        </div>
        <div
          v-if="ncTestResult"
          class="kc-test-result"
          :class="ncTestResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
          style="margin-top:8px"
        >
          <div class="kc-test-result__title">
            {{ ncTestResult.ok ? t('admin.system.ncTestOk') : t('admin.system.ncTestFail') }}
          </div>
          <div
            v-if="ncTestResult.details"
            class="kc-test-result__details"
          >
            {{ ncTestResult.details }}
          </div>
        </div>
      </div>
    </n-form>
  </template>
  <div
    class="email-actions"
    style="margin-top:16px"
  >
    <n-button
      type="primary"
      :loading="saving"
      @click="$emit('save')"
    >
      {{ t('common.save') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NForm, NFormItem } from 'naive-ui'

const { t } = useI18n()

defineProps<{
  enabled: boolean
  ncForm: {
    nextcloud_url: string
    nc_service_username: string
    nc_files_root: string
    nc_user_id_field: string
    nc_service_password: string
  }
  ncPasswordSet: boolean
  ncTesting: boolean
  ncTestResult: { ok: boolean; details?: string } | null
  ncDirty: boolean
  saving: boolean
}>()

defineEmits<{
  (e: 'testConnection'): void
  (e: 'save'): void
}>()
</script>

<style scoped>
@import '../../../pages/admin/admin-tabs.css';
</style>
