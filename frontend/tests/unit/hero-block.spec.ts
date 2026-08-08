import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    ru: {
      home: {
        greetings: {
          morning: 'Доброе утро',
          afternoon: 'Добрый день',
          evening: 'Добрый вечер',
          night: 'Доброй ночи',
        },
        heroSubs: {
          morning: 'Новый день — новые открытия.',
          afternoon: 'Всё важное из жизни МАГЭ.',
          evening: 'Рабочий день подходит к завершению.',
          night: 'Доброй ночи.',
        },
        greetingAnonymous: 'Коллега',
      },
    },
    en: {},
  },
})

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

// Hero больше не использует router/NButton/useHeroStats/modules — только
// HeroWorldClock как дочерний компонент. Мокаем его целиком, чтобы не тянуть
// composables world-clock в изоляционном тесте Hero.
vi.mock('../../src/components/widgets/HeroWorldClock.vue', () => ({
  default: { name: 'HeroWorldClock', template: '<div class="hero-clock-stub" />' },
}))

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

  it('renders without user logged in', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = null
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.exists()).toBe(true)
  })

  // ── Подзаголовок по режиму hero_subtitle_mode (админка) ────────────────────

  it('renders HeroWorldClock (часы в правом верхнем углу)', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.find('.hero-clock-stub').exists()).toBe(true)
  })

  it('applies hero--<slot> class based on current hour', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const hour = new Date().getHours()
    const expected = hour < 6 || hour >= 18 ? 'evening' : hour < 12 ? 'morning' : 'day'
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.find('section.hero').classes()).toContain(`hero--${expected}`)
  })

  it('shows per-time subtitle in auto mode (default)', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    const hour = new Date().getHours()
    const expected = hour < 6 || hour >= 18 ? 'evening' : hour < 12 ? 'morning' : 'day'
    expect(wrapper.text()).toContain(i18n.global.t(`home.heroSubs.${expected}`))
  })

  it('shows custom welcome_subtitle when mode is "custom"', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useBrandingStore } = await import('../../src/stores/branding')
    const branding = useBrandingStore()
    branding.settings.hero_subtitle_mode = 'custom'
    branding.settings.welcome_subtitle = 'Добро пожаловать!'
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.text()).toContain('Добро пожаловать!')
  })

  it('hides subtitle element entirely when mode is "hidden"', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useBrandingStore } = await import('../../src/stores/branding')
    const branding = useBrandingStore()
    branding.settings.hero_subtitle_mode = 'hidden'
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.find('.hero__sub').exists()).toBe(false)
  })

  it('respects custom hero hour boundaries from branding settings', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useBrandingStore } = await import('../../src/stores/branding')
    const branding = useBrandingStore()
    branding.settings.hero_morning_hour = 0
    branding.settings.hero_day_hour = 9
    branding.settings.hero_evening_hour = 17
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    const hour = new Date().getHours()
    const expected = hour >= 17 ? 'evening' : hour >= 9 ? 'day' : 'morning'
    expect(wrapper.find('section.hero').classes()).toContain(`hero--${expected}`)
  })

  it('renders hero photo when branding has_hero_bg_<slot> is set', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useBrandingStore } = await import('../../src/stores/branding')
    const branding = useBrandingStore()
    branding.settings.has_hero_bg_morning = true
    branding.settings.has_hero_bg_day = true
    branding.settings.has_hero_bg_evening = true
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.find('section.hero').classes()).toContain('hero--has-photo')
    expect(wrapper.find('img.hero__photo').exists()).toBe(true)
  })

  it('renders no photo when no hero_bg flags set', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.find('section.hero').classes()).not.toContain('hero--has-photo')
    expect(wrapper.find('img.hero__photo').exists()).toBe(false)
  })
})
