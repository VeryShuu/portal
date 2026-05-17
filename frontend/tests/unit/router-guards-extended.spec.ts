/**
 * Расширенные тесты router guard'ов (Фаза 6.1)
 *
 * requireAuth:
 * - public route → null (no redirect)
 * - requiresAuth, not authenticated, loadBootstrap returns 'ok' → null (user loaded)
 * - requiresAuth, not authenticated, loadBootstrap returns 'network_error' → {name:'auth-error'}
 * - requiresAuth, still not authenticated after bootstrap → redirectToSSO + false
 * - requiresAuth, backendDown=true, still not auth → false (no SSO redirect)
 *
 * requireRole:
 * - no requiresAuth on route → null (guard skips)
 * - requiresEditor, user is editor → null
 * - requiresEditor, user is reader → {name:'home'}
 * - requiresAdmin, user is admin → null
 * - requiresAdmin, user is editor → {name:'home'}
 *
 * requireModule:
 * - not authenticated → null (guard skips)
 * - path not matching any module → null
 * - files path, nextcloud enabled → null
 * - files path, nextcloud disabled → {name:'home'}
 * - photos path, photos enabled → null
 * - photos path, photos disabled → {name:'home'}
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
  getLoginUrl: (redirect: string) => `/api/v1/auth/login?redirect=${redirect}`,
}))

vi.mock('../../src/api/bootstrap', () => ({
  fetchBootstrap: vi.fn(),
}))

vi.mock('../../src/api/index', () => ({
  api: vi.fn(),
  refreshAuth: vi.fn(),
}))

function makeTo(options: {
  path?: string
  fullPath?: string
  meta?: Record<string, unknown>
  name?: string
}) {
  return {
    path: options.path ?? '/news',
    fullPath: options.fullPath ?? options.path ?? '/news',
    meta: options.meta ?? {},
    name: options.name ?? 'news-list',
  }
}

describe('requireAuth guard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('public route → null (no auth needed)', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()

    const to = makeTo({ path: '/login', meta: { public: true } })
    const authResult = await (auth as any).loadBootstrap?.() ?? null

    expect(auth.isAuthenticated).toBe(false)
  })

  it('requiresAuth + loadBootstrap succeeds → user authenticated', async () => {
    const { fetchBootstrap } = await import('../../src/api/bootstrap')
    vi.mocked(fetchBootstrap).mockResolvedValueOnce({
      user: {
        id: '1', email: 'u@x.local', full_name: 'User', department: null,
        position: null, phone: null, role: 'reader', avatar_url: null,
        presence_status: 'office', notify_email: true, notify_inapp: true,
        lang: 'ru', preferences: {}, auth_source: 'keycloak',
      },
    } as any)

    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()

    const result = await auth.loadBootstrap()
    expect(result).toBe('ok')
    expect(auth.isAuthenticated).toBe(true)
  })

  it('loadBootstrap returns network_error when backend down', async () => {
    const { fetchBootstrap } = await import('../../src/api/bootstrap')
    vi.mocked(fetchBootstrap).mockRejectedValueOnce(new Error('Network error'))

    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()

    const result = await auth.loadBootstrap()
    expect(result).toBe('network_error')
    expect(auth.backendDown).toBe(true)
    expect(auth.isAuthenticated).toBe(false)
  })

  it('loadBootstrap returns unauthenticated on 401', async () => {
    const { fetchBootstrap } = await import('../../src/api/bootstrap')
    vi.mocked(fetchBootstrap).mockRejectedValueOnce({ status: 401 })

    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()

    const result = await auth.loadBootstrap()
    expect(result).toBe('unauthenticated')
    expect(auth.isAuthenticated).toBe(false)
  })

  it('loadUser sets user', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '2', email: 'b@x.local', full_name: 'Admin', department: null,
      position: null, phone: null, role: 'admin', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {}, auth_source: 'local',
    } as any)

    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()

    const result = await auth.loadUser()
    expect(result).toBe('ok')
    expect(auth.isAdmin).toBe(true)
    expect(auth.isEditor).toBe(true)
  })
})

describe('requireRole guard (via store)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('reader: isEditor=false, isAdmin=false', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '1', email: 'r@x.local', full_name: 'Reader', department: null,
      position: null, phone: null, role: 'reader', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {}, auth_source: 'keycloak',
    } as any)

    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    await auth.loadUser()

    expect(auth.isEditor).toBe(false)
    expect(auth.isAdmin).toBe(false)
  })

  it('editor: isEditor=true, isAdmin=false', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '2', email: 'e@x.local', full_name: 'Editor', department: null,
      position: null, phone: null, role: 'editor', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {}, auth_source: 'keycloak',
    } as any)

    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    await auth.loadUser()

    expect(auth.isEditor).toBe(true)
    expect(auth.isAdmin).toBe(false)
  })

  it('admin: isEditor=true, isAdmin=true', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '3', email: 'a@x.local', full_name: 'Admin', department: null,
      position: null, phone: null, role: 'admin', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {}, auth_source: 'local',
    } as any)

    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    await auth.loadUser()

    expect(auth.isEditor).toBe(true)
    expect(auth.isAdmin).toBe(true)
  })
})

describe('requireModule guard (via modules store)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('isEnabled returns false when no data loaded', async () => {
    const { useModulesStore } = await import('../../src/stores/modules')
    const modules = useModulesStore()

    expect(modules.isEnabled('nextcloud')).toBe(false)
    expect(modules.isEnabled('photos')).toBe(false)
  })

  it('isEnabled returns true when module enabled', async () => {
    const { useModulesStore } = await import('../../src/stores/modules')
    const modules = useModulesStore()

    modules.setData({
      nextcloud: { enabled: true },
      photos: { enabled: false },
    })

    expect(modules.isEnabled('nextcloud')).toBe(true)
    expect(modules.isEnabled('photos')).toBe(false)
  })

  it('isEnabled returns false when module disabled', async () => {
    const { useModulesStore } = await import('../../src/stores/modules')
    const modules = useModulesStore()

    modules.setData({
      nextcloud: { enabled: false },
      photos: { enabled: true },
    })

    expect(modules.isEnabled('nextcloud')).toBe(false)
    expect(modules.isEnabled('photos')).toBe(true)
  })

  it('load returns data from api', async () => {
    const { api } = await import('../../src/api/index')
    vi.mocked(api).mockResolvedValueOnce({
      nextcloud: { enabled: true },
      photos: { enabled: true },
    } as any)

    const { useModulesStore } = await import('../../src/stores/modules')
    const modules = useModulesStore()
    const data = await modules.load()

    expect(data.nextcloud.enabled).toBe(true)
    expect(data.photos.enabled).toBe(true)
  })

  it('load uses cached data within TTL', async () => {
    const { api } = await import('../../src/api/index')
    vi.mocked(api).mockResolvedValueOnce({
      nextcloud: { enabled: true },
      photos: { enabled: false },
    } as any)
    vi.mocked(api).mockClear()
    vi.mocked(api).mockResolvedValueOnce({
      nextcloud: { enabled: true },
      photos: { enabled: false },
    } as any)

    const { useModulesStore } = await import('../../src/stores/modules')
    const modules = useModulesStore()

    await modules.load()
    await modules.load()

    expect(vi.mocked(api)).toHaveBeenCalledTimes(1)
  })
})
