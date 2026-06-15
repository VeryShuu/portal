import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../../src/stores/auth'

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
  getLoginUrl: (redirect: string) => `/api/v1/auth/login?redirect=${redirect}`,
}))

vi.mock('../../src/api/bootstrap', () => ({
  fetchBootstrap: vi.fn(),
}))

vi.mock('../../src/api/index', () => ({
  api: vi.fn(() => Promise.resolve(undefined)),
  refreshAuth: vi.fn(() => Promise.resolve()),
}))

vi.mock('../../src/stores/branding', () => ({
  useBrandingStore: () => ({ setSettings: vi.fn() }),
}))
vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => ({ setData: vi.fn(), setGalleryLinks: vi.fn() }),
}))
vi.mock('../../src/stores/notifications', () => ({
  useNotificationsStore: () => ({ setUnreadCount: vi.fn() }),
}))

const reader = {
  id: 'u1', email: 'u@x.local', full_name: 'U', department: null, position: null,
  phone: null, role: 'reader' as const, avatar_url: null, presence_status: 'office' as const,
  notify_email: true, notify_inapp: true, lang: 'ru', preferences: {},
  auth_source: 'local' as const,
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
  window.sessionStorage.clear()
  // reset window.location.href without removing the property
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { href: '', pathname: '/dashboard', search: '?x=1' },
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('useAuthStore — extra branches', () => {
  it('loadBootstrap: ok path populates stores and starts silent refresh', async () => {
    const { fetchBootstrap } = await import('../../src/api/bootstrap')
    const { refreshAuth } = await import('../../src/api/index')
    // Keycloak-юзер: silent-refresh таймер заводится только для них (у local нет
    // refresh_token, сессия держится на Redis-TTL — таймер для них не нужен).
    vi.mocked(fetchBootstrap).mockResolvedValueOnce({
      user: { ...reader, auth_source: 'keycloak' },
      branding: { logo_url: null, primary_color: '#000' } as any,
      modules: { nextcloud: { enabled: false } } as any,
      gallery_links: [] as any,
      unread_count: 0,
    } as any)

    const auth = useAuthStore()
    const result = await auth.loadBootstrap()

    expect(result).toBe('ok')
    expect(auth.user).toEqual({ ...reader, auth_source: 'keycloak' })
    expect(auth.isAuthenticated).toBe(true)

    vi.advanceTimersByTime(4 * 60 * 1000 + 100)
    expect(refreshAuth).toHaveBeenCalled()
  })

  it('loadBootstrap: 401 → unauthenticated, stops timer', async () => {
    const { fetchBootstrap } = await import('../../src/api/bootstrap')
    vi.mocked(fetchBootstrap).mockRejectedValueOnce({ status: 401 })

    const auth = useAuthStore()
    const result = await auth.loadBootstrap()

    expect(result).toBe('unauthenticated')
    expect(auth.user).toBeNull()
    expect(auth.backendDown).toBe(false)
  })

  it('loadBootstrap: 500 / network → network_error, backendDown=true', async () => {
    const { fetchBootstrap } = await import('../../src/api/bootstrap')
    vi.mocked(fetchBootstrap).mockRejectedValueOnce({ statusCode: 500 })

    const auth = useAuthStore()
    const result = await auth.loadBootstrap()

    expect(result).toBe('network_error')
    expect(auth.backendDown).toBe(true)
  })

  it('loadUser: network error (no status) → network_error', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockRejectedValueOnce(new Error('connection refused'))

    const auth = useAuthStore()
    const result = await auth.loadUser()

    expect(result).toBe('network_error')
    expect(auth.backendDown).toBe(true)
  })

  it('loadUser: 401 → unauthenticated, no backendDown', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockRejectedValueOnce({ status: 401 })

    const auth = useAuthStore()
    const result = await auth.loadUser()

    expect(result).toBe('unauthenticated')
    expect(auth.backendDown).toBe(false)
  })

  it('logout: clears user, stops timer, navigates to /auth/error', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce(reader as any)
    const { api } = await import('../../src/api/index')

    const auth = useAuthStore()
    await auth.loadUser()
    expect(auth.user).not.toBeNull()

    auth.logout()
    expect(auth.user).toBeNull()
    expect(api).toHaveBeenCalledWith('/auth/logout', { method: 'POST' })

    await vi.runAllTimersAsync()
    expect(window.location.href).toBe('/auth/error?reason=logged_out')
  })

  it('setUser replaces the user reactive ref', async () => {
    const auth = useAuthStore()
    auth.setUser(reader as any)
    expect(auth.user).toEqual(reader)
    expect(auth.isAuthenticated).toBe(true)
  })

  it('auth:expired event clears user and stops timer', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce(reader as any)

    const auth = useAuthStore()
    await auth.loadUser()
    expect(auth.isAuthenticated).toBe(true)

    window.dispatchEvent(new Event('auth:expired'))
    expect(auth.user).toBeNull()
  })

  it('isLocalUser reflects user.auth_source', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({ ...reader, auth_source: 'keycloak' } as any)
    const auth = useAuthStore()
    await auth.loadUser()
    expect(auth.isLocalUser).toBe(false)

    vi.mocked(fetchMe).mockResolvedValueOnce({ ...reader, auth_source: 'local' } as any)
    await auth.loadUser()
    expect(auth.isLocalUser).toBe(true)
  })
})
