import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

import { useAppMenu } from '../../src/composables/useAppMenu'
import { ROUTES } from '../../src/router'
import { useAuthStore } from '../../src/stores/auth'
import { useModulesStore } from '../../src/stores/modules'
import { queryKeys } from '../../src/queries/keys'

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'ru',
    messages: { ru: {} },
    missingWarn: false,
    fallbackWarn: false,
    silentFallbackWarn: true,
    silentTranslationWarn: true,
  })
}

function makeRouter(initial = '/') {
  const r = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/:pathMatch(.*)*', component: { render: () => null } },
    ],
  })
  r.push(initial)
  return r
}

async function setup(opts: {
  path?: string
  role?: 'reader' | 'editor' | 'admin'
  modulesEnabled?: string[]
  gallery?: Partial<{
    photo_gallery_url: string | null
    photo_gallery_mode: 'internal' | 'external' | null
    photo_gallery_new_tab: boolean
    video_gallery_url: string | null
  }>
} = {}) {
  setActivePinia(createPinia())
  const router = makeRouter(opts.path ?? '/')
  await router.isReady()
  const i18n = makeI18n()

  const auth = useAuthStore()
  auth.user = {
    id: '1', email: 'a@b', full_name: 'A', department: null, position: null,
    phone: null, role: opts.role ?? 'reader', avatar_url: null,
    current_status: 'working', current_status_until: null, notify_email: true, notify_inapp: true,
    lang: 'ru', preferences: {}, auth_source: 'local', last_login_at: null,
  } as any

  const modules = useModulesStore()
  const enabled = new Set(opts.modulesEnabled ?? [])
  ;(modules as any).isEnabled = (name: string) => enabled.has(name)
  ;(modules as any).galleryLinks = {
    photo_gallery_url: opts.gallery?.photo_gallery_url ?? null,
    photo_gallery_mode: opts.gallery?.photo_gallery_mode ?? null,
    photo_gallery_new_tab: opts.gallery?.photo_gallery_new_tab ?? false,
    video_gallery_url: opts.gallery?.video_gallery_url ?? null,
  }

  let captured: ReturnType<typeof useAppMenu> | null = null
  const Host = defineComponent({
    setup() {
      captured = useAppMenu()
      return () => h('div')
    },
  })

  // useAppMenu дёргает useMyTicketCountsQuery / useAgentTicketCountsQuery —
  // для unit-теста нужен VueQueryPlugin с QueryClient (queries по умолчанию
  // disabled через enabled=false, т.к. модуль helpdesk в тестах выключен).
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  mount(Host, { global: { plugins: [router, i18n, [VueQueryPlugin, { queryClient }]] } })
  await nextTick()
  return { menu: captured!, router, modules, auth, queryClient }
}

/** VNode бейджа-цифры пункта меню (второй child лейбла) — для проверок класса. */
function badgeVnodeOf(menuOptionLabel: () => unknown): any {
  const labelVnode = (menuOptionLabel as () => any)()
  return labelVnode.children?.[1]
}

describe('useAppMenu', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('activeKey is "home" on root path', async () => {
    const { menu } = await setup({ path: '/' })
    expect(menu.activeKey.value).toBe('home')
  })

  it('activeKey resolves news, kb, files, links, bookmarks', async () => {
    for (const [path, key] of [
      [ROUTES.NEWS, 'news'],
      [ROUTES.KB, 'kb'],
      [ROUTES.FILES, 'files'],
      [ROUTES.LINKS, 'links'],
      [ROUTES.BOOKMARKS, 'links'],
      [ROUTES.STAFF, 'staff'],
      [ROUTES.PHOTOS, 'photo-gallery'],
      [ROUTES.PROFILE, 'profile'],
      [ROUTES.MY_FEEDBACK, 'my-feedback'],
      [ROUTES.SETTINGS, 'settings'],
      [ROUTES.ADMIN, 'admin'],
      [ROUTES.TRASH, 'trash'],
    ] as const) {
      const { menu } = await setup({ path })
      expect(menu.activeKey.value).toBe(key)
    }
  })

  it('menuOptions hide files when nextcloud disabled, show when enabled', async () => {
    const { menu: m1 } = await setup({ modulesEnabled: [] })
    const work1 = (m1.menuOptions.value.find((g: any) => g.key === 'g-work') as any).children
    expect(work1.find((c: any) => c.key === 'files')).toBeUndefined()

    const { menu: m2 } = await setup({ modulesEnabled: ['nextcloud'] })
    const work2 = (m2.menuOptions.value.find((g: any) => g.key === 'g-work') as any).children
    expect(work2.find((c: any) => c.key === 'files')).toBeDefined()
  })

  it('menuOptions include photo-gallery and video-gallery when configured', async () => {
    const { menu } = await setup({
      gallery: {
        photo_gallery_mode: 'internal',
        video_gallery_url: 'https://video.example/',
      },
    })
    const services = (menu.menuOptions.value.find((g: any) => g.key === 'g-services') as any).children
    expect(services.find((c: any) => c.key === 'photo-gallery')).toBeDefined()
    expect(services.find((c: any) => c.key === 'video-gallery')).toBeDefined()
  })

  it('menuOptions reflect admin role (admin visible)', async () => {
    const { menu } = await setup({ role: 'admin' })
    const acc = (menu.menuOptions.value.find((g: any) => g.key === 'g-account') as any).children
    const keys = acc.map((c: any) => c.key)
    expect(keys).toContain('admin')
  })

  it('menuOptions hide admin-only items for reader', async () => {
    const { menu } = await setup({ role: 'reader' })
    const acc = (menu.menuOptions.value.find((g: any) => g.key === 'g-account') as any).children
    const keys = acc.map((c: any) => c.key)
    expect(keys).not.toContain('admin')
  })

  it('handleMenuSelect routes simple keys via router.push', async () => {
    const { menu, router } = await setup()
    const spy = vi.spyOn(router, 'push').mockResolvedValue(undefined as any)
    menu.handleMenuSelect('news')
    expect(spy).toHaveBeenCalledWith(ROUTES.NEWS)
  })

  it('handleMenuSelect for unknown key falls back to HOME', async () => {
    const { menu, router } = await setup()
    const spy = vi.spyOn(router, 'push').mockResolvedValue(undefined as any)
    menu.handleMenuSelect('unknown')
    expect(spy).toHaveBeenCalledWith(ROUTES.HOME)
  })

  it('handleMenuSelect photo-gallery internal goes to /photos', async () => {
    const { menu, router } = await setup({
      gallery: { photo_gallery_mode: 'internal' },
    })
    const spy = vi.spyOn(router, 'push').mockResolvedValue(undefined as any)
    menu.handleMenuSelect('photo-gallery')
    expect(spy).toHaveBeenCalledWith(ROUTES.PHOTOS)
  })

  it('handleMenuSelect photo-gallery external + new_tab opens window', async () => {
    const { menu } = await setup({
      gallery: {
        photo_gallery_mode: 'external',
        photo_gallery_url: 'https://external/',
        photo_gallery_new_tab: true,
      },
    })
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    menu.handleMenuSelect('photo-gallery')
    expect(openSpy).toHaveBeenCalledWith('https://external/', '_blank', 'noopener,noreferrer')
    openSpy.mockRestore()
  })

  it('handleMenuSelect video-gallery (internal path) uses router.push', async () => {
    const { menu, router } = await setup({
      gallery: { video_gallery_url: '/video' },
    })
    const spy = vi.spyOn(router, 'push').mockResolvedValue(undefined as any)
    menu.handleMenuSelect('video-gallery')
    expect(spy).toHaveBeenCalledWith('/video')
  })

  it('handleMenuSelect video-gallery (external) opens window', async () => {
    const { menu } = await setup({
      gallery: { video_gallery_url: 'https://video.example/' },
    })
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    menu.handleMenuSelect('video-gallery')
    expect(openSpy).toHaveBeenCalledWith(
      'https://video.example/',
      '_blank',
      'noopener,noreferrer',
    )
    openSpy.mockRestore()
  })

  it('defaultTitle returns localized fallback per key', async () => {
    const { menu } = await setup({ path: '/' })
    // i18n возвращает ключ при отсутствии перевода — нам важно, что значение определено.
    expect(typeof menu.defaultTitle.value).toBe('string')
  })

  // ── Helpdesk-бейджи: цифра + красная подсветка непрочитанных ─────────────
  function findOption(menu: ReturnType<typeof useAppMenu>, key: string): any {
    for (const group of menu.menuOptions.value as any[]) {
      const hit = (group.children ?? []).find((c: any) => c.key === key)
      if (hit) return hit
    }
    return undefined
  }

  it('helpdesk-inbox badge gray when unread = 0, red when unread > 0', async () => {
    const { menu, auth, queryClient } = await setup({
      role: 'admin',
      modulesEnabled: ['helpdesk'],
    })
    ;(auth as any).isHelpdeskAgent = true

    // Серый: активные есть, непрочитанных нет (Vue нормализует class без
    // falsy-модификаторов в чистую строку).
    queryClient.setQueryData(queryKeys.helpdesk.agentTicketCounts(), { active: 2, unread: 0 })
    await nextTick()
    let badge = badgeVnodeOf(findOption(menu, 'helpdesk-inbox').label)
    expect(badge).toBeTruthy()
    expect(badge.children).toBe('2')
    expect(String(badge.props.class)).toBe('menu-count-badge')

    // Красный: появился непрочитанный ответ заявителя.
    queryClient.setQueryData(queryKeys.helpdesk.agentTicketCounts(), { active: 2, unread: 1 })
    await nextTick()
    badge = badgeVnodeOf(findOption(menu, 'helpdesk-inbox').label)
    expect(String(badge.props.class)).toContain('menu-count-badge--unread')
  })

  it('helpdesk-inbox badge hidden when active = 0 (даже с unread)', async () => {
    const { menu, auth, queryClient } = await setup({
      role: 'admin',
      modulesEnabled: ['helpdesk'],
    })
    ;(auth as any).isHelpdeskAgent = true

    // Нет активных — цифры нет вообще (0 не рисуем); unread сам по себе
    // бейдж не оживляет: непрочитанное возможно только внутри активных.
    queryClient.setQueryData(queryKeys.helpdesk.agentTicketCounts(), { active: 0, unread: 0 })
    await nextTick()
    expect(badgeVnodeOf(findOption(menu, 'helpdesk-inbox').label)).toBeNull()
  })

  it('helpdesk-my badge краснеет при непрочитанных ответах поддержки', async () => {
    const { menu, queryClient } = await setup({ modulesEnabled: ['helpdesk'] })

    queryClient.setQueryData(queryKeys.helpdesk.myTicketCounts(), { active: 1, unread: 0 })
    await nextTick()
    let badge = badgeVnodeOf(findOption(menu, 'helpdesk-my').label)
    expect(badge).toBeTruthy()
    expect(badge.children).toBe('1')
    expect(String(badge.props.class)).toBe('menu-count-badge')

    queryClient.setQueryData(queryKeys.helpdesk.myTicketCounts(), { active: 1, unread: 2 })
    await nextTick()
    badge = badgeVnodeOf(findOption(menu, 'helpdesk-my').label)
    expect(String(badge.props.class)).toContain('menu-count-badge--unread')
  })

  it('learning-admin item shows for methodist with module enabled, hidden otherwise', async () => {
    // Не-методист + модуль включён → пункта нет
    const a = await setup({ role: 'reader', modulesEnabled: ['learning'] })
    let g = (a.menu.menuOptions.value.find((x: any) => x.key === 'g-account') as any)
    expect(g.children.some((c: any) => c.key === 'learning-admin')).toBe(false)

    // Методист (флаг из bootstrap) + модуль включён → пункт есть и ведёт на /learning/admin
    const b = await setup({ role: 'reader', modulesEnabled: ['learning'] })
    b.auth.isLearningAdmin = true
    await nextTick()
    g = (b.menu.menuOptions.value.find((x: any) => x.key === 'g-account') as any)
    const item = g.children.find((c: any) => c.key === 'learning-admin')
    expect(item).toBeTruthy()

    // handleMenuSelect ведёт на админку методиста (в тестовом роутере реального
    // маршрута нет — проверяем сам вызов push, как для остальных пунктов)
    const pushSpy = vi.spyOn(b.router, 'push').mockResolvedValue(undefined as any)
    b.menu.handleMenuSelect('learning-admin')
    expect(pushSpy).toHaveBeenCalledWith(ROUTES.LEARNING_ADMIN)
  })

  it('activeKey resolves learning-admin path', async () => {
    const { menu } = await setup({ path: ROUTES.LEARNING_ADMIN })
    expect(menu.activeKey.value).toBe('learning-admin')
  })
})
