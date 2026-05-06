/**
 * Тесты роутерных guard'ов через моки store.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
  getLoginUrl: (redirect: string) => `/api/v1/auth/login?redirect=${redirect}`,
}))

describe('useAuthStore — role helpers', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('isLocalUser true for local auth_source', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '1', email: 'a@x.local', full_name: 'A', department: null,
      position: null, phone: null, role: 'admin', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {}, auth_source: 'local',
    } as any)
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    await auth.loadUser()
    expect(auth.isLocalUser).toBe(true)
  })

  it('isLocalUser false for keycloak auth_source', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '2', email: 'b@x.local', full_name: 'B', department: null,
      position: null, phone: null, role: 'admin', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {}, auth_source: 'keycloak',
    } as any)
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    await auth.loadUser()
    expect(auth.isLocalUser).toBe(false)
  })

  it('redirectToSSO формирует URL на /api/v1/auth/login c redirect-параметром', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    const orig = window.location
    delete (window as any).location
    ;(window as any).location = { pathname: '/news', search: '', href: '' }
    window.sessionStorage.clear()
    auth.redirectToSSO('/kb/articles/123')
    expect((window as any).location.href).toContain('/api/v1/auth/login?redirect=')
    expect((window as any).location.href).toContain(encodeURIComponent('/kb/articles/123'))
    ;(window as any).location = orig
  })
})
