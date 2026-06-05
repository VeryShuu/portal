import { ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { api } from '../../../../api'
import { useModulesAdminQuery, useSystemSettingsQuery, type AdminSystemSettings } from '../../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../../queries/keys'
import { ROUTES } from '../../../../router'
import { useManageDrawer } from '../../../../composables/useManageDrawer'
import { useOnboardingSettingsStore } from '../../../../stores/onboarding'

interface NcStatusOut {
  ok: boolean
  configured: boolean
  server_reachable: boolean
  nc_version: string | null
  auth_ok: boolean
  webdav_ok: boolean
  details: string | null
}

export function useModulesState() {
  const { t } = useI18n()
  const message = useMessage()
  const qc = useQueryClient()
  const router = useRouter()

  const modulesForm = ref({
    nextcloud: { enabled: false },
    photos: { enabled: true },
    meetings: { enabled: false },
    directories: { enabled: false },
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
  const directoriesToggling = ref(false)
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
      if (data.directories) modulesForm.value.directories.enabled = data.directories.enabled
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

  const manage = useManageDrawer(['onboarding'])
  const onboardingToggling = ref(false)
  const onboardingSysData = sysSettingsData
  const onboardingStore = useOnboardingSettingsStore()

  function openOnboardingDrawer() {
    manage.open('onboarding')
  }

  async function onToggleOnboarding(value: boolean) {
    onboardingToggling.value = true
    try {
      const updated = await api<AdminSystemSettings>('/admin/system/settings', {
        method: 'PATCH',
        body: { onboarding_enabled: value },
      })
      qc.invalidateQueries({ queryKey: queryKeys.admin.systemSettings() })
      onboardingStore.setSettings({
        onboarding_enabled: updated.onboarding_enabled,
        onboarding_reset_trigger: updated.onboarding_reset_trigger,
      })
      message.success(t('admin.modules.saved'))
    } catch {
      message.error(t('errors.generic'))
    } finally {
      onboardingToggling.value = false
    }
  }

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

  async function onToggleDirectories(value: boolean) {
    directoriesToggling.value = true
    try {
      await api('/admin/modules/directories', {
        method: 'PUT',
        body: { enabled: value },
      })
      modulesForm.value.directories.enabled = value
      qc.invalidateQueries({ queryKey: queryKeys.admin.modules() })
      message.success(t('admin.modules.saved'))
    } catch {
      message.error(t('errors.generic'))
    } finally {
      directoriesToggling.value = false
    }
  }

  function goToDirectories() {
    router.push({ path: ROUTES.STAFF, query: { manage: 'directory' } })
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

  function goToPhotos() {
    router.push({ path: ROUTES.PHOTOS, query: { manage: 'module' } })
  }

  function goToMeetings() {
    router.push({ path: ROUTES.MEETINGS, query: { manage: 'module' } })
  }

  return {
    modulesForm,
    ncForm,
    ncPasswordSet,
    videoGalleryUrl,
    nextcloudSaving,
    videoUrlSaving,
    photosToggling,
    meetingsToggling,
    directoriesToggling,
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
    onToggleDirectories,
    onToggleOnboarding,
    openOnboardingDrawer,
    goToPhotos,
    goToMeetings,
    goToDirectories,
  }
}
