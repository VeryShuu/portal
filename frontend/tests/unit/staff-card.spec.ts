import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NAvatar: { template: '<div class="n-avatar"><slot /></div>', props: ['src', 'size', 'round'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'bordered'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  CallOutline: { template: '<span />' },
  CopyOutline: { template: '<span />' },
  LocationOutline: { template: '<span />' },
  MailOutline: { template: '<span />' },
  PhonePortraitOutline: { template: '<span />' },
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false } })),
}))

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

describe('StaffCard.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const hlFn = (text: string | null | undefined) => text ?? ''

  it('renders without errors', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows user full name', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Иван Иванов')
  })

  it('shows department tag when department present', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('ИТ')
  })

  it('shows position', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Разработчик')
  })

  it('renders without phone', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const userNoPhone = { ...MOCK_USER, phone: null, attributes: {} }
    const wrapper = mount(StaffCard, {
      props: { user: userNoPhone as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders with extra attributes', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const schema = [{
      attr_key: 'team',
      label_ru: 'Команда',
      label_en: 'Team',
      sort_order: 0,
    }]
    const userWithAttrs = { ...MOCK_USER, attributes: { team: 'Бэкенд' } }
    const wrapper = mount(StaffCard, {
      props: { user: userWithAttrs as any, hl: hlFn, attributeSchema: schema as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Бэкенд')
  })

  it('shows initials when no avatar', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-avatar').text()).toContain('ИИ')
  })
})
