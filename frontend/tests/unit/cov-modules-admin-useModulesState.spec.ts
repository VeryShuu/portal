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
vi.mock('../../src/router', () => ({ ROUTES: { PHOTOS: '/photos', MEETINGS: '/meetings', STAFF: '/staff' } }))
vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: () => ({ open: mockManageOpen, close: vi.fn(), is: vi.fn(), current: ref(null) }),
}))
vi.mock('../../src/stores/onboarding', () => ({ useOnboardingSettingsStore: () => ({ setSettings: mockOnboardingSetSettings }) }))

function seedData() {
  modulesDataRef.value = {
    nextcloud: { enabled: true },
    photos: { enabled: true, widget_limit: 8, max_size_mb: 50, allowed_mime: ['image/png'], strip_gps: true },
    meetings: { enabled: true, calendar_start_hour: 8, calendar_end_hour: 20, max_recurrence_horizon_days: 365, min_search_chars: 2 },
    directories: { enabled: false },
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

describe('useModulesState (src/pages/admin/tabs/composables)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.resetModules()
    modulesErrorRef.value = false
    sysErrorRef.value = false
    seedData()
  })

  it('hydrates directories state and routing helpers', async () => {
    const { useModulesState } = await import('../../src/pages/admin/tabs/composables/useModulesState')
    const state = useModulesState()

    expect(state.modulesForm.value.directories.enabled).toBe(false)
    state.openOnboardingDrawer()
    state.goToPhotos()
    state.goToMeetings()
    state.goToDirectories()

    expect(mockManageOpen).toHaveBeenCalledWith('onboarding')
    expect(mockRouterPush).toHaveBeenCalledWith({ path: '/staff', query: { manage: 'directory' } })
  })

  it('onToggleDirectories covers success and error', async () => {
    const { useModulesState } = await import('../../src/pages/admin/tabs/composables/useModulesState')
    const state = useModulesState()

    mockApi.mockResolvedValueOnce({})
    await state.onToggleDirectories(true)
    expect(state.modulesForm.value.directories.enabled).toBe(true)

    mockApi.mockRejectedValueOnce(new Error('x'))
    await state.onToggleDirectories(false)
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('onTogglePhotos and onToggleMeetings cover guard/success/error', async () => {
    const { useModulesState } = await import('../../src/pages/admin/tabs/composables/useModulesState')
    const state = useModulesState()

    modulesDataRef.value = { nextcloud: { enabled: true }, meetings: modulesDataRef.value.meetings, directories: { enabled: false } }
    await state.onTogglePhotos(false)
    expect(mockApi).not.toHaveBeenCalled()

    seedData()
    mockApi.mockResolvedValueOnce({})
    await state.onTogglePhotos(false)
    expect(state.modulesForm.value.photos.enabled).toBe(false)

    mockApi.mockRejectedValueOnce(new Error('x'))
    await state.onTogglePhotos(true)
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')

    vi.resetAllMocks()
    seedData()
    const { useModulesState: useModulesState2 } = await import('../../src/pages/admin/tabs/composables/useModulesState')
    const state2 = useModulesState2()
    modulesDataRef.value = { nextcloud: { enabled: true }, photos: modulesDataRef.value.photos, directories: { enabled: false } }
    await state2.onToggleMeetings(false)
    expect(mockApi).not.toHaveBeenCalled()

    seedData()
    mockApi.mockResolvedValueOnce({})
    await state2.onToggleMeetings(false)
    expect(state2.modulesForm.value.meetings.enabled).toBe(false)

    mockApi.mockRejectedValueOnce(new Error('y'))
    await state2.onToggleMeetings(true)
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('saveNextcloudAll covers module-load guard and sys-load guard', async () => {
    const { useModulesState } = await import('../../src/pages/admin/tabs/composables/useModulesState')
    const state = useModulesState()

    modulesErrorRef.value = true
    await nextTick()
    await state.saveNextcloudAll()
    expect(mockMessageError).toHaveBeenCalledWith('admin.modules.loadFailedGuard')

    vi.resetAllMocks()
    seedData()
    const { useModulesState: useModulesState2 } = await import('../../src/pages/admin/tabs/composables/useModulesState')
    const state2 = useModulesState2()
    state2.modulesForm.value.nextcloud.enabled = true
    sysErrorRef.value = true
    await nextTick()
    mockApi.mockResolvedValueOnce({})
    await state2.saveNextcloudAll()
    expect(mockApi).toHaveBeenCalledWith('/admin/modules/nextcloud', expect.any(Object))
    expect(mockMessageError).toHaveBeenCalledWith('admin.system.loadFailedGuard')
  })

  it('saveNextcloudAll success + catch, saveVideoUrl success + catch', async () => {
    const { useModulesState } = await import('../../src/pages/admin/tabs/composables/useModulesState')
    const state = useModulesState()

    state.modulesForm.value.nextcloud.enabled = true
    state.ncForm.value.nc_service_password = 'pwd-12345678'
    mockApi.mockResolvedValueOnce({}).mockResolvedValueOnce({})
    await state.saveNextcloudAll()
    expect(state.ncPasswordSet.value).toBe(true)

    mockApi.mockRejectedValueOnce(new Error('save fail'))
    await state.saveNextcloudAll()
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')

    mockApi.mockResolvedValueOnce({})
    await state.saveVideoUrl()
    expect(mockMessageSuccess).toHaveBeenCalledWith('admin.system.saved')

    mockApi.mockRejectedValueOnce(new Error('video fail'))
    await state.saveVideoUrl()
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('onToggleOnboarding and testNcConnection cover success/catch', async () => {
    const { useModulesState } = await import('../../src/pages/admin/tabs/composables/useModulesState')
    const state = useModulesState()

    mockApi.mockResolvedValueOnce({ onboarding_enabled: false, onboarding_reset_trigger: 'v2' })
    await state.onToggleOnboarding(false)
    expect(mockOnboardingSetSettings).toHaveBeenCalledWith({ onboarding_enabled: false, onboarding_reset_trigger: 'v2' })

    mockApi.mockRejectedValueOnce(new Error('x'))
    await state.onToggleOnboarding(true)
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')

    mockApi.mockResolvedValueOnce({ ok: true, configured: true, server_reachable: true, nc_version: '30', auth_ok: true, webdav_ok: true, details: null })
    await state.testNcConnection()
    expect(state.ncTestResult.value).toEqual({ ok: true, details: 'Nextcloud 30 · admin.system.ncTestAuthOk' })

    mockApi.mockRejectedValueOnce({ message: 'no conn' })
    await state.testNcConnection()
    expect(state.ncTestResult.value).toEqual({ ok: false, details: 'no conn' })
  })
})
