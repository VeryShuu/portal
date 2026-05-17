import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import { useAppMenu } from '../../src/composables/useAppMenu'
import { ROUTES } from '../../src/router'
import { useAuthStore } from '../../src/stores/auth'
import { useModulesStore } from '../../src/stores/modules'

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
    presence_status: 'office', notify_email: true, notify_inapp: true,
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

  mount(Host, { global: { plugins: [router, i18n] } })
  await nextTick()
  return { menu: captured!, router, modules, auth }
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

  it('menuOptions reflect admin role (settings/admin/trash visible)', async () => {
    const { menu } = await setup({ role: 'admin' })
    const acc = (menu.menuOptions.value.find((g: any) => g.key === 'g-account') as any).children
    const keys = acc.map((c: any) => c.key)
    expect(keys).toContain('settings')
    expect(keys).toContain('admin')
    expect(keys).toContain('trash')
  })

  it('menuOptions hide admin-only items for reader', async () => {
    const { menu } = await setup({ role: 'reader' })
    const acc = (menu.menuOptions.value.find((g: any) => g.key === 'g-account') as any).children
    const keys = acc.map((c: any) => c.key)
    expect(keys).not.toContain('settings')
    expect(keys).not.toContain('admin')
    expect(keys).not.toContain('trash')
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
})
