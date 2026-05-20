<template>
  <div class="branding-wrap">
    <div class="modules-hint">
      {{ t('admin.modules.tabHint') }}
    </div>

    <div class="branding-section">
      <div class="module-header">
        <div>
          <div class="branding-section__title">
            {{ t('admin.modules.photos.title') }}
          </div>
          <div class="branding-section__hint">
            {{ t('admin.modules.photos.hint') }}
          </div>
        </div>
        <div class="module-header__right">
          <n-button
            text
            size="small"
            @click="goToPhotos"
          >
            {{ t('admin.modules.openSettings') }} →
          </n-button>
          <n-switch
            :value="modulesForm.photos.enabled"
            :loading="photosToggling"
            @update:value="onTogglePhotos"
          />
        </div>
      </div>
    </div>

    <div
      class="branding-section"
      style="margin-top:16px"
    >
      <div class="module-header">
        <div>
          <div class="branding-section__title">
            {{ t('admin.modules.meetings.title') }}
          </div>
          <div class="branding-section__hint">
            {{ t('admin.modules.meetings.hint') }}
          </div>
        </div>
        <div class="module-header__right">
          <n-button
            text
            size="small"
            @click="goToMeetings"
          >
            {{ t('admin.modules.openSettings') }} →
          </n-button>
          <n-switch
            :value="modulesForm.meetings.enabled"
            :loading="meetingsToggling"
            @update:value="onToggleMeetings"
          />
        </div>
      </div>
    </div>

    <div
      class="branding-section"
      style="margin-top:16px"
    >
      <div class="module-header">
        <div>
          <div class="branding-section__title">
            {{ t('admin.modules.nextcloud.title') }}
          </div>
          <div class="branding-section__hint">
            {{ t('admin.modules.nextcloud.hint') }}
          </div>
        </div>
        <n-switch v-model:value="modulesForm.nextcloud.enabled" />
      </div>
      <template v-if="modulesForm.nextcloud.enabled">
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
                @click="testNcConnection"
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
          :loading="nextcloudSaving"
          @click="saveNextcloudAll"
        >
          {{ t('common.save') }}
        </n-button>
      </div>
    </div>

    <div
      class="branding-section"
      style="margin-top:16px"
    >
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NForm, NFormItem, NSwitch, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { api } from '../../../api'
import { useModulesAdminQuery, useSystemSettingsQuery } from '../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'
import { ROUTES } from '../../../router'

const { t } = useI18n()
const message = useMessage()
const qc = useQueryClient()
const router = useRouter()

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
  photos: { enabled: true },
  meetings: { enabled: false },
})

const ncForm = ref({
  nextcloud_url: '',
  nc_service_username: 'portal-svc',
  nc_files_root: 'PortalFiles',
  nc_user_id_field: '',
  nc_service_password: '',
})
const ncPasswordSet = ref(false)
const videoGalleryUrl = ref('')

const nextcloudSaving = ref(false)
const videoUrlSaving = ref(false)
const photosToggling = ref(false)
const meetingsToggling = ref(false)
const ncTesting = ref(false)
const ncTestResult = ref<{ ok: boolean; details?: string } | null>(null)
const modulesLoadError = ref(false)
const sysLoadError = ref(false)
const ncDirty = ref(false)
const ncLoaded = ref(false)

const { data: modulesData, isError: modulesLoadFailed } = useModulesAdminQuery()
const { data: sysSettingsData, isError: sysSettingsFailed } = useSystemSettingsQuery()

watch(modulesData, (data) => {
  if (data) {
    modulesForm.value.nextcloud.enabled = data.nextcloud.enabled
    if (data.photos) modulesForm.value.photos.enabled = data.photos.enabled
    if (data.meetings) modulesForm.value.meetings.enabled = data.meetings.enabled
    modulesLoadError.value = false
  }
}, { immediate: true })

watch(modulesLoadFailed, (failed) => {
  if (failed) {
    modulesLoadError.value = true
    message.error(t('errors.generic'))
  }
})

watch(sysSettingsData, (data) => {
  if (data) {
    ncForm.value.nextcloud_url = data.nextcloud_url
    ncForm.value.nc_service_username = data.nc_service_username as string
    ncForm.value.nc_files_root = data.nc_files_root as string
    ncForm.value.nc_user_id_field = data.nc_user_id_field as string
    ncForm.value.nc_service_password = ''
    ncPasswordSet.value = data.nc_service_app_password_set
    videoGalleryUrl.value = data.video_gallery_url as string
    sysLoadError.value = false
  }
}, { immediate: true })

watch(sysSettingsFailed, (failed) => {
  if (failed) sysLoadError.value = true
})

async function withSaving(flag: { value: boolean }, op: () => Promise<void>, successKey: string) {
  flag.value = true
  try {
    await op()
    message.success(t(successKey))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    flag.value = false
  }
}

async function onTogglePhotos(value: boolean) {
  if (!modulesData.value?.photos) return
  photosToggling.value = true
  try {
    await api('/admin/modules/photos', {
      method: 'PUT',
      body: {
        enabled: value,
        widget_limit: modulesData.value.photos.widget_limit,
        max_size_mb: modulesData.value.photos.max_size_mb,
        allowed_mime: modulesData.value.photos.allowed_mime,
        strip_gps: modulesData.value.photos.strip_gps,
      },
    })
    modulesForm.value.photos.enabled = value
    qc.invalidateQueries({ queryKey: queryKeys.admin.modules() })
    message.success(t('admin.modules.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    photosToggling.value = false
  }
}

async function onToggleMeetings(value: boolean) {
  if (!modulesData.value?.meetings) return
  meetingsToggling.value = true
  try {
    await api('/admin/modules/meetings', {
      method: 'PUT',
      body: {
        enabled: value,
        calendar_start_hour: modulesData.value.meetings.calendar_start_hour,
        calendar_end_hour: modulesData.value.meetings.calendar_end_hour,
        max_recurrence_horizon_days: modulesData.value.meetings.max_recurrence_horizon_days,
        min_search_chars: modulesData.value.meetings.min_search_chars,
      },
    })
    modulesForm.value.meetings.enabled = value
    qc.invalidateQueries({ queryKey: queryKeys.admin.modules() })
    message.success(t('admin.modules.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    meetingsToggling.value = false
  }
}

async function saveNcAll() {
  if (modulesLoadError.value) { message.error(t('admin.modules.loadFailedGuard')); return }
  await api('/admin/modules/nextcloud', {
    method: 'PUT',
    body: { enabled: modulesForm.value.nextcloud.enabled },
  })
  qc.invalidateQueries({ queryKey: queryKeys.admin.modules() })
  if (modulesForm.value.nextcloud.enabled) {
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
    qc.invalidateQueries({ queryKey: queryKeys.admin.systemSettings() })
    if (ncForm.value.nc_service_password) {
      ncPasswordSet.value = true
    }
    ncForm.value.nc_service_password = ''
  }
  await nextTick()
  ncDirty.value = false
}

function saveNextcloudAll() {
  return withSaving(nextcloudSaving, saveNcAll, 'admin.modules.saved')
}

function saveVideoUrl() {
  return withSaving(videoUrlSaving, () => api('/admin/system/settings', {
    method: 'PATCH',
    body: { video_gallery_url: videoGalleryUrl.value },
  }), 'admin.system.saved')
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

watch(modulesData, () => {
  if (!ncLoaded.value && modulesData.value && sysSettingsData.value) {
    ncLoaded.value = true
    watch(ncForm, () => { if (ncLoaded.value) ncDirty.value = true }, { deep: true })
    watch(() => modulesForm.value.nextcloud.enabled, () => { if (ncLoaded.value) ncDirty.value = true })
  }
})

watch(sysSettingsData, () => {
  if (!ncLoaded.value && modulesData.value && sysSettingsData.value) {
    ncLoaded.value = true
    watch(ncForm, () => { if (ncLoaded.value) ncDirty.value = true }, { deep: true })
    watch(() => modulesForm.value.nextcloud.enabled, () => { if (ncLoaded.value) ncDirty.value = true })
  }
})

function goToPhotos() {
  router.push({ path: ROUTES.PHOTOS, query: { manage: 'module' } })
}
function goToMeetings() {
  router.push({ path: ROUTES.MEETINGS, query: { manage: 'module' } })
}
</script>

<style scoped>
@import '../admin-tabs.css';
.modules-hint {
  font-size: 13px;
  color: var(--color-text-muted, #999);
  margin-bottom: 16px;
}
.module-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
