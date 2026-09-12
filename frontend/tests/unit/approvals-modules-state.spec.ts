/**
 * onToggleApprovals/goToApprovals в useModulesState (тумблер модуля).
 * vue-i18n замокан целиком — компоненты в этом файле не монтируются.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('../../src/api/index', () => ({ api: mockApi }))
vi.mock('../../src/api', () => ({ api: mockApi }))
vi.mock('../../src/queries/admin', () => ({
  useModulesAdminQuery: () => ({ data: modulesDataRef, isError: ref(false) }),
  useSystemSettingsQuery: () => ({ data: sysDataRef, isError: ref(false) }),
}))
vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}))
vi.mock('../../src/queries/keys', () => ({
  queryKeys: { admin: { modules: () => ['admin', 'modules'], systemSettings: () => ['admin', 'systemSettings'] } },
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ success: mockMessageSuccess, error: mockMessageError }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mockRouterPush }) }))
vi.mock('../../src/router', () => ({ ROUTES: { ADMIN: '/admin', PHOTOS: '/photos', MEETINGS: '/meetings' } }))
vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: () => ({ open: vi.fn(), close: vi.fn(), is: vi.fn(), current: ref(null) }),
}))
vi.mock('../../src/stores/onboarding', () => ({
  useOnboardingSettingsStore: () => ({ setSettings: vi.fn() }),
}))

// ── useModulesState: approvals toggle ──────────────────────────────────────

const mockApi = vi.fn().mockResolvedValue({})
const mockInvalidateQueries = vi.fn()
const mockRouterPush = vi.fn()
const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()

const modulesDataRef = ref<any>(null)
const sysDataRef = ref<any>(null)

vi.mock('../../src/api/index', () => ({ api: mockApi }))
vi.mock('../../src/api', () => ({ api: mockApi }))
vi.mock('../../src/queries/admin', () => ({
  useModulesAdminQuery: () => ({ data: modulesDataRef, isError: ref(false) }),
  useSystemSettingsQuery: () => ({ data: sysDataRef, isError: ref(false) }),
}))
vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}))
vi.mock('../../src/queries/keys', () => ({
  queryKeys: { admin: { modules: () => ['admin', 'modules'], systemSettings: () => ['admin', 'systemSettings'] } },
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ success: mockMessageSuccess, error: mockMessageError }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mockRouterPush }) }))
vi.mock('../../src/router', () => ({ ROUTES: { ADMIN: '/admin', PHOTOS: '/photos', MEETINGS: '/meetings' } }))
vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: () => ({ open: vi.fn(), close: vi.fn(), is: vi.fn(), current: ref(null) }),
}))
vi.mock('../../src/stores/onboarding', () => ({
  useOnboardingSettingsStore: () => ({ setSettings: vi.fn() }),
}))

describe('useModulesState: approvals', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
    modulesDataRef.value = {
      nextcloud: { enabled: false },
      photos: { enabled: false },
      meetings: { enabled: false },
      directories: { enabled: false },
      signature: { enabled: false },
      helpdesk: { enabled: false },
      erp_sync: { enabled: false },
      directum: { enabled: false },
      learning: { enabled: false },
      approvals: { enabled: false },
    }
    sysDataRef.value = {}
  })

  async function getState() {
    const { useModulesState } = await import('../../src/pages/admin/tabs/composables/useModulesState')
    return useModulesState()
  }

  it('onToggleApprovals: PUT + инвалидация + success', async () => {
    const state = await getState()
    await state.onToggleApprovals(true)
    expect(mockApi).toHaveBeenCalledWith('/admin/modules/approvals', {
      method: 'PUT',
      body: { enabled: true },
    })
    expect(mockInvalidateQueries).toHaveBeenCalled()
    expect(mockMessageSuccess).toHaveBeenCalled()
    expect(state.modulesForm.value.approvals.enabled).toBe(true)
  })

  it('onToggleApprovals: ошибка — message.error', async () => {
    mockApi.mockRejectedValueOnce(new Error('boom'))
    const state = await getState()
    await state.onToggleApprovals(true)
    expect(mockMessageError).toHaveBeenCalled()
  })

  it('goToApprovals ведёт на админ-таб approvals', async () => {
    const state = await getState()
    state.goToApprovals()
    expect(mockRouterPush).toHaveBeenCalledWith({ path: '/admin', query: { tab: 'approvals' } })
  })
})
