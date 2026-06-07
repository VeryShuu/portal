import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

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
  NTabs: {
    template: '<div class="n-tabs"><slot /></div>',
    props: ['value', 'type', 'animated', 'displayDirective'],
    emits: ['update:value'],
  },
  NTabPane: {
    template: '<div class="n-tab-pane"><slot /></div>',
    props: ['name', 'tab'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {} })),
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({}),
  apiUpload: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false } })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn() })),
}))


describe('TrashPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  const mountOpts = {
    global: {
      plugins: [i18n],
      stubs: {
        TrashNewsTab: { template: '<div class="trash-news-tab" />' },
        PhotoTrashView: { template: '<div class="photo-trash-view" />' },
      },
    },
  }

  it('renders without errors', async () => {
    const TrashPage = (await import('../../src/pages/TrashPage.vue')).default
    const wrapper = mount(TrashPage, mountOpts)
    expect(wrapper.exists()).toBe(true)
    await flushPromises()
  })

  it('renders tabs', async () => {
    const TrashPage = (await import('../../src/pages/TrashPage.vue')).default
    const wrapper = mount(TrashPage, mountOpts)
    expect(wrapper.find('.n-tabs').exists()).toBe(true)
    await flushPromises()
  })
})
