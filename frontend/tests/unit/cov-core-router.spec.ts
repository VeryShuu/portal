import { beforeEach, describe, expect, it, vi } from 'vitest'

const createRouterMock = vi.fn()
const createWebHistoryMock = vi.fn()

let authState: any
let modulesState: any

vi.mock('vue-router', () => ({
  createRouter: (...args: any[]) => createRouterMock(...args),
  createWebHistory: (...args: any[]) => createWebHistoryMock(...args),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => authState,
}))

vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => modulesState,
}))

async function loadRouterModule() {
  vi.resetModules()

  let guard: any = null
  const routerObj: any = {
    beforeEach: vi.fn((fn: any) => {
      guard = fn
    }),
  }

  createWebHistoryMock.mockReturnValue({})
  createRouterMock.mockImplementation((opts: any) => {
    routerObj.options = opts
    return routerObj
  })

  authState = {
    isAuthenticated: true,
    backendDown: false,
    isEditor: false,
    isAdmin: false,
    loadBootstrap: vi.fn().mockResolvedValue('ok'),
    redirectToSSO: vi.fn(),
  }

  modulesState = {
    load: vi.fn().mockResolvedValue(undefined),
    isEnabled: vi.fn().mockReturnValue(true),
  }

  const mod = await import('../../src/router')
  return { ...mod, guard, routerObj }
}

describe('src/router', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('exports key route constants', async () => {
    const { ROUTES } = await loadRouterModule()
    expect(ROUTES.HOME).toBe('/')
    expect(ROUTES.FILES).toBe('/files')
    expect(ROUTES.AUTH_ERROR).toBe('/auth/error')
    expect(ROUTES.PHOTOS_PUBLIC_PHOTO).toBe('/p/:token')
  })

  it('registers beforeEach and defines public routes', async () => {
    const { guard, routerObj, ROUTES } = await loadRouterModule()
    expect(typeof guard).toBe('function')

    const routes = routerObj.options.routes
    const loginRoute = routes.find((r: any) => r.path === ROUTES.LOGIN)
    expect(loginRoute.meta.public).toBe(true)

    const root = routes.find((r: any) => r.path === ROUTES.HOME)
    const settingsRoute = root.children.find((c: any) => c.path === ROUTES.SETTINGS)
    expect(typeof settingsRoute.redirect).toBe('function')
  })

  it('settings redirect maps tabs to proper targets and default', async () => {
    const { routerObj, ROUTES } = await loadRouterModule()
    const root = routerObj.options.routes.find((r: any) => r.path === ROUTES.HOME)
    const settingsRoute = root.children.find((c: any) => c.path === ROUTES.SETTINGS)
    const redirect = settingsRoute.redirect

    expect(redirect({ query: { tab: 'links' } })).toEqual({ path: ROUTES.LINKS, query: { manage: 'links' } })
    expect(redirect({ query: { tab: 'branding' } })).toEqual({ path: ROUTES.ADMIN, query: { tab: 'branding' } })
    expect(redirect({ query: { tab: 'news-categories' } })).toEqual({ path: ROUTES.NEWS, query: { manage: 'categories' } })
    expect(redirect({ query: { tab: 'world-clock' } })).toEqual({ path: ROUTES.HOME, query: { manage: 'world-clock' } })
    expect(redirect({ query: { tab: 'kb' } })).toEqual({ path: ROUTES.KB, query: { manage: 'kb' } })
    expect(redirect({ query: { tab: 'file-icons' } })).toEqual({ path: ROUTES.FILES, query: { manage: 'file-icons' } })
    expect(redirect({ query: { tab: 'unknown' } })).toEqual({ path: ROUTES.ADMIN })
  })

  it('bookmarks route redirects to links tab=my', async () => {
    const { routerObj, ROUTES } = await loadRouterModule()
    const root = routerObj.options.routes.find((r: any) => r.path === ROUTES.HOME)
    const bookmarks = root.children.find((c: any) => c.path === ROUTES.BOOKMARKS)
    expect(bookmarks.redirect).toEqual({ name: 'links', query: { tab: 'my' } })
  })

  it('guard returns auth-error on bootstrap network error for protected route', async () => {
    const { guard } = await loadRouterModule()
    authState.isAuthenticated = false
    authState.loadBootstrap.mockResolvedValueOnce('network_error')

    const to = { path: '/files', fullPath: '/files', meta: { requiresAuth: true } }
    await expect(guard(to)).resolves.toEqual({ name: 'auth-error' })
  })

  it('guard redirects unauthenticated protected route via SSO and returns false', async () => {
    const { guard } = await loadRouterModule()
    authState.isAuthenticated = false

    const to = { path: '/news/create', fullPath: '/news/create?x=1', meta: { requiresAuth: true } }
    await expect(guard(to)).resolves.toBe(false)
    expect(authState.redirectToSSO).toHaveBeenCalledWith('/news/create?x=1')
  })

  it('guard returns false without redirect when backendDown=true', async () => {
    const { guard } = await loadRouterModule()
    authState.isAuthenticated = false
    authState.backendDown = true

    const to = { path: '/kb', fullPath: '/kb', meta: { requiresAuth: true } }
    await expect(guard(to)).resolves.toBe(false)
    expect(authState.redirectToSSO).not.toHaveBeenCalled()
  })

  it('guard enforces editor/admin role routes', async () => {
    const { guard } = await loadRouterModule()
    authState.isAuthenticated = true
    authState.isEditor = false
    authState.isAdmin = false

    await expect(guard({ path: '/news/create', fullPath: '/news/create', meta: { requiresAuth: true, requiresEditor: true } })).resolves.toEqual({ name: 'home' })
    await expect(guard({ path: '/admin', fullPath: '/admin', meta: { requiresAuth: true, requiresAdmin: true } })).resolves.toEqual({ name: 'home' })
  })

  it('guard skips role check when route does not require auth', async () => {
    const { guard } = await loadRouterModule()
    authState.isAuthenticated = true
    authState.isEditor = false

    await expect(guard({ path: '/p/token', fullPath: '/p/token', meta: { requiresAuth: false, requiresEditor: true } })).resolves.toBe(true)
  })

  it('guard checks module access for matching path and redirects home when disabled', async () => {
    const { guard } = await loadRouterModule()
    authState.isAuthenticated = true
    modulesState.isEnabled.mockReturnValue(false)

    await expect(guard({ path: '/files/f1', fullPath: '/files/f1', meta: { requiresAuth: true } })).resolves.toEqual({ name: 'home' })
    expect(modulesState.load).toHaveBeenCalled()
    expect(modulesState.isEnabled).toHaveBeenCalledWith('nextcloud')
  })

  it('guard fails closed when module loading throws and module is not enabled', async () => {
    const { guard } = await loadRouterModule()
    authState.isAuthenticated = true
    modulesState.load.mockRejectedValueOnce(new Error('network'))
    modulesState.isEnabled.mockReturnValue(false)

    await expect(guard({ path: '/photos/albums', fullPath: '/photos/albums', meta: { requiresAuth: true } })).resolves.toEqual({ name: 'home' })
    expect(modulesState.isEnabled).toHaveBeenCalledWith('photos')
  })

  it('guard allows when module route enabled and path not matched', async () => {
    const { guard } = await loadRouterModule()
    authState.isAuthenticated = true
    modulesState.isEnabled.mockReturnValue(true)

    await expect(guard({ path: '/meetings', fullPath: '/meetings', meta: { requiresAuth: true } })).resolves.toBe(true)
    await expect(guard({ path: '/news', fullPath: '/news', meta: { requiresAuth: true } })).resolves.toBe(true)
  })

  it('guard returns true for unauthenticated public route', async () => {
    const { guard } = await loadRouterModule()
    authState.isAuthenticated = false

    await expect(guard({ path: '/login', fullPath: '/login', meta: { public: true, requiresAuth: false } })).resolves.toBe(true)
  })
})
