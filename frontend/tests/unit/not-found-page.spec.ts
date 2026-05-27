import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'ru' } }),
  createI18n: () => ({ global: { t: (k: string) => k, locale: { value: 'ru' } } }),
}))

const i18n = {
  install: (app: any) => {
    app.config.globalProperties.$t = (k: string) => k
    app.config.globalProperties.$i18n = { locale: 'ru' }
  },
}

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'loading'],
    emits: ['click'],
  },
  NResult: {
    template: '<div class="n-result"><slot name="footer" /></div>',
    props: ['status', 'title', 'description'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {} })),
}))

describe('NotFoundPage.vue', () => {
  it('renders 404 result component', async () => {
    const NotFoundPage = (await import('../../src/pages/NotFoundPage.vue')).default
    const wrapper = mount(NotFoundPage, { global: { plugins: [i18n] } })
    expect(wrapper.find('.n-result').exists()).toBe(true)
  })

  it('has back button', async () => {
    const NotFoundPage = (await import('../../src/pages/NotFoundPage.vue')).default
    const wrapper = mount(NotFoundPage, { global: { plugins: [i18n] } })
    expect(wrapper.findAll('button').length).toBeGreaterThan(0)
  })
})
