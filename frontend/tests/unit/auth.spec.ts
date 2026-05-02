import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../../src/stores/auth'

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
  getLoginUrl: (redirect: string) => `/api/v1/auth/login?redirect=${redirect}`,
}))

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('isAuthenticated is false initially', () => {
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('isEditor is false for reader', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '1', email: 'test@x.local', full_name: 'Test', department: null,
      position: null, phone: null, role: 'reader', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {},
    })
    const auth = useAuthStore()
    await auth.loadUser()
    expect(auth.isEditor).toBe(false)
    expect(auth.isAdmin).toBe(false)
  })

  it('isEditor is true for editor role', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '2', email: 'ed@x.local', full_name: 'Editor', department: 'IT',
      position: null, phone: null, role: 'editor', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {},
    })
    const auth = useAuthStore()
    await auth.loadUser()
    expect(auth.isEditor).toBe(true)
    expect(auth.isAdmin).toBe(false)
  })

  it('isAdmin is true for admin role', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '3', email: 'admin@x.local', full_name: 'Admin', department: null,
      position: null, phone: null, role: 'admin', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {},
    })
    const auth = useAuthStore()
    await auth.loadUser()
    expect(auth.isAdmin).toBe(true)
    expect(auth.isEditor).toBe(true)
  })

  it('loadUser returns false on network error', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockRejectedValueOnce(new Error('Network error'))
    const auth = useAuthStore()
    const result = await auth.loadUser()
    expect(result).toBe(false)
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })
})
