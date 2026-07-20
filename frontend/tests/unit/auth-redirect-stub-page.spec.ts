import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/', name: 'home' })),
}))

const globalPlugins = {
  plugins: [i18n],
}

describe('AuthRedirectStub.vue', () => {
  it('renders a div without errors', async () => {
    Object.defineProperty(window, 'location', {
      value: { replace: vi.fn(), href: '/' },
      writable: true,
    })
    const AuthRedirectStub = (await import('../../src/pages/AuthRedirectStub.vue')).default
    const wrapper = mount(AuthRedirectStub, { global: globalPlugins })
    expect(wrapper.exists()).toBe(true)
  })
})
