<template>
  <div class="branding-wrap">
    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.system.generalTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.system.generalHint') }}
      </div>
      <div class="branding-fields">
        <n-form-item
          :label="t('admin.system.portalBaseUrl')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="sysForm.portal_base_url"
            :placeholder="t('admin.system.portalBaseUrlPlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.system.timezone')"
          style="margin-bottom:0;max-width:280px"
        >
          <n-input
            v-model:value="sysForm.timezone"
            :placeholder="t('admin.system.timezonePlaceholder')"
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.system.timezoneHint') }}
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.system.staffDirectoryTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.system.staffDirectoryHint') }}
      </div>
      <div class="branding-fields">
        <n-form-item
          :label="t('admin.system.phoneExtractRegex')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="sysForm.phone_extract_regex"
            :placeholder="t('admin.system.phoneExtractRegexPlaceholder')"
            :status="phoneRegexError ? 'error' : undefined"
            clearable
            @update:value="validatePhoneRegex"
          />
        </n-form-item>
        <div
          v-if="phoneRegexError"
          style="font-size:12px;color:var(--n-error-color,#d03050)"
        >
          {{ phoneRegexError }}
        </div>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.system.phoneExtractRegexHint') }}
        </div>
        <div
          v-if="phoneRegexPreview"
          style="font-size:12px;color:var(--color-text-secondary)"
        >
          {{ t('admin.system.phoneExtractRegexPreview', { result: phoneRegexPreview }) }}
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.system.securityTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.system.securityHint') }}
      </div>
      <div class="branding-fields">
        <n-form-item
          :label="t('admin.system.allowedCidr')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="sysForm.allowed_cidr"
            :placeholder="t('admin.system.allowedCidrPlaceholder')"
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.system.allowedCidrHint') }}
        </div>
        <n-form-item
          :label="t('admin.system.maxUploadMb')"
          style="margin-bottom:0;max-width:200px"
        >
          <n-input-number
            v-model:value="sysForm.max_upload_size_mb"
            :min="1"
            :max="1024"
          />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">
          {{ t('admin.system.maxUploadMbHint') }}
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.system.fileLimitsTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.system.fileLimitsHint') }}
      </div>
      <div class="branding-fields">
        <div class="email-row-2">
          <n-form-item
            :label="t('admin.system.newsAttachmentMb')"
            style="margin-bottom:0;flex:1"
          >
            <n-input-number
              v-model:value="sysForm.news_attachment_max_size_mb"
              :min="1"
              :max="1024"
            />
          </n-form-item>
          <n-form-item
            :label="t('admin.system.kbMediaMb')"
            style="margin-bottom:0;flex:1"
          >
            <n-input-number
              v-model:value="sysForm.kb_media_max_size_mb"
              :min="1"
              :max="512"
            />
          </n-form-item>
          <n-form-item
            :label="t('admin.system.kbAttachmentMb')"
            style="margin-bottom:0;flex:1"
          >
            <n-input-number
              v-model:value="sysForm.kb_attachment_max_size_mb"
              :min="1"
              :max="1024"
            />
          </n-form-item>
          <n-form-item
            :label="t('admin.system.kbImportMb')"
            style="margin-bottom:0;flex:1"
          >
            <n-input-number
              v-model:value="sysForm.kb_import_max_size_mb"
              :min="1"
              :max="1024"
            />
          </n-form-item>
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="email-actions">
        <n-button
          type="primary"
          :loading="sysSaving"
          @click="saveSystemSettings"
        >
          {{ t('admin.system.save') }}
        </n-button>
        <n-button
          :loading="sysNginxReloading"
          @click="reloadNginx"
        >
          <template #icon>
            <n-icon><SyncOutline /></n-icon>
          </template>
          {{ t('admin.system.nginxReload') }}
        </n-button>
      </div>
      <div style="font-size:12px;color:var(--color-text-secondary);margin-top:8px">
        {{ t('admin.system.nginxReloadHint') }}
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.system.tlsTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.system.tlsHint') }}
      </div>

      <div class="tls-status-row">
        <n-tag
          :type="tlsStatus?.cert_exists ? 'success' : 'warning'"
          size="small"
          :bordered="false"
        >
          {{ tlsStatus?.cert_exists ? t('admin.system.tlsCertExists') : t('admin.system.tlsCertMissing') }}
        </n-tag>
        <span
          v-if="tlsStatus?.cert_expires_at"
          class="tls-meta"
        >
          {{ t('admin.system.tlsCertExpires') }}: {{ tlsStatus.cert_expires_at }}
        </span>
        <span
          v-if="tlsStatus?.cert_subject"
          class="tls-meta"
        >
          {{ t('admin.system.tlsCertSubject') }}: {{ tlsStatus.cert_subject }}
        </span>
      </div>
      <div
        class="tls-status-row"
        style="margin-top:6px"
      >
        <n-tag
          :type="tlsStatus?.key_exists ? 'success' : 'warning'"
          size="small"
          :bordered="false"
        >
          {{ tlsStatus?.key_exists ? t('admin.system.tlsKeyExists') : t('admin.system.tlsKeyMissing') }}
        </n-tag>
      </div>

      <div
        class="email-actions"
        style="margin-top:16px"
      >
        <n-upload
          :show-file-list="false"
          accept=".pem,.crt,.cer"
          @change="(info) => uploadTlsFile('cert', info)"
        >
          <n-button>{{ t('admin.system.tlsUploadCert') }}</n-button>
        </n-upload>
        <n-upload
          :show-file-list="false"
          accept=".pem,.key"
          @change="(info) => uploadTlsFile('key', info)"
        >
          <n-button>{{ t('admin.system.tlsUploadKey') }}</n-button>
        </n-upload>
        <n-button
          v-if="tlsStatus?.cert_exists"
          quaternary
          type="error"
          @click="deleteTlsFile('cert')"
        >
          {{ t('admin.system.tlsDeleteCert') }}
        </n-button>
        <n-button
          v-if="tlsStatus?.key_exists"
          quaternary
          type="error"
          @click="deleteTlsFile('key')"
        >
          {{ t('admin.system.tlsDeleteKey') }}
        </n-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NInput, NInputNumber, NIcon, NTag, NUpload, NFormItem, useMessage, type UploadFileInfo,
} from 'naive-ui'
import { SyncOutline } from '@vicons/ionicons5'
import { parseApiError } from '../../../utils/parseApiError'
import {
  useSystemSettingsQuery, useTlsStatusQuery,
  useSaveSystemSettingsMutation, useReloadNginxMutation,
  useUploadTlsMutation, useDeleteTlsMutation,
} from '../../../queries/admin'

const { t } = useI18n()
const message = useMessage()
const saveSettingsMut = useSaveSystemSettingsMutation()
const reloadNginxMut = useReloadNginxMutation()
const uploadTlsMut = useUploadTlsMutation()
const deleteTlsMut = useDeleteTlsMutation()

const sysSaving = ref(false)
const sysNginxReloading = ref(false)
const sysLoadError = ref(false)
const tlsLoadError = ref(false)
const phoneRegexError = ref('')

const PHONE_PREVIEW_SAMPLE = '8(495)6655566,609'

const sysForm = ref({
  portal_base_url: '',
  timezone: 'Europe/Moscow',
  allowed_cidr: '',
  max_upload_size_mb: 100,
  news_attachment_max_size_mb: 50,
  kb_media_max_size_mb: 20,
  kb_attachment_max_size_mb: 50,
  kb_import_max_size_mb: 50,
  phone_extract_regex: '',
})

function applyPhoneRegex(phone: string, pattern: string): string {
  if (!phone || !pattern) return phone
  try {
    const m = new RegExp(pattern).exec(phone)
    if (m) return m[1] ?? m[0]
  } catch {
  }
  return phone
}

const phoneRegexPreview = computed(() => {
  const pattern = sysForm.value.phone_extract_regex
  if (!pattern || phoneRegexError.value) return ''
  const result = applyPhoneRegex(PHONE_PREVIEW_SAMPLE, pattern)
  return result !== PHONE_PREVIEW_SAMPLE ? result : ''
})

function validatePhoneRegex(value: string) {
  if (!value) {
    phoneRegexError.value = ''
    return
  }
  try {
    new RegExp(value)
    phoneRegexError.value = ''
  } catch (e: unknown) {
    phoneRegexError.value = e instanceof Error ? e.message : String(e)
  }
}

const { data: sysSettingsData, isError: sysSettingsFailed } = useSystemSettingsQuery()
const { data: tlsStatusData, isError: tlsStatusFailed } = useTlsStatusQuery()
const tlsStatus = computed(() => tlsStatusData.value ?? null)

watch(sysSettingsData, (data) => {
  if (data) {
    sysForm.value.portal_base_url = data.portal_base_url
    sysForm.value.timezone = data.timezone
    sysForm.value.allowed_cidr = data.allowed_cidr
    sysForm.value.max_upload_size_mb = data.max_upload_size_mb
    sysForm.value.news_attachment_max_size_mb = data.news_attachment_max_size_mb
    sysForm.value.kb_media_max_size_mb = data.kb_media_max_size_mb
    sysForm.value.kb_attachment_max_size_mb = data.kb_attachment_max_size_mb
    sysForm.value.kb_import_max_size_mb = data.kb_import_max_size_mb
    sysForm.value.phone_extract_regex = data.phone_extract_regex ?? ''
    sysLoadError.value = false
  }
}, { immediate: true })

watch(sysSettingsFailed, (failed) => { if (failed) sysLoadError.value = true })
watch(tlsStatusFailed, (failed) => { if (failed) tlsLoadError.value = true })

const CIDR_RE = /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/

function validateCidrList(raw: string): boolean {
  if (!raw.trim()) return true
  return raw.split(',').map(s => s.trim()).every(c => CIDR_RE.test(c))
}

async function saveSystemSettings() {
  if (sysLoadError.value) {
    message.error(t('admin.system.loadFailedGuard'))
    return
  }
  if (!validateCidrList(sysForm.value.allowed_cidr)) {
    message.error(t('admin.system.allowedCidrInvalid'))
    return
  }
  if (phoneRegexError.value) {
    message.error(t('admin.system.phoneExtractRegexInvalid'))
    return
  }
  sysSaving.value = true
  try {
    await saveSettingsMut.mutateAsync({
      portal_base_url: sysForm.value.portal_base_url,
      timezone: sysForm.value.timezone,
      allowed_cidr: sysForm.value.allowed_cidr,
      max_upload_size_mb: sysForm.value.max_upload_size_mb,
      news_attachment_max_size_mb: sysForm.value.news_attachment_max_size_mb,
      kb_media_max_size_mb: sysForm.value.kb_media_max_size_mb,
      kb_attachment_max_size_mb: sysForm.value.kb_attachment_max_size_mb,
      kb_import_max_size_mb: sysForm.value.kb_import_max_size_mb,
      phone_extract_regex: sysForm.value.phone_extract_regex,
    })
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
    await reloadNginxMut.mutateAsync()
    message.success(t('admin.system.nginxReloaded'))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    sysNginxReloading.value = false
  }
}

async function uploadTlsFile(type: 'cert' | 'key', info: { file: UploadFileInfo }) {
  const file = info.file?.file
  if (!file) return
  if (file.size > 64 * 1024) {
    message.error(t('admin.system.tlsFileTooLarge'))
    return
  }
  try {
    await uploadTlsMut.mutateAsync({ type, file })
    message.success(t('admin.system.tlsUploaded'))
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

async function deleteTlsFile(type: 'cert' | 'key') {
  try {
    await deleteTlsMut.mutateAsync(type)
    message.success(t('admin.system.tlsDeleted'))
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}


</script>

<style scoped>
@import '../admin-tabs.css';
</style>
