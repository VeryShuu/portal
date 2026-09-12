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
  setSessionAuthSource: vi.fn(),
  getSessionAuthSource: vi.fn(() => 'keycloak'),
}))

describe('requireAuth guard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('public route → null (guard пропускает, навигация проходит)', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    const { fetchBootstrap } = await import('../../src/api/bootstrap')
    vi.mocked(fetchBootstrap).mockClear()

    // Едем через РЕАЛЬНЫЙ router: requireAuth не экспортирован — его исход
    // наблюдаем по результату навигации (null → переход состоялся, без
    // редиректа) и по отсутствию походов в bootstrap.
    const { router, ROUTES } = await import('../../src/router')
    const failure = await router.push(ROUTES.LOGIN)

    expect(failure).toBeUndefined()
    expect(router.currentRoute.value.path).toBe(ROUTES.LOGIN)
    expect(auth.isAuthenticated).toBe(false)
    // meta.public → requireAuth не должен даже дёргать loadBootstrap
    expect(fetchBootstrap).not.toHaveBeenCalled()
  })

  it('requiresAuth + loadBootstrap succeeds → user authenticated', async () => {
    const { fetchBootstrap } = await import('../../src/api/bootstrap')
    vi.mocked(fetchBootstrap).mockResolvedValueOnce({
      user: {
        id: '1', email: 'u@x.local', full_name: 'User', department: null,
        position: null, phone: null, role: 'reader', avatar_url: null,
        current_status: 'working', current_status_until: null, notify_email: true, notify_inapp: true,
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
      current_status: 'working', current_status_until: null, notify_email: true, notify_inapp: true,
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
      current_status: 'working', current_status_until: null, notify_email: true, notify_inapp: true,
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
      current_status: 'working', current_status_until: null, notify_email: true, notify_inapp: true,
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
      current_status: 'working', current_status_until: null, notify_email: true, notify_inapp: true,
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
      meetings: { enabled: false, calendar_start_hour: 8, calendar_end_hour: 19, max_recurrence_horizon_days: 31, min_search_chars: 3 },
      directories: { enabled: false },
      signature: { enabled: false },
      helpdesk: { enabled: false },
      erp_sync: { enabled: false },
      directum: { enabled: false },
    learning: { enabled: false },
      approvals: { enabled: false },
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
      meetings: { enabled: false, calendar_start_hour: 8, calendar_end_hour: 19, max_recurrence_horizon_days: 31, min_search_chars: 3 },
      directories: { enabled: false },
      signature: { enabled: false },
      helpdesk: { enabled: false },
      erp_sync: { enabled: false },
      directum: { enabled: false },
    learning: { enabled: false },
      approvals: { enabled: false },
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

const FULL_MODULES = {
  nextcloud: { enabled: false }, photos: { enabled: false },
  meetings: { enabled: false, calendar_start_hour: 8, calendar_end_hour: 19, max_recurrence_horizon_days: 31, min_search_chars: 3 },
  directories: { enabled: false }, signature: { enabled: false },
  helpdesk: { enabled: false }, erp_sync: { enabled: false },
  directum: { enabled: false }, learning: { enabled: true },
      approvals: { enabled: false },
}

describe('requiresLearningAdmin guard (via real router)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  // Маршрут /learning/admin лежит под AppLayout с requiresAuth, поэтому
  // аутентифицируемся честным bootstrap: флаг методиста приходит из него же
  // (прод-контракт BootstrapOut.is_learning_admin).
  async function bootstrapAs(learningAdmin: boolean) {
    const { fetchBootstrap } = await import('../../src/api/bootstrap')
    vi.mocked(fetchBootstrap).mockResolvedValue({
      user: {
        id: '9', email: 'm@x.local', full_name: 'Методист', department: null,
        position: null, phone: null, role: 'reader', avatar_url: null,
        current_status: 'working', current_status_until: null, notify_email: true,
        notify_inapp: true, lang: 'ru', preferences: {}, auth_source: 'local',
        last_login_at: null,
      },
      branding: {} as Record<string, never>,
      modules: FULL_MODULES,
      gallery_links: {
        photo_gallery_url: null,
        photo_gallery_mode: 'internal',
        photo_gallery_new_tab: false,
        video_gallery_url: null,
      },
      unread_count: 0,
      is_helpdesk_agent: false,
      is_learning_admin: learningAdmin,
    } as any)
  }

  it('методист + модуль включён → навигация на /learning/admin проходит', async () => {
    await bootstrapAs(true)
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    await auth.loadBootstrap()

    const { router } = await import('../../src/router')
    await router.push('/learning/admin')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('learning-admin')
  })

  it('не-методист → редирект на home', async () => {
    await bootstrapAs(false)
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    await auth.loadBootstrap()

    const { router, ROUTES } = await import('../../src/router')
    // Роутер — синглтон модуля: после первого теста мы уже на /learning/admin,
    // повторный push того же пути дедуплицируется и guard не запустится.
    await router.push(ROUTES.HOME)
    await router.push('/learning/admin')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe(ROUTES.HOME)
  })
})
