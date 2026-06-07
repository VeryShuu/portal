import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref, nextTick } from 'vue'

const mockApi = vi.fn()
const mockInvalidateQueries = vi.fn()
const mockRouterPush = vi.fn()
const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()
const mockManageOpen = vi.fn()
const mockOnboardingSetSettings = vi.fn()

const modulesDataRef = ref<any>(null)
const modulesErrorRef = ref(false)
const sysDataRef = ref<any>(null)
const sysErrorRef = ref(false)

vi.mock('../../src/api/index', () => ({ api: mockApi }))
vi.mock('../../src/api', () => ({ api: mockApi }))
vi.mock('../../src/queries/admin', () => ({
  useModulesAdminQuery: () => ({ data: modulesDataRef, isError: modulesErrorRef }),
  useSystemSettingsQuery: () => ({ data: sysDataRef, isError: sysErrorRef }),
}))
vi.mock('@tanstack/vue-query', () => ({ useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }) }))
vi.mock('../../src/queries/keys', () => ({
  queryKeys: { admin: { modules: () => ['admin', 'modules'], systemSettings: () => ['admin', 'systemSettings'] } },
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ success: mockMessageSuccess, error: mockMessageError }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mockRouterPush }) }))
vi.mock('../../src/router', () => ({ ROUTES: { PHOTOS: '/photos', MEETINGS: '/meetings' } }))
vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: () => ({ open: mockManageOpen, close: vi.fn(), is: vi.fn(), current: ref(null) }),
}))
vi.mock('../../src/stores/onboarding', () => ({ useOnboardingSettingsStore: () => ({ setSettings: mockOnboardingSetSettings }) }))

function seedData() {
  modulesDataRef.value = {
    nextcloud: { enabled: false },
    photos: { enabled: true, widget_limit: 8, max_size_mb: 50, allowed_mime: ['image/png'], strip_gps: true },
    meetings: { enabled: true, calendar_start_hour: 8, calendar_end_hour: 20, max_recurrence_horizon_days: 365, min_search_chars: 2 },
  }
  sysDataRef.value = {
    nextcloud_url: 'https://nc.example',
    nc_service_username: 'svc',
    nc_files_root: 'PortalFiles',
    nc_user_id_field: 'email',
    nc_service_app_password_set: false,
    video_gallery_url: 'https://video.example',
    onboarding_enabled: true,
    onboarding_reset_trigger: 'r1',
  }
}

describe('useModulesState (src/composables)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.resetModules()
    modulesErrorRef.value = false
    sysErrorRef.value = false
    seedData()
  })

  it('hydrates state and ncDirty flips after loaded watchers are armed', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()

    expect(state.modulesForm.value.photos.enabled).toBe(true)
    expect(state.ncForm.value.nextcloud_url).toBe('https://nc.example')

    modulesDataRef.value = { ...modulesDataRef.value }
    await nextTick()
    state.ncForm.value.nc_files_root = 'AnotherRoot'
    await nextTick()
    expect(state.ncDirty.value).toBe(true)
  })

  it('handles onboarding toggle success and error', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()

    mockApi.mockResolvedValueOnce({ onboarding_enabled: false, onboarding_reset_trigger: 'x' })
    await state.onToggleOnboarding(false)
    expect(mockOnboardingSetSettings).toHaveBeenCalledWith({ onboarding_enabled: false, onboarding_reset_trigger: 'x' })
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['admin', 'systemSettings'] })
    expect(state.onboardingToggling.value).toBe(false)

    mockApi.mockRejectedValueOnce(new Error('fail'))
    await state.onToggleOnboarding(true)
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('opens onboarding drawer and routes to module pages', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()
    state.openOnboardingDrawer()
    state.goToPhotos()
    state.goToMeetings()
    expect(mockManageOpen).toHaveBeenCalledWith('onboarding')
    expect(mockRouterPush).toHaveBeenCalledWith({ path: '/photos', query: { manage: 'module' } })
    expect(mockRouterPush).toHaveBeenCalledWith({ path: '/meetings', query: { manage: 'module' } })
  })

  it('onTogglePhotos covers guard/success/error', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()

    modulesDataRef.value = { nextcloud: { enabled: false }, meetings: modulesDataRef.value.meetings }
    await state.onTogglePhotos(false)
    expect(mockApi).not.toHaveBeenCalled()

    seedData()
    mockApi.mockResolvedValueOnce({})
    await state.onTogglePhotos(false)
    expect(state.modulesForm.value.photos.enabled).toBe(false)

    mockApi.mockRejectedValueOnce(new Error('boom'))
    await state.onTogglePhotos(true)
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('onToggleMeetings covers guard/success/error', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()

    modulesDataRef.value = { nextcloud: { enabled: false }, photos: modulesDataRef.value.photos }
    await state.onToggleMeetings(false)
    expect(mockApi).not.toHaveBeenCalled()

    seedData()
    mockApi.mockResolvedValueOnce({})
    await state.onToggleMeetings(false)
    expect(state.modulesForm.value.meetings.enabled).toBe(false)

    mockApi.mockRejectedValueOnce(new Error('boom'))
    await state.onToggleMeetings(true)
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('saveNextcloudAll module-load guard branch', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()
    modulesErrorRef.value = true
    await nextTick()
    await state.saveNextcloudAll()
    expect(mockApi).not.toHaveBeenCalled()
    expect(mockMessageError).toHaveBeenCalledWith('admin.modules.loadFailedGuard')
  })

  it('saveNextcloudAll sys-load guard branch', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()
    state.modulesForm.value.nextcloud.enabled = true
    sysErrorRef.value = true
    await nextTick()
    mockApi.mockResolvedValueOnce({})
    await state.saveNextcloudAll()
    expect(mockApi).toHaveBeenCalledWith('/admin/modules/nextcloud', expect.any(Object))
    expect(mockMessageError).toHaveBeenCalledWith('admin.system.loadFailedGuard')
  })

  it('saveNextcloudAll success and withSaving catch', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()

    state.modulesForm.value.nextcloud.enabled = true
    state.ncForm.value.nc_service_password = 'pwd-12345678'
    mockApi.mockResolvedValueOnce({}).mockResolvedValueOnce({})
    await state.saveNextcloudAll()
    expect(state.ncPasswordSet.value).toBe(true)
    expect(state.ncForm.value.nc_service_password).toBe('')
    expect(state.nextcloudSaving.value).toBe(false)

    mockApi.mockRejectedValueOnce(new Error('fail'))
    await state.saveNextcloudAll()
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('saveVideoUrl covers success and catch', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()
    state.videoGalleryUrl.value = 'https://gallery.new'

    mockApi.mockResolvedValueOnce({})
    await state.saveVideoUrl()
    expect(mockMessageSuccess).toHaveBeenCalledWith('admin.system.saved')

    mockApi.mockRejectedValueOnce(new Error('x'))
    await state.saveVideoUrl()
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('testNcConnection covers success and catch fallbacks', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    const state = useModulesState()

    mockApi.mockResolvedValueOnce({ ok: true, configured: true, server_reachable: true, nc_version: '29', auth_ok: false, webdav_ok: true, details: 'detail-text' })
    await state.testNcConnection()
    expect(state.ncTestResult.value).toEqual({ ok: true, details: 'Nextcloud 29 · admin.system.ncTestServerOk · detail-text' })

    mockApi.mockRejectedValueOnce({ data: { detail: 'bad auth' } })
    await state.testNcConnection()
    expect(state.ncTestResult.value).toEqual({ ok: false, details: 'bad auth' })

    mockApi.mockRejectedValueOnce({ status: 503 })
    await state.testNcConnection()
    expect(state.ncTestResult.value).toEqual({ ok: false, details: 'HTTP 503' })

    mockApi.mockRejectedValueOnce({})
    await state.testNcConnection()
    expect(state.ncTestResult.value).toEqual({ ok: false, details: 'errors.generic' })
  })

  it('reacts to modules load failed watcher with generic message', async () => {
    const { useModulesState } = await import('../../src/composables/useModulesState')
    useModulesState()
    modulesErrorRef.value = true
    await nextTick()
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })
})
