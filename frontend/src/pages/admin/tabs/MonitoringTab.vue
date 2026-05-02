<template>
  <div class="branding-wrap">

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.monitoring.prometheusSection') }}</div>
      <div class="branding-section__hint">{{ t('admin.monitoring.prometheusSectionHint') }}</div>
      <div class="branding-fields">
        <n-checkbox v-model:checked="form.prometheus_metrics_enabled">
          {{ t('admin.monitoring.prometheusEnabled') }}
        </n-checkbox>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.monitoring.prometheusEnabledHint') }}</div>
        <n-form-item :label="t('admin.monitoring.metricsToken')" style="margin-bottom:0;margin-top:4px">
          <n-input
            v-model:value="form.metrics_token"
            type="password"
            show-password-on="click"
            :placeholder="settings?.metrics_token_set ? t('admin.monitoring.metricsTokenKeep') : t('admin.monitoring.metricsTokenPlaceholder')"
            clearable
            :input-props="{ autocomplete: 'new-password' }"
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.monitoring.metricsTokenHint') }}</div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.monitoring.loggingSection') }}</div>
      <div class="branding-section__hint">{{ t('admin.monitoring.loggingSectionHint') }}</div>
      <div class="branding-fields">
        <n-form-item :label="t('admin.monitoring.logLevel')" style="margin-bottom:0;max-width:220px">
          <n-select v-model:value="form.log_level" :options="logLevelOptions" />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.monitoring.logLevelHint') }}</div>
        <n-form-item :label="t('admin.monitoring.logSlowRequestMs')" style="margin-bottom:0;margin-top:4px;max-width:220px">
          <n-input-number v-model:value="form.log_slow_request_ms" :min="0" :max="60000" />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.monitoring.logSlowRequestMsHint') }}</div>
        <n-form-item :label="t('admin.monitoring.logForceJson')" style="margin-bottom:0;margin-top:4px;max-width:260px">
          <n-select v-model:value="form.log_force_json" :options="logForceJsonOptions" />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.monitoring.logForceJsonHint') }}</div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.monitoring.workerSection') }}</div>
      <div class="branding-section__hint">{{ t('admin.monitoring.workerSectionHint') }}</div>
      <div class="branding-fields">
        <n-form-item :label="t('admin.monitoring.arqMaxJobs')" style="margin-bottom:0;max-width:160px">
          <n-input-number v-model:value="form.arq_max_jobs" :min="1" :max="200" />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.monitoring.arqMaxJobsHint') }}</div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.monitoring.sentrySection') }}</div>
      <div class="branding-section__hint">{{ t('admin.monitoring.sentrySectionHint') }}</div>
      <div class="branding-fields">
        <n-form-item :label="t('admin.monitoring.sentryDsn')" style="margin-bottom:0">
          <n-input
            v-model:value="form.sentry_dsn"
            type="password"
            show-password-on="click"
            :placeholder="settings?.sentry_dsn_set ? t('admin.monitoring.sentryDsnKeep') : t('admin.monitoring.sentryDsnPlaceholder')"
            :input-props="{ autocomplete: 'new-password' }"
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.monitoring.sentryDsnHint') }}</div>
      </div>
    </div>

    <div class="branding-section">
      <div class="email-actions">
        <n-button type="primary" :loading="saving" @click="save">
          {{ t('admin.monitoring.save') }}
        </n-button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NInput, NInputNumber, NSelect, NCheckbox, NFormItem, useMessage,
} from 'naive-ui'
import { api } from '../../../api'

const { t } = useI18n()
const message = useMessage()

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

const settings = ref<SysSettingsOut | null>(null)
const saving = ref(false)
const loadError = ref(false)

const form = ref({
  portal_base_url: '',
  nextcloud_url: '',
  nc_user_id_field: '',
  nc_service_password: '',
  max_upload_size_mb: 100,
  allowed_cidr: '',
  prometheus_metrics_enabled: true,
  news_attachment_max_size_mb: 50,
  kb_media_max_size_mb: 20,
  kb_attachment_max_size_mb: 50,
  log_level: 'INFO',
  timezone: 'Europe/Moscow',
  sentry_dsn: '',
  log_force_json: 'null',
  log_slow_request_ms: 1000,
  arq_max_jobs: 10,
  photo_gallery_url: '',
  photo_gallery_mode: 'external',
  photo_gallery_new_tab: false,
  video_gallery_url: '',
  nc_service_username: 'portal-svc',
  nc_files_root: 'PortalFiles',
  kb_import_max_size_mb: 50,
  metrics_token: '',
})

async function load() {
  try {
    const data = await api<SysSettingsOut>('/admin/system/settings')
    settings.value = data
    form.value.portal_base_url = data.portal_base_url
    form.value.nextcloud_url = data.nextcloud_url
    form.value.nc_user_id_field = data.nc_user_id_field
    form.value.nc_service_password = ''
    form.value.max_upload_size_mb = data.max_upload_size_mb
    form.value.allowed_cidr = data.allowed_cidr
    form.value.prometheus_metrics_enabled = data.prometheus_metrics_enabled
    form.value.news_attachment_max_size_mb = data.news_attachment_max_size_mb
    form.value.kb_media_max_size_mb = data.kb_media_max_size_mb
    form.value.kb_attachment_max_size_mb = data.kb_attachment_max_size_mb
    form.value.log_level = data.log_level
    form.value.timezone = data.timezone
    form.value.sentry_dsn = ''
    form.value.log_force_json = logForceJsonToStr(data.log_force_json)
    form.value.log_slow_request_ms = data.log_slow_request_ms
    form.value.arq_max_jobs = data.arq_max_jobs
    form.value.photo_gallery_url = data.photo_gallery_url
    form.value.photo_gallery_mode = data.photo_gallery_mode
    form.value.photo_gallery_new_tab = data.photo_gallery_new_tab
    form.value.video_gallery_url = data.video_gallery_url
    form.value.nc_service_username = data.nc_service_username
    form.value.nc_files_root = data.nc_files_root
    form.value.kb_import_max_size_mb = data.kb_import_max_size_mb
    form.value.metrics_token = ''
    loadError.value = false
  } catch {
    loadError.value = true
    message.error(t('errors.generic'))
  }
}

async function save() {
  if (loadError.value) {
    message.error(t('admin.monitoring.loadFailedGuard'))
    return
  }
  saving.value = true
  try {
    const body = {
      portal_base_url: form.value.portal_base_url,
      nextcloud_url: form.value.nextcloud_url,
      nc_user_id_field: form.value.nc_user_id_field,
      nc_service_app_password: form.value.nc_service_password || null,
      max_upload_size_mb: form.value.max_upload_size_mb,
      allowed_cidr: form.value.allowed_cidr,
      prometheus_metrics_enabled: form.value.prometheus_metrics_enabled,
      news_attachment_max_size_mb: form.value.news_attachment_max_size_mb,
      kb_media_max_size_mb: form.value.kb_media_max_size_mb,
      kb_attachment_max_size_mb: form.value.kb_attachment_max_size_mb,
      log_level: form.value.log_level,
      timezone: form.value.timezone,
      sentry_dsn: form.value.sentry_dsn || null,
      log_force_json: logForceJsonFromStr(form.value.log_force_json),
      log_slow_request_ms: form.value.log_slow_request_ms,
      arq_max_jobs: form.value.arq_max_jobs,
      photo_gallery_url: form.value.photo_gallery_url,
      photo_gallery_mode: form.value.photo_gallery_mode,
      photo_gallery_new_tab: form.value.photo_gallery_new_tab,
      video_gallery_url: form.value.video_gallery_url,
      nc_service_username: form.value.nc_service_username,
      nc_files_root: form.value.nc_files_root,
      kb_import_max_size_mb: form.value.kb_import_max_size_mb,
      metrics_token: form.value.metrics_token || null,
    }
    const data = await api<SysSettingsOut>('/admin/system/settings', { method: 'PUT', body })
    settings.value = data
    form.value.sentry_dsn = ''
    form.value.metrics_token = ''
    message.success(t('admin.monitoring.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
