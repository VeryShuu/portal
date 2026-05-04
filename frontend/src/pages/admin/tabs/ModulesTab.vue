<template>
  <div class="branding-wrap">

    <PhotosTab :photos-form="modulesForm.photos" />
    <div class="email-actions" style="margin-top:16px">
      <n-button type="primary" :loading="modulesPhotosSaving" @click="savePhotosModuleOnly">
        {{ t('common.save') }}
      </n-button>
    </div>

    <div class="branding-section" style="margin-top:16px">
      <div class="branding-section__title">{{ t('admin.modules.photoGallery.title') }}</div>
      <div class="branding-section__hint">{{ t('admin.modules.photoGallery.hint') }}</div>
      <div class="branding-fields" style="margin-top:16px">
        <n-form-item :label="t('admin.modules.photoGallery.modeLabel')" style="margin-bottom:0">
          <n-radio-group v-model:value="photoGalleryMode">
            <n-radio value="internal">{{ t('admin.modules.photoGallery.modeInternal') }}</n-radio>
            <n-radio value="external">{{ t('admin.modules.photoGallery.modeExternal') }}</n-radio>
          </n-radio-group>
        </n-form-item>
        <template v-if="photoGalleryMode === 'external'">
          <n-form-item :label="t('admin.system.photoGalleryUrl')" style="margin-bottom:0">
            <n-input v-model:value="photoGalleryUrl" :placeholder="t('admin.system.photoGalleryUrlPlaceholder')" clearable />
          </n-form-item>
          <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.photoGalleryUrlHint') }}</div>
          <n-form-item style="margin-bottom:0;margin-top:8px">
            <n-checkbox v-model:checked="photoGalleryNewTab">
              {{ t('admin.modules.photoGallery.newTab') }}
            </n-checkbox>
          </n-form-item>
        </template>
      </div>
      <div class="email-actions" style="margin-top:16px">
        <n-button type="primary" :loading="photoUrlSaving" @click="savePhotoUrl">
          {{ t('common.save') }}
        </n-button>
      </div>
    </div>

    <div class="branding-section" style="margin-top:16px">
      <div class="module-header">
        <div>
          <div class="branding-section__title">{{ t('admin.modules.nextcloud.title') }}</div>
          <div class="branding-section__hint">{{ t('admin.modules.nextcloud.hint') }}</div>
        </div>
        <n-switch v-model:value="modulesForm.nextcloud.enabled" />
      </div>
      <template v-if="modulesForm.nextcloud.enabled">
        <div class="branding-fields" style="margin-top:16px">
          <n-form-item :label="t('admin.system.nextcloudUrl')" style="margin-bottom:0">
            <n-input v-model:value="ncForm.nextcloud_url" :placeholder="t('admin.system.nextcloudUrlPlaceholder')" />
          </n-form-item>
          <div class="email-row-2">
            <n-form-item :label="t('admin.system.ncServiceUsername')" style="margin-bottom:0;flex:1">
              <n-input v-model:value="ncForm.nc_service_username" :placeholder="t('admin.system.ncServiceUsernamePlaceholder')" />
            </n-form-item>
            <n-form-item :label="t('admin.system.ncFilesRoot')" style="margin-bottom:0;flex:1">
              <n-input v-model:value="ncForm.nc_files_root" :placeholder="t('admin.system.ncFilesRootPlaceholder')" />
            </n-form-item>
          </div>
          <div class="email-row-2">
            <n-form-item :label="t('admin.system.ncUserIdField')" style="margin-bottom:0;flex:1">
              <n-input v-model:value="ncForm.nc_user_id_field" :placeholder="t('admin.system.ncUserIdFieldPlaceholder')" />
            </n-form-item>
            <n-form-item :label="t('admin.system.ncServicePassword')" style="margin-bottom:0;flex:1">
              <n-input
                v-model:value="ncForm.nc_service_password"
                type="password"
                show-password-on="click"
                :placeholder="ncPasswordSet ? t('admin.system.ncServicePasswordKeep') : t('admin.system.ncServicePasswordPlaceholder')"
                :input-props="{ autocomplete: 'new-password' }"
              />
            </n-form-item>
          </div>
          <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.ncUserIdFieldHint') }}</div>
          <div class="email-actions" style="margin-top:8px">
            <n-button :loading="ncTesting" :disabled="ncDirty" @click="testNcConnection">
              {{ t('admin.system.ncTestConnection') }}
            </n-button>
          </div>
          <div v-if="ncTestResult" class="kc-test-result" :class="ncTestResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'" style="margin-top:8px">
            <div class="kc-test-result__title">{{ ncTestResult.ok ? t('admin.system.ncTestOk') : t('admin.system.ncTestFail') }}</div>
            <div v-if="ncTestResult.details" class="kc-test-result__details">{{ ncTestResult.details }}</div>
          </div>
        </div>
      </template>
      <div class="email-actions" style="margin-top:16px">
        <n-button type="primary" :loading="nextcloudSaving" @click="saveNextcloudAll">
          {{ t('common.save') }}
        </n-button>
      </div>
    </div>

    <div class="branding-section" style="margin-top:16px">
      <div class="branding-section__title">{{ t('admin.modules.videoGallery.title') }}</div>
      <div class="branding-section__hint">{{ t('admin.modules.videoGallery.hint') }}</div>
      <div class="branding-fields" style="margin-top:16px">
        <n-form-item :label="t('admin.system.videoGalleryUrl')" style="margin-bottom:0">
          <n-input v-model:value="videoGalleryUrl" :placeholder="t('admin.system.videoGalleryUrlPlaceholder')" clearable />
        </n-form-item>
        <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.videoGalleryUrlHint') }}</div>
      </div>
      <div class="email-actions" style="margin-top:16px">
        <n-button type="primary" :loading="videoUrlSaving" @click="saveVideoUrl">
          {{ t('common.save') }}
        </n-button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NFormItem, NSwitch, NRadioGroup, NRadio, NCheckbox, useMessage } from 'naive-ui'
import { api } from '../../../api'
import PhotosTab from './PhotosTab.vue'

const { t } = useI18n()
const message = useMessage()

interface PhotosModuleOut {
  enabled: boolean
  widget_limit: number
  max_size_mb: number
  allowed_mime: string[]
  strip_gps: boolean
}

interface AllModulesOut {
  nextcloud: { enabled: boolean }
  photos: PhotosModuleOut
}

interface SysSettingsOut {
  nextcloud_url: string
  nc_service_username: string
  nc_files_root: string
  nc_user_id_field: string
  nc_service_app_password_set: boolean
  photo_gallery_url: string
  photo_gallery_mode: string
  photo_gallery_new_tab: boolean
  video_gallery_url: string
  [key: string]: unknown
}

interface NcStatusOut {
  ok: boolean
  configured: boolean
  server_reachable: boolean
  nc_version: string | null
  auth_ok: boolean
  webdav_ok: boolean
  details: string | null
}

const modulesForm = ref({
  nextcloud: { enabled: false },
  photos: {
    enabled: true,
    widget_limit: 8,
    max_size_mb: 50,
    allowed_mime: 'image/jpeg,image/png,image/webp,image/heic,image/heif,image/gif',
    strip_gps: true,
  },
})

const ncForm = ref({
  nextcloud_url: '',
  nc_service_username: 'portal-svc',
  nc_files_root: 'PortalFiles',
  nc_user_id_field: '',
  nc_service_password: '',
})
const ncPasswordSet = ref(false)
const photoGalleryUrl = ref('')
const photoGalleryMode = ref('external')
const photoGalleryNewTab = ref(false)
const videoGalleryUrl = ref('')

const modulesPhotosSaving = ref(false)
const photoUrlSaving = ref(false)
const nextcloudSaving = ref(false)
const videoUrlSaving = ref(false)
const ncTesting = ref(false)
const ncTestResult = ref<{ ok: boolean; details?: string } | null>(null)
const modulesLoadError = ref(false)
const sysLoadError = ref(false)
const ncDirty = ref(false)
const ncLoaded = ref(false)

async function loadModules() {
  try {
    const data = await api<AllModulesOut>('/admin/modules')
    modulesForm.value.nextcloud.enabled = data.nextcloud.enabled
    if (data.photos) {
      modulesForm.value.photos.enabled = data.photos.enabled
      modulesForm.value.photos.widget_limit = data.photos.widget_limit
      modulesForm.value.photos.max_size_mb = data.photos.max_size_mb
      modulesForm.value.photos.allowed_mime = (data.photos.allowed_mime || []).join(',')
      modulesForm.value.photos.strip_gps = data.photos.strip_gps
    }
    modulesLoadError.value = false
  } catch {
    modulesLoadError.value = true
    message.error(t('errors.generic'))
  }
}

async function loadSystemSettings() {
  try {
    const data = await api<SysSettingsOut>('/admin/system/settings')
    ncForm.value.nextcloud_url = data.nextcloud_url
    ncForm.value.nc_service_username = data.nc_service_username as string
    ncForm.value.nc_files_root = data.nc_files_root as string
    ncForm.value.nc_user_id_field = data.nc_user_id_field as string
    ncForm.value.nc_service_password = ''
    ncPasswordSet.value = data.nc_service_app_password_set
    photoGalleryUrl.value = data.photo_gallery_url as string
    photoGalleryMode.value = (data.photo_gallery_mode as string) || 'external'
    photoGalleryNewTab.value = Boolean(data.photo_gallery_new_tab)
    videoGalleryUrl.value = data.video_gallery_url as string
    sysLoadError.value = false
  } catch {
    sysLoadError.value = true
  }
}

async function savePhotosModule() {
  if (modulesLoadError.value) { message.error(t('admin.modules.loadFailedGuard')); return }
  const body = {
    enabled: modulesForm.value.photos.enabled,
    widget_limit: modulesForm.value.photos.widget_limit,
    max_size_mb: modulesForm.value.photos.max_size_mb,
    allowed_mime: modulesForm.value.photos.allowed_mime
      .split(',').map((s: string) => s.trim()).filter(Boolean),
    strip_gps: modulesForm.value.photos.strip_gps,
  }
  await api<PhotosModuleOut>('/admin/modules/photos', { method: 'PUT', body })
}

async function savePhotoGalleryUrl() {
  if (sysLoadError.value) { message.error(t('admin.system.loadFailedGuard')); return }
  await api('/admin/system/settings', {
    method: 'PATCH',
    body: {
      photo_gallery_url: photoGalleryUrl.value,
      photo_gallery_mode: photoGalleryMode.value,
      photo_gallery_new_tab: photoGalleryNewTab.value,
    },
  })
}

async function savePhotosModuleOnly() {
  modulesPhotosSaving.value = true
  try {
    await savePhotosModule()
    message.success(t('admin.modules.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    modulesPhotosSaving.value = false
  }
}

async function savePhotoUrl() {
  photoUrlSaving.value = true
  try {
    await savePhotoGalleryUrl()
    message.success(t('admin.modules.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    photoUrlSaving.value = false
  }
}

async function saveNextcloudModule() {
  if (modulesLoadError.value) { message.error(t('admin.modules.loadFailedGuard')); return }
  await api('/admin/modules/nextcloud', {
    method: 'PUT',
    body: { enabled: modulesForm.value.nextcloud.enabled },
  })
}

async function saveNcConnectionSettings() {
  if (sysLoadError.value) { message.error(t('admin.system.loadFailedGuard')); return }
  await api('/admin/system/settings', {
    method: 'PATCH',
    body: {
      nextcloud_url: ncForm.value.nextcloud_url,
      nc_service_username: ncForm.value.nc_service_username,
      nc_files_root: ncForm.value.nc_files_root,
      nc_user_id_field: ncForm.value.nc_user_id_field,
      nc_service_app_password: ncForm.value.nc_service_password || null,
    },
  })
  ncForm.value.nc_service_password = ''
}

async function saveNextcloudAll() {
  nextcloudSaving.value = true
  try {
    await saveNextcloudModule()
    if (modulesForm.value.nextcloud.enabled) {
      await saveNcConnectionSettings()
    }
    ncDirty.value = false
    message.success(t('admin.modules.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    nextcloudSaving.value = false
  }
}

async function saveVideoUrl() {
  videoUrlSaving.value = true
  try {
    await api('/admin/system/settings', {
      method: 'PATCH',
      body: { video_gallery_url: videoGalleryUrl.value },
    })
    message.success(t('admin.system.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    videoUrlSaving.value = false
  }
}

async function testNcConnection() {
  ncTesting.value = true
  ncTestResult.value = null
  try {
    const res = await api<NcStatusOut>('/admin/system/nextcloud/status')
    const parts: string[] = []
    if (res.nc_version) parts.push(`Nextcloud ${res.nc_version}`)
    if (res.server_reachable && !res.auth_ok) parts.push(t('admin.system.ncTestServerOk'))
    if (res.auth_ok) parts.push(t('admin.system.ncTestAuthOk'))
    if (res.details) parts.push(res.details)
    ncTestResult.value = { ok: res.ok, details: parts.join(' · ') || undefined }
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; statusText?: string; status?: number; message?: string }
    const details =
      err?.data?.detail ||
      err?.message ||
      err?.statusText ||
      (err?.status ? `HTTP ${err.status}` : t('errors.generic'))
    ncTestResult.value = { ok: false, details }
  } finally {
    ncTesting.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadModules(), loadSystemSettings()])
  ncLoaded.value = true
  watch(ncForm, () => { if (ncLoaded.value) ncDirty.value = true }, { deep: true })
  watch(() => modulesForm.value.nextcloud.enabled, () => { if (ncLoaded.value) ncDirty.value = true })
})
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
