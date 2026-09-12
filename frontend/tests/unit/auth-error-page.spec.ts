import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'loading', 'block'],
    emits: ['click'],
  },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title'] },
}))

vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/', name: 'home' })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({ clearSSOState: vi.fn() })),
}))

vi.mock('../../src/stores/branding', () => ({
  useBrandingStore: vi.fn(() => ({
    settings: {
      portal_name: '',
      portal_tagline: '',
      has_login_bg: false,
    },
  })),
}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
  },
}

describe('AuthErrorPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders the form column', async () => {
    const AuthErrorPage = (await import('../../src/pages/AuthErrorPage.vue')).default
    const wrapper = mount(AuthErrorPage, { global: globalPlugins })
    expect(wrapper.find('.login-form-col').exists()).toBe(true)
  })

  it('shows the error alert', async () => {
    const AuthErrorPage = (await import('../../src/pages/AuthErrorPage.vue')).default
    const wrapper = mount(AuthErrorPage, { global: globalPlugins })
    expect(wrapper.find('.n-alert').exists()).toBe(true)
  })

  it('has retry button', async () => {
    const AuthErrorPage = (await import('../../src/pages/AuthErrorPage.vue')).default
    const wrapper = mount(AuthErrorPage, { global: globalPlugins })
    expect(wrapper.findAll('button').length).toBeGreaterThan(0)
  })
})
