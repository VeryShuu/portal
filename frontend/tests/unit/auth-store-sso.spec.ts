/**
 * Тесты loop-protection и SSO state в useAuthStore.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
  getLoginUrl: (redirect: string) => `/api/v1/auth/login?redirect=${redirect}`,
}))

describe('useAuthStore — SSO loop-protection', () => {
  let originalLocation: Location

  beforeEach(() => {
    setActivePinia(createPinia())
    originalLocation = window.location
    delete (window as any).location
    ;(window as any).location = { pathname: '/', search: '', href: '' }
    window.sessionStorage.clear()
  })

  afterEach(() => {
    ;(window as any).location = originalLocation
    window.sessionStorage.clear()
  })

  it('redirectToSSO добавляет timestamp в sso_attempts и навигирует', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.redirectToSSO('/news')
    const attempts = JSON.parse(window.sessionStorage.getItem('sso_attempts') || '[]')
    expect(attempts.length).toBe(1)
    expect((window as any).location.href).toContain('/api/v1/auth/login?redirect=')
  })

  it('loop-detection: 2 попытки за 30s → /auth/error?reason=loop_detected', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    const now = Date.now()
    window.sessionStorage.setItem('sso_attempts', JSON.stringify([now - 1000, now - 500]))
    auth.redirectToSSO('/news')
    expect((window as any).location.href).toContain('/auth/error?reason=loop_detected')
    expect(window.sessionStorage.getItem('sso_failed')).toBe('loop_detected')
  })

  it('старые попытки (>30s) фильтруются, новый редирект разрешён', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    const now = Date.now()
    window.sessionStorage.setItem('sso_attempts', JSON.stringify([now - 60_000, now - 45_000]))
    auth.redirectToSSO('/news')
    const attempts = JSON.parse(window.sessionStorage.getItem('sso_attempts') || '[]')
    expect(attempts.length).toBe(1)
    expect((window as any).location.href).toContain('/api/v1/auth/login')
  })

  it('clearSSOState удаляет оба ключа', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    window.sessionStorage.setItem('sso_attempts', JSON.stringify([Date.now()]))
    window.sessionStorage.setItem('sso_failed', 'sso_failed')
    auth.clearSSOState()
    expect(window.sessionStorage.getItem('sso_attempts')).toBeNull()
    expect(window.sessionStorage.getItem('sso_failed')).toBeNull()
  })

  it('markSSOFailed сохраняет причину', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.markSSOFailed('keycloak_unavailable')
    expect(window.sessionStorage.getItem('sso_failed')).toBe('keycloak_unavailable')
  })

  it('loadUser успех очищает sso_attempts и sso_failed', async () => {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce({
      id: '1', email: 'a@x.local', full_name: 'A', department: null,
      position: null, phone: null, role: 'admin', avatar_url: null,
      presence_status: 'office', notify_email: true, notify_inapp: true,
      lang: 'ru', preferences: {}, auth_source: 'local',
    } as any)
    window.sessionStorage.setItem('sso_attempts', JSON.stringify([Date.now()]))
    window.sessionStorage.setItem('sso_failed', 'sso_failed')
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    await auth.loadUser()
    expect(window.sessionStorage.getItem('sso_attempts')).toBeNull()
    expect(window.sessionStorage.getItem('sso_failed')).toBeNull()
  })
})
