<template>
  <div class="branding-wrap">
    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.monitoring.prometheusSection') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.monitoring.prometheusSectionHint') }}
      </div>
      <n-form
        :model="form"
        label-placement="top"
      >
        <input
          type="text"
          autocomplete="username"
          style="display:none"
        >
        <div class="branding-fields">
          <n-checkbox v-model:checked="form.prometheus_metrics_enabled">
            {{ t('admin.monitoring.prometheusEnabled') }}
          </n-checkbox>
          <div style="font-size:12px;color:var(--color-text-secondary)">
            {{ t('admin.monitoring.prometheusEnabledHint') }}
          </div>
          <n-form-item
            :label="t('admin.monitoring.metricsToken')"
            style="margin-bottom:0;margin-top:4px"
          >
            <n-input
              v-model:value="form.metrics_token"
              type="password"
              show-password-on="click"
              :placeholder="settings?.metrics_token_set ? t('admin.monitoring.metricsTokenKeep') : t('admin.monitoring.metricsTokenPlaceholder')"
              clearable
              :input-props="{ autocomplete: 'new-password' }"
            />
          </n-form-item>
          <div style="font-size:12px;color:var(--color-text-secondary)">
            {{ t('admin.monitoring.metricsTokenHint') }}
          </div>
        </div>
      </n-form>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.monitoring.loggingSection') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.monitoring.loggingSectionHint') }}
      </div>
      <div class="branding-fields">
        <n-form-item
          :label="t('admin.monitoring.logLevel')"
          style="margin-bottom:0;max-width:220px"
        >
          <n-select
            v-model:value="form.log_level"
            :options="logLevelOptions"
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.monitoring.logLevelHint') }}
        </div>
        <n-form-item
          :label="t('admin.monitoring.logSlowRequestMs')"
          style="margin-bottom:0;margin-top:4px;max-width:220px"
        >
          <n-input-number
            v-model:value="form.log_slow_request_ms"
            :min="0"
            :max="60000"
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.monitoring.logSlowRequestMsHint') }}
        </div>
        <n-form-item
          :label="t('admin.monitoring.logForceJson')"
          style="margin-bottom:0;margin-top:4px;max-width:260px"
        >
          <n-select
            v-model:value="form.log_force_json"
            :options="logForceJsonOptions"
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.monitoring.logForceJsonHint') }}
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.monitoring.workerSection') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.monitoring.workerSectionHint') }}
      </div>
      <div class="branding-fields">
        <n-form-item
          :label="t('admin.monitoring.arqMaxJobs')"
          style="margin-bottom:0;max-width:160px"
        >
          <n-input-number
            v-model:value="form.arq_max_jobs"
            :min="1"
            :max="200"
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.monitoring.arqMaxJobsHint') }}
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.monitoring.sentrySection') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.monitoring.sentrySectionHint') }}
      </div>
      <n-form
        :model="form"
        label-placement="top"
      >
        <input
          type="text"
          autocomplete="username"
          style="display:none"
        >
        <div class="branding-fields">
          <n-form-item
            :label="t('admin.monitoring.sentryDsn')"
            style="margin-bottom:0"
          >
            <n-input
              v-model:value="form.sentry_dsn"
              type="password"
              show-password-on="click"
              :placeholder="settings?.sentry_dsn_set ? t('admin.monitoring.sentryDsnKeep') : t('admin.monitoring.sentryDsnPlaceholder')"
              :input-props="{ autocomplete: 'new-password' }"
            />
          </n-form-item>
          <div style="font-size:12px;color:var(--color-text-secondary)">
            {{ t('admin.monitoring.sentryDsnHint') }}
          </div>
        </div>
      </n-form>
    </div>

    <div class="branding-section">
      <div class="email-actions">
        <n-button
          type="primary"
          :loading="saving"
          @click="save"
        >
          {{ t('admin.monitoring.save') }}
        </n-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NInput, NInputNumber, NSelect, NCheckbox, NForm, NFormItem, useMessage,
} from 'naive-ui'
import { api } from '../../../api'
import { useSystemSettingsQuery } from '../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'

const { t } = useI18n()
const message = useMessage()
const qc = useQueryClient()

interface SysSettingsOut {
  portal_base_url: string
  nextcloud_url: string
  nc_user_id_field: string
  nc_service_app_password_set: boolean
  max_upload_size_mb: number
  allowed_cidr: string
  prometheus_metrics_enabled: boolean
  news_attachment_max_size_mb: number
  kb_media_max_size_mb: number
  kb_attachment_max_size_mb: number
  log_level: string
  timezone: string
  sentry_dsn_set: boolean
  log_force_json: boolean | null
  log_slow_request_ms: number
  arq_max_jobs: number
  photo_gallery_url: string
  photo_gallery_mode: string
  photo_gallery_new_tab: boolean
  video_gallery_url: string
  nc_service_username: string
  nc_files_root: string
  kb_import_max_size_mb: number
  metrics_token_set: boolean
}

const logLevelOptions = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].map(v => ({ label: v, value: v }))

const logForceJsonOptions = computed(() => [
  { label: t('admin.monitoring.logForceJsonAuto'), value: 'null' },
  { label: t('admin.monitoring.logForceJsonJson'), value: 'true' },
  { label: t('admin.monitoring.logForceJsonText'), value: 'false' },
])

function logForceJsonToStr(v: boolean | null): string {
  if (v === true) return 'true'
  if (v === false) return 'false'
  return 'null'
}

function logForceJsonFromStr(v: string): boolean | null {
  if (v === 'true') return true
  if (v === 'false') return false
  return null
}

const saving = ref(false)
const loadError = ref(false)

const form = ref({
  prometheus_metrics_enabled: true,
  metrics_token: '',
  log_level: 'INFO',
  log_force_json: 'null',
  log_slow_request_ms: 1000,
  arq_max_jobs: 10,
  sentry_dsn: '',
})

const { data: settingsData, isError: settingsLoadFailed } = useSystemSettingsQuery()
const settings = computed(() => settingsData.value ?? null)

watch(settingsData, (data) => {
  if (data) {
    form.value.prometheus_metrics_enabled = data.prometheus_metrics_enabled
    form.value.metrics_token = ''
    form.value.log_level = data.log_level
    form.value.log_force_json = logForceJsonToStr(data.log_force_json)
    form.value.log_slow_request_ms = data.log_slow_request_ms
    form.value.arq_max_jobs = data.arq_max_jobs
    form.value.sentry_dsn = ''
    loadError.value = false
  }
}, { immediate: true })

watch(settingsLoadFailed, (failed) => {
  if (failed) loadError.value = true
})

async function save() {
  if (loadError.value) {
    message.error(t('admin.monitoring.loadFailedGuard'))
    return
  }
  saving.value = true
  try {
    await api<SysSettingsOut>('/admin/system/settings', {
      method: 'PATCH',
      body: {
        prometheus_metrics_enabled: form.value.prometheus_metrics_enabled,
        metrics_token: form.value.metrics_token || null,
        log_level: form.value.log_level,
        log_force_json: logForceJsonFromStr(form.value.log_force_json),
        log_slow_request_ms: form.value.log_slow_request_ms,
        arq_max_jobs: form.value.arq_max_jobs,
        sentry_dsn: form.value.sentry_dsn || null,
      },
    })
    form.value.sentry_dsn = ''
    form.value.metrics_token = ''
    qc.invalidateQueries({ queryKey: queryKeys.admin.systemSettings() })
    message.success(t('admin.monitoring.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    saving.value = false
  }
}


</script>

<style scoped>
@import '../admin-tabs.css';
</style>
