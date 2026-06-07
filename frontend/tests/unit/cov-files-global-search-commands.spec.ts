import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const ROUTES = {
  HOME: '/',
  NEWS: '/news',
  KB: '/kb',
  PROFILE: '/profile',
  ADMIN: '/admin',
  LINKS: '/links',
  FILES: '/files',
  PHOTOS: '/photos',
  MEETINGS: '/meetings',
} as const

const mockAuth = {
  isEditor: false,
  isAdmin: false,
  logout: vi.fn(),
}

const mockThemeStore = {
  toggle: vi.fn(),
}

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string) => k,
  }),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => mockAuth,
}))

vi.mock('../../src/stores/theme', () => ({
  useThemeStore: () => mockThemeStore,
}))

vi.mock('../../src/router', () => ({
  ROUTES,
}))

type CommandsApi = Awaited<ReturnType<typeof setupHost>>['api']

async function setupHost(initialQuery = '>') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: ROUTES.HOME, component: { template: '<div/>' } },
      { path: ROUTES.NEWS, component: { template: '<div/>' } },
      { path: `${ROUTES.NEWS}/create`, component: { template: '<div/>' } },
      { path: ROUTES.KB, component: { template: '<div/>' } },
      { path: ROUTES.PROFILE, component: { template: '<div/>' } },
      { path: ROUTES.ADMIN, component: { template: '<div/>' } },
      { path: ROUTES.LINKS, component: { template: '<div/>' } },
      { path: ROUTES.FILES, component: { template: '<div/>' } },
      { path: ROUTES.PHOTOS, component: { template: '<div/>' } },
      { path: ROUTES.MEETINGS, component: { template: '<div/>' } },
    ],
  })
  await router.push(ROUTES.HOME)
  await router.isReady()

  const close = vi.fn()
  const query = ref(initialQuery)
  const { useGlobalSearchCommands } = await import('../../src/composables/useGlobalSearchCommands')

  let api: any = null
  const Host = defineComponent({
    setup() {
      api = useGlobalSearchCommands(query, close)
      return () => h('div')
    },
  })

  mount(Host, { global: { plugins: [router] } })

  return {
    api: api as CommandsApi,
    query,
    close,
    router,
  }
}

function ids(api: CommandsApi): string[] {
  return api.filteredCommands.value.map((c) => c.id)
}

describe('useGlobalSearchCommands', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuth.isEditor = false
    mockAuth.isAdmin = false
  })

  it('detects command mode and returns base commands for non-editor/non-admin', async () => {
    const { api, query } = await setupHost('plain text')

    expect(api.isCommandMode.value).toBe(false)

    query.value = '>'
    await nextTick()

    expect(api.isCommandMode.value).toBe(true)
    expect(ids(api)).toEqual([
      'go-home',
      'go-news',
      'go-kb',
      'go-profile',
      'toggle-theme',
      'logout',
    ])
  })

  it('adds editor and admin commands by role and filters by command query', async () => {
    mockAuth.isEditor = true
    mockAuth.isAdmin = true

    const { api, query } = await setupHost('>')

    const all = ids(api)
    expect(all).toContain('create-news')
    expect(all).toContain('manage-news-categories')
    expect(all).toContain('go-admin')
    expect(all).toContain('manage-world-clock')
    expect(all).toContain('manage-links')
    expect(all).toContain('manage-file-icons')
    expect(all).toContain('manage-kb')
    expect(all).toContain('manage-photos-module')
    expect(all).toContain('manage-meetings-module')

    query.value = '>manage'
    await nextTick()
    expect(ids(api)).not.toContain('create-news')

    query.value = '>toggle'
    await nextTick()

    expect(ids(api)).toEqual(['toggle-theme'])
  })

  it('executes navigation, theme toggle, and logout actions with close callback', async () => {
    mockAuth.isEditor = true
    mockAuth.isAdmin = true

    const { api, close, router } = await setupHost('>')
    const pushSpy = vi.spyOn(router, 'push')

    api.filteredCommands.value.find((c) => c.id === 'go-home')?.action()
    expect(pushSpy).toHaveBeenLastCalledWith('/')

    api.filteredCommands.value.find((c) => c.id === 'create-news')?.action()
    expect(pushSpy).toHaveBeenLastCalledWith('/news/create')

    api.filteredCommands.value.find((c) => c.id === 'manage-news-categories')?.action()
    expect(pushSpy).toHaveBeenLastCalledWith({ path: '/news', query: { manage: 'categories' } })

    api.filteredCommands.value.find((c) => c.id === 'manage-world-clock')?.action()
    expect(pushSpy).toHaveBeenLastCalledWith({ path: '/', query: { manage: 'world-clock' } })

    api.filteredCommands.value.find((c) => c.id === 'toggle-theme')?.action()
    expect(mockThemeStore.toggle).toHaveBeenCalledTimes(1)

    api.filteredCommands.value.find((c) => c.id === 'logout')?.action()
    expect(mockAuth.logout).toHaveBeenCalledTimes(1)

    expect(close).toHaveBeenCalledTimes(6)
  })
})
