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
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type'],
    emits: ['update:value'],
  },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title'] },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/', name: 'home' })),
}))

vi.mock('@/i18n', () => ({
  loadLocale: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../../src/api/auth', () => ({
  localLogin: vi.fn(),
}))

vi.mock('../../src/api/index', () => ({
  api: vi.fn().mockResolvedValue({ local_auth_enabled: true, keycloak_enabled: true }),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    isAuthenticated: false,
    loadBootstrap: vi.fn(),
  })),
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
}

describe('AuthLocalPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders login form column', async () => {
    const AuthLocalPage = (await import('../../src/pages/AuthLocalPage.vue')).default
    const wrapper = mount(AuthLocalPage, { global: globalPlugins })
    expect(wrapper.find('.login-form-col').exists()).toBe(true)
  })

  it('renders form elements', async () => {
    const AuthLocalPage = (await import('../../src/pages/AuthLocalPage.vue')).default
    const wrapper = mount(AuthLocalPage, { global: globalPlugins })
    expect(wrapper.find('.login-form').exists()).toBe(true)
  })
})
