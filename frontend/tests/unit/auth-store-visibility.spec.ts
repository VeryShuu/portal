/**
 * Тесты проактивного refresh при возврате вкладки из фона (visibilitychange).
 * См. docs/wip/auth.md, П.2.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../src/api/index', () => ({
  api: vi.fn(),
  refreshAuth: vi.fn(() => Promise.resolve(true)),
  setSessionAuthSource: vi.fn(),
  getSessionAuthSource: vi.fn(() => 'keycloak'),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
}))

vi.mock('../../src/api/bootstrap', () => ({
  fetchBootstrap: vi.fn(),
}))

const USER = {
  id: '1', email: 'a@x.local', full_name: 'A', department: null,
  position: null, phone: null, role: 'admin', avatar_url: null,
  presence_status: 'office', notify_email: true, notify_inapp: true,
  lang: 'ru', preferences: {}, auth_source: 'keycloak',
}

const LOCAL_USER = { ...USER, auth_source: 'local' }

function setVisibility(state: 'visible' | 'hidden'): void {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

const flush = () => new Promise((r) => setTimeout(r, 0))

describe('useAuthStore — refresh при возврате вкладки', () => {
  let disposeStore: (() => void) | null = null
  let originalLocation: Location

  beforeEach(() => {
    setActivePinia(createPinia())
    originalLocation = window.location
    delete (window as any).location
    ;(window as any).location = { pathname: '/news', search: '', href: '' }
    window.sessionStorage.clear()
  })

  afterEach(() => {
    // Снимаем visibilitychange-слушатель текущего стора, чтобы он не накапливался
    // между тестами (onScopeDispose срабатывает на $dispose).
    disposeStore?.()
    disposeStore = null
    ;(window as any).location = originalLocation
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  async function login(profile: Record<string, unknown> = USER) {
    const { fetchMe } = await import('../../src/api/auth')
    vi.mocked(fetchMe).mockResolvedValueOnce(profile as any)
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    disposeStore = () => auth.$dispose()
    await auth.loadUser()
    return auth
  }

  it('возврат в visible после простоя (>1 мин) вызывает refreshAuth', async () => {
    const { refreshAuth } = await import('../../src/api/index')
    await login()
    vi.mocked(refreshAuth).mockClear()

    // эмулируем, что прошло >1 минуты с момента последнего refresh
    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 2 * 60 * 1000)
    setVisibility('visible')

    expect(refreshAuth).toHaveBeenCalledTimes(1)
  })

  it('быстрое переключение вкладок (<1 мин) не дёргает refreshAuth', async () => {
    const { refreshAuth } = await import('../../src/api/index')
    await login()
    vi.mocked(refreshAuth).mockClear()

    setVisibility('visible')

    expect(refreshAuth).not.toHaveBeenCalled()
  })

  it('переход в hidden не вызывает refreshAuth', async () => {
    const { refreshAuth } = await import('../../src/api/index')
    await login()
    vi.mocked(refreshAuth).mockClear()

    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 2 * 60 * 1000)
    setVisibility('hidden')

    expect(refreshAuth).not.toHaveBeenCalled()
  })

  it('неавторизованный пользователь не триггерит refresh по visibility', async () => {
    const { refreshAuth } = await import('../../src/api/index')
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    disposeStore = () => auth.$dispose()

    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 2 * 60 * 1000)
    setVisibility('visible')

    expect(refreshAuth).not.toHaveBeenCalled()
  })

  it('провал refresh при возврате → грациозный экран session_expired (не loop_detected)', async () => {
    const { refreshAuth } = await import('../../src/api/index')
    const auth = await login()
    vi.mocked(refreshAuth).mockClear()
    vi.mocked(refreshAuth).mockResolvedValueOnce(false)

    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 2 * 60 * 1000)
    setVisibility('visible')
    await flush()

    expect((window as any).location.href).toContain('/auth/error?reason=session_expired')
    expect(window.sessionStorage.getItem('sso_failed')).toBe('session_expired')
    // loop-counter не трогаем: это не цикл, а ожидаемое истечение сессии.
    expect(window.sessionStorage.getItem('sso_attempts')).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('локальный пользователь не рефрешится и не выбрасывается на session_expired', async () => {
    const { refreshAuth } = await import('../../src/api/index')
    const auth = await login(LOCAL_USER)
    vi.mocked(refreshAuth).mockClear()
    // даже если бы refresh вызвали — он бы провалился (у local нет refresh_token)
    vi.mocked(refreshAuth).mockResolvedValueOnce(false)

    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 2 * 60 * 1000)
    setVisibility('visible')
    await flush()

    expect(refreshAuth).not.toHaveBeenCalled()
    expect((window as any).location.href).toBe('')
    expect(auth.isAuthenticated).toBe(true)
  })
})
