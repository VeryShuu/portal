import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), go: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/', name: 'home' })),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    loadUser: vi.fn(),
    redirectToSSO: vi.fn(),
  })),
}))

const globalPlugins = {
  plugins: [i18n],
}

describe('AuthCallbackPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders a spinner', async () => {
    const AuthCallbackPage = (await import('../../src/pages/AuthCallbackPage.vue')).default
    const wrapper = mount(AuthCallbackPage, { global: globalPlugins })
    expect(wrapper.exists()).toBe(true)
  })
})
