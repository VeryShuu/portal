import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  CopyOutline: { template: '<span />' },
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

describe('StaffRow.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const hlFn = (text: string | null | undefined) => text ?? ''

  it('renders without errors', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const wrapper = mount(StaffRow, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows user full name', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const wrapper = mount(StaffRow, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Иван Иванов')
  })

  it('shows position', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const wrapper = mount(StaffRow, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Разработчик')
  })

  it('shows city from attributes', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const wrapper = mount(StaffRow, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Москва')
  })

  it('renders without optional fields', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const minimalUser = {
      id: '00000000-0000-0000-0000-000000000002',
      full_name: 'Петр Петров',
      email: 'petr@example.com',
      role: 'reader' as const,
      auth_source: 'keycloak' as const,
      avatar_url: null,
      is_active: true,
      position: null,
      department: null,
      phone: null,
      attributes: {},
    }
    const wrapper = mount(StaffRow, {
      props: { user: minimalUser as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Петр Петров')
  })
})
