import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const MOCK_USER = {
  id: '00000000-0000-0000-0000-000000000001',
  full_name: 'Иван Иванов',
  email: 'ivan@example.com',
  role: 'reader' as const,
  auth_source: 'keycloak' as const,
  avatar_url: null,
  is_active: true,
  position: 'Разработчик',
  department: 'ИТ',
  phone: '+7 (999) 123-45-67',
  attributes: { mobile: '+7 (888) 000-00-00', city: 'Москва' },
}

describe('HeroBlock.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders section.hero element', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.find('section.hero').exists()).toBe(true)
  })

  it('shows greeting with user first name', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = { ...MOCK_USER } as any
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.text()).toContain('Иван')
  })

  it('shows custom welcome subtitle from branding', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useBrandingStore } = await import('../../src/stores/branding')
    const branding = useBrandingStore()
    branding.settings.welcome_subtitle = 'Добро пожаловать!'
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.text()).toContain('Добро пожаловать!')
  })

  it('renders without user logged in', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = null
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.exists()).toBe(true)
  })
})
