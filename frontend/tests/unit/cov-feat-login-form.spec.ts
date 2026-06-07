import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const loadLocale = vi.fn()
const localLogin = vi.fn()
const getSSOLoginUrl = vi.fn((redirect: string) => `https://sso.test?redirect=${encodeURIComponent(redirect)}`)
const loadUser = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: ref('en') }),
}))

vi.mock('@/i18n', () => ({
  loadLocale: (...args: any[]) => loadLocale(...args),
}))

vi.mock('../../src/api/auth', () => ({
  localLogin: (...args: any[]) => localLogin(...args),
  getSSOLoginUrl: (...args: any[]) => getSSOLoginUrl(...args),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({ loadUser }),
}))

async function setupHost(path = '/login') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: { template: '<div />' } },
      { path: '/staff', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()

  let api: any = null
  const mod = await import('../../src/composables/useLoginForm')
  const Host = defineComponent({
    setup() {
      api = mod.useLoginForm()
      return () => h('div')
    },
  })
  mount(Host, { global: { plugins: [router] } })
  return { api, router }
}

describe('cov-feat useLoginForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('sanitizes redirect query values', async () => {
    const a = await setupHost('/login?redirect=/dashboard?x=1')
    expect(a.api.redirectTo).toBe('/dashboard?x=1')

    const b = await setupHost('/login?redirect=//evil.com')
    expect(b.api.redirectTo).toBe('/')

    const c = await setupHost('/login?redirect=/api/hijack')
    expect(c.api.redirectTo).toBe('/')

    const d = await setupHost('/login?redirect=/realms/secret')
    expect(d.api.redirectTo).toBe('/')
  })

  it('loginSSO sets loading and redirects to SSO URL', async () => {
    const { api } = await setupHost('/login?redirect=/target')
    api.loginSSO()
    expect(api.ssoLoading.value).toBe(true)
    expect(getSSOLoginUrl).toHaveBeenCalledWith('/target')
  })

  it('loginLocal returns when form validation fails', async () => {
    const { api } = await setupHost('/login')
    api.formRef.value = { validate: vi.fn().mockRejectedValue(new Error('bad')) }
    await api.loginLocal()
    expect(localLogin).not.toHaveBeenCalled()
    expect(api.localLoading.value).toBe(false)
  })

  it('loginLocal success loads user and routes to redirect', async () => {
    const { api, router } = await setupHost('/login?redirect=/staff')
    const pushSpy = vi.spyOn(router, 'push')
    api.formRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    api.form.value.email = 'a@b.com'
    api.form.value.password = 'pw'

    localLogin.mockResolvedValueOnce({})
    loadUser.mockResolvedValueOnce({})

    await api.loginLocal()
    expect(localLogin).toHaveBeenCalledWith('a@b.com', 'pw')
    expect(loadUser).toHaveBeenCalled()
    expect(pushSpy).toHaveBeenCalledWith('/staff')
    expect(api.localLoading.value).toBe(false)
  })

  it('loginLocal maps 403/429/default errors to user-facing messages', async () => {
    const { api } = await setupHost('/login')
    api.formRef.value = { validate: vi.fn().mockResolvedValue(undefined) }

    localLogin.mockRejectedValueOnce({ status: 403, body: { detail: 'Local authentication is disabled' } })
    await api.loginLocal()
    expect(api.error.value).toBe('auth.localAuthDisabled')

    localLogin.mockRejectedValueOnce({ status: 403, body: { detail: 'Other' } })
    await api.loginLocal()
    expect(api.error.value).toBe('auth.useSSO')

    localLogin.mockRejectedValueOnce({ status: 429 })
    await api.loginLocal()
    expect(api.error.value).toBe('auth.rateLimited')

    localLogin.mockRejectedValueOnce({ status: 401 })
    await api.loginLocal()
    expect(api.error.value).toBe('auth.invalidCredentials')
  })

  it('setLang loads locale and persists it', async () => {
    const { api } = await setupHost('/login')
    loadLocale.mockResolvedValueOnce(undefined)
    await api.setLang('ru')
    expect(loadLocale).toHaveBeenCalledWith('ru')
    expect(api.locale.value).toBe('ru')
    expect(localStorage.getItem('lang')).toBe('ru')
  })
})
