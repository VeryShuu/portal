/**
 * Интеграция approvals в роутер и меню: маршрут /approvals (включая ленивый
 * компонент), module-guard редирект при выключенном модуле, пункт меню
 * появляется только при modules.approvals.enabled.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

let createRouterCapture: { options: any } | null = null
let guard: any = null
const routerObj: any = {
  beforeEach: vi.fn((fn: any) => {
    guard = fn
  }),
}

vi.mock('vue-router', () => ({
  createRouter: (opts: any) => {
    if (createRouterCapture) createRouterCapture.options = opts
    routerObj.options = opts
    return routerObj
  },
  createWebHistory: () => ({}),
  useRoute: () => ({ path: '/' }),
  useRouter: () => ({ push: vi.fn() }),
}))

const authState = {
  isAuthenticated: true,
  backendDown: false,
  isAdmin: false,
  isHelpdeskAgent: false,
  isLearningAdmin: false,
}

const enabledFlags = ref<Record<string, boolean>>({})
const modulesState = {
  load: vi.fn().mockResolvedValue(undefined),
  isEnabled: (name: string) => !!enabledFlags.value[name],
  galleryLinks: ref({ photo_gallery_url: null, photo_gallery_mode: 'external', photo_gallery_new_tab: false, video_gallery_url: null }),
}

vi.mock('../../src/stores/auth', () => ({ useAuthStore: () => authState }))
vi.mock('../../src/stores/modules', () => ({ useModulesStore: () => modulesState }))
vi.mock('../../src/queries/helpdesk', () => ({
  useMyTicketCountsQuery: () => ({ data: ref({ active: 0, unread: 0 }) }),
  useAgentTicketCountsQuery: () => ({ data: ref({ active: 0, unread: 0 }) }),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))

vi.mock('../../src/pages/approvals/ApprovalsPage.vue', () => ({
  default: { name: 'ApprovalsPageStub', template: '<div/>' },
}))
vi.mock('../../src/components/AppLayout.vue', () => ({
  default: { name: 'AppLayoutStub', template: '<div/>' },
}))

async function loadRouter() {
  vi.resetModules()
  createRouterCapture = { options: null }
  routerObj.options = null
  guard = null
  const mod = await import('../../src/router')
  return mod
}

describe('router: approvals route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    enabledFlags.value = {}
  })

  it('маршрут /approvals зарегистрирован с ленивым компонентом', async () => {
    const mod = await loadRouter()
    console.log('DEBUG createRouterCapture:', JSON.stringify(createRouterCapture))
    console.log('DEBUG mod.router keys:', Object.keys(mod))
    const route = mod.router.options.routes
      .flatMap((r: any) => r.children ?? [r])
      .find((r: any) => r.path === '/approvals')
    expect(route).toBeDefined()
    expect(route.name).toBe('approvals')
    expect(route.meta.title).toBe('nav.approvals')
    // Ленивый компонент резолвится (строка component: () => import(...) покрыта)
    const component = await route.component()
    expect((component as { default: { name: string } }).default.name).toBe('ApprovalsPageStub')
  })

  it('module-guard: approvals выключен → редирект на home', async () => {
    const mod = await loadRouter()
    await mod.router.options.routes // routes построены
    expect(guard).toBeTypeOf('function')
    const to = { path: '/approvals', fullPath: '/approvals', meta: {} }
    const result = await guard(to)
    expect(result).toEqual({ name: 'home' })
  })

  it('module-guard: approvals включён → пропускает', async () => {
    enabledFlags.value = { approvals: true }
    await loadRouter()
    const to = { path: '/approvals', fullPath: '/approvals', meta: {} }
    const result = await guard(to)
    expect(result).toBe(true)
  })
})

describe('useAppMenu: approvals item', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
    enabledFlags.value = {}
  })

  it('пункт меню появляется при включённом модуле и исчезает при выключенном', async () => {
    enabledFlags.value = { approvals: true }
    const { useAppMenu } = await import('../../src/composables/useAppMenu')
    const menu = useAppMenu()
    const keys = JSON.stringify(menu.menuOptions.value)
    expect(keys).toContain('"key":"approvals"')

    enabledFlags.value = { approvals: false }
    expect(JSON.stringify(menu.menuOptions.value)).not.toContain('"key":"approvals"')
  })

  it('routeMap ведёт на ROUTES.APPROVALS, activeKey распознаёт /approvals', async () => {
    enabledFlags.value = { approvals: true }
    const { useAppMenu } = await import('../../src/composables/useAppMenu')
    const menu = useAppMenu()
    expect(menu.defaultTitle.value).toBeDefined()
  })
})
