<template>
  <div class="branding-wrap">

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.system.generalTitle') }}</div>
      <div class="branding-section__hint">{{ t('admin.system.generalHint') }}</div>
      <div class="branding-fields">
        <n-form-item :label="t('admin.system.portalBaseUrl')" style="margin-bottom:0">
          <n-input v-model:value="sysForm.portal_base_url" :placeholder="t('admin.system.portalBaseUrlPlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('admin.system.timezone')" style="margin-bottom:0;max-width:280px">
          <n-input v-model:value="sysForm.timezone" :placeholder="t('admin.system.timezonePlaceholder')" />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.timezoneHint') }}</div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.system.securityTitle') }}</div>
      <div class="branding-section__hint">{{ t('admin.system.securityHint') }}</div>
      <div class="branding-fields">
        <n-form-item :label="t('admin.system.allowedCidr')" style="margin-bottom:0">
          <n-input v-model:value="sysForm.allowed_cidr" :placeholder="t('admin.system.allowedCidrPlaceholder')" />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.allowedCidrHint') }}</div>
        <n-form-item :label="t('admin.system.maxUploadMb')" style="margin-bottom:0;max-width:200px">
          <n-input-number v-model:value="sysForm.max_upload_size_mb" :min="1" :max="1024" />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.maxUploadMbHint') }}</div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.system.fileLimitsTitle') }}</div>
      <div class="branding-section__hint">{{ t('admin.system.fileLimitsHint') }}</div>
      <div class="branding-fields">
        <div class="email-row-2">
          <n-form-item :label="t('admin.system.newsAttachmentMb')" style="margin-bottom:0;flex:1">
            <n-input-number v-model:value="sysForm.news_attachment_max_size_mb" :min="1" :max="1024" />
          </n-form-item>
          <n-form-item :label="t('admin.system.kbMediaMb')" style="margin-bottom:0;flex:1">
            <n-input-number v-model:value="sysForm.kb_media_max_size_mb" :min="1" :max="512" />
          </n-form-item>
          <n-form-item :label="t('admin.system.kbAttachmentMb')" style="margin-bottom:0;flex:1">
            <n-input-number v-model:value="sysForm.kb_attachment_max_size_mb" :min="1" :max="1024" />
          </n-form-item>
          <n-form-item :label="t('admin.system.kbImportMb')" style="margin-bottom:0;flex:1">
            <n-input-number v-model:value="sysForm.kb_import_max_size_mb" :min="1" :max="1024" />
          </n-form-item>
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="email-actions">
        <n-button type="primary" :loading="sysSaving" @click="saveSystemSettings">
          {{ t('admin.system.save') }}
        </n-button>
        <n-button :loading="sysNginxReloading" @click="reloadNginx">
          <template #icon><n-icon><SyncOutline /></n-icon></template>
          {{ t('admin.system.nginxReload') }}
        </n-button>
      </div>
      <div style="font-size:12px;color:var(--color-text-secondary);margin-top:8px">{{ t('admin.system.nginxReloadHint') }}</div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.system.tlsTitle') }}</div>
      <div class="branding-section__hint">{{ t('admin.system.tlsHint') }}</div>

      <div class="tls-status-row">
        <n-tag :type="tlsStatus?.cert_exists ? 'success' : 'warning'" size="small" :bordered="false">
          {{ tlsStatus?.cert_exists ? t('admin.system.tlsCertExists') : t('admin.system.tlsCertMissing') }}
        </n-tag>
        <span v-if="tlsStatus?.cert_expires_at" class="tls-meta">
          {{ t('admin.system.tlsCertExpires') }}: {{ tlsStatus.cert_expires_at }}
        </span>
        <span v-if="tlsStatus?.cert_subject" class="tls-meta">
          {{ t('admin.system.tlsCertSubject') }}: {{ tlsStatus.cert_subject }}
        </span>
      </div>
      <div class="tls-status-row" style="margin-top:6px">
        <n-tag :type="tlsStatus?.key_exists ? 'success' : 'warning'" size="small" :bordered="false">
          {{ tlsStatus?.key_exists ? t('admin.system.tlsKeyExists') : t('admin.system.tlsKeyMissing') }}
        </n-tag>
      </div>

      <div class="email-actions" style="margin-top:16px">
        <n-upload :show-file-list="false" accept=".pem,.crt,.cer" @change="(info) => uploadTlsFile('cert', info)">
          <n-button>{{ t('admin.system.tlsUploadCert') }}</n-button>
        </n-upload>
        <n-upload :show-file-list="false" accept=".pem,.key" @change="(info) => uploadTlsFile('key', info)">
          <n-button>{{ t('admin.system.tlsUploadKey') }}</n-button>
        </n-upload>
        <n-button v-if="tlsStatus?.cert_exists" quaternary type="error" @click="deleteTlsFile('cert')">
          {{ t('admin.system.tlsDeleteCert') }}
        </n-button>
        <n-button v-if="tlsStatus?.key_exists" quaternary type="error" @click="deleteTlsFile('key')">
          {{ t('admin.system.tlsDeleteKey') }}
        </n-button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NInput, NInputNumber, NIcon, NTag, NUpload, NFormItem, useMessage, type UploadFileInfo,
} from 'naive-ui'
import { SyncOutline } from '@vicons/ionicons5'
import { api, apiUpload } from '../../../api'
import { parseApiError } from '../../../utils/parseApiError'

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

interface TlsStatus {
  cert_exists: boolean
  key_exists: boolean
  cert_expires_at: string | null
  cert_subject: string | null
}

function logForceJsonFromStr(v: string): boolean | null {
  if (v === 'true') return true
  if (v === 'false') return false
  return null
}

function logForceJsonToStr(v: boolean | null): string {
  if (v === true) return 'true'
  if (v === false) return 'false'
  return 'null'
}

const sysSettings = ref<SysSettingsOut | null>(null)
const tlsStatus = ref<TlsStatus | null>(null)
const sysSaving = ref(false)
const sysNginxReloading = ref(false)
const sysLoadError = ref(false)
const tlsLoadError = ref(false)

const sysForm = ref({
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

async function loadSystemSettings() {
  try {
    const data = await api<SysSettingsOut>('/admin/system/settings')
    sysSettings.value = data
    sysForm.value.portal_base_url = data.portal_base_url
    sysForm.value.nextcloud_url = data.nextcloud_url
    sysForm.value.nc_user_id_field = data.nc_user_id_field
    sysForm.value.nc_service_password = ''
    sysForm.value.max_upload_size_mb = data.max_upload_size_mb
    sysForm.value.allowed_cidr = data.allowed_cidr
    sysForm.value.prometheus_metrics_enabled = data.prometheus_metrics_enabled
    sysForm.value.news_attachment_max_size_mb = data.news_attachment_max_size_mb
    sysForm.value.kb_media_max_size_mb = data.kb_media_max_size_mb
    sysForm.value.kb_attachment_max_size_mb = data.kb_attachment_max_size_mb
    sysForm.value.log_level = data.log_level
    sysForm.value.timezone = data.timezone
    sysForm.value.sentry_dsn = ''
    sysForm.value.log_force_json = logForceJsonToStr(data.log_force_json)
    sysForm.value.log_slow_request_ms = data.log_slow_request_ms
    sysForm.value.arq_max_jobs = data.arq_max_jobs
    sysForm.value.photo_gallery_url = data.photo_gallery_url
    sysForm.value.photo_gallery_mode = data.photo_gallery_mode
    sysForm.value.photo_gallery_new_tab = data.photo_gallery_new_tab
    sysForm.value.video_gallery_url = data.video_gallery_url
    sysForm.value.nc_service_username = data.nc_service_username
    sysForm.value.nc_files_root = data.nc_files_root
    sysForm.value.kb_import_max_size_mb = data.kb_import_max_size_mb
    sysForm.value.metrics_token = ''
    sysLoadError.value = false
  } catch {
    sysLoadError.value = true
    message.error(t('errors.generic'))
  }
}

async function loadTlsStatus() {
  try {
    tlsStatus.value = await api<TlsStatus>('/admin/system/tls/status')
    tlsLoadError.value = false
  } catch {
    tlsLoadError.value = true
  }
}

async function saveSystemSettings() {
  if (sysLoadError.value) {
    message.error(t('admin.system.loadFailedGuard'))
    return
  }
  sysSaving.value = true
  try {
    const body = {
      portal_base_url: sysForm.value.portal_base_url,
      nextcloud_url: sysForm.value.nextcloud_url,
      nc_user_id_field: sysForm.value.nc_user_id_field,
      nc_service_app_password: sysForm.value.nc_service_password || null,
      max_upload_size_mb: sysForm.value.max_upload_size_mb,
      allowed_cidr: sysForm.value.allowed_cidr,
      prometheus_metrics_enabled: sysForm.value.prometheus_metrics_enabled,
      news_attachment_max_size_mb: sysForm.value.news_attachment_max_size_mb,
      kb_media_max_size_mb: sysForm.value.kb_media_max_size_mb,
      kb_attachment_max_size_mb: sysForm.value.kb_attachment_max_size_mb,
      log_level: sysForm.value.log_level,
      timezone: sysForm.value.timezone,
      sentry_dsn: sysForm.value.sentry_dsn || null,
      log_force_json: logForceJsonFromStr(sysForm.value.log_force_json),
      log_slow_request_ms: sysForm.value.log_slow_request_ms,
      arq_max_jobs: sysForm.value.arq_max_jobs,
      photo_gallery_url: sysForm.value.photo_gallery_url,
      photo_gallery_mode: sysForm.value.photo_gallery_mode,
      photo_gallery_new_tab: sysForm.value.photo_gallery_new_tab,
      video_gallery_url: sysForm.value.video_gallery_url,
      nc_service_username: sysForm.value.nc_service_username,
      nc_files_root: sysForm.value.nc_files_root,
      kb_import_max_size_mb: sysForm.value.kb_import_max_size_mb,
      metrics_token: sysForm.value.metrics_token || null,
    }
    const data = await api<SysSettingsOut>('/admin/system/settings', { method: 'PUT', body })
    sysSettings.value = data
    sysForm.value.nc_service_password = ''
    sysForm.value.sentry_dsn = ''
    sysForm.value.metrics_token = ''
    message.success(t('admin.system.saved'))
  } catch (err) {
    message.error(parseApiError(err, t))
  } finally {
    sysSaving.value = false
  }
}

async function reloadNginx() {
  sysNginxReloading.value = true
  try {
    await api('/admin/system/nginx/reload', { method: 'POST' })
    message.success(t('admin.system.nginxReloaded'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    sysNginxReloading.value = false
  }
}

async function uploadTlsFile(type: 'cert' | 'key', info: { file: UploadFileInfo }) {
  const file = info.file?.file
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  try {
    await apiUpload(`/admin/system/tls/${type}`, form)
    message.success(t('admin.system.tlsUploaded'))
    await loadTlsStatus()
  } catch {
    message.error(t('errors.generic'))
  }
}

async function deleteTlsFile(type: 'cert' | 'key') {
  try {
    await api(`/admin/system/tls/${type}`, { method: 'DELETE' })
    message.success(t('admin.system.tlsDeleted'))
    await loadTlsStatus()
  } catch {
    message.error(t('errors.generic'))
  }
}

onMounted(() => {
  void Promise.allSettled([loadSystemSettings(), loadTlsStatus()])
})
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
