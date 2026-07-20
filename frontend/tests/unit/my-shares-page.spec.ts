import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'loading', 'block', 'text', 'ghost', 'quaternary', 'secondary', 'tertiary', 'circle', 'title'],
    emits: ['click'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('@/api/photos', () => ({
  thumbUrl: vi.fn((id: string, size: number) => `/photos/thumb/${id}/${size}`),
}))

vi.mock('../../src/queries/photos', async () => {
  const { ref } = await import('vue')
  return {
    useMySharesQuery: vi.fn(() => ({
      data: ref({ photo_tokens: [{ id: 't1', photo_id: 'p1', url: 'http://portal/pub/photo/tok1' }], folder_tokens: [{ id: 't2', folder_id: 'f1', url: 'http://portal/pub/folder/tok2' }] }),
      isLoading: ref(false),
    })),
    useRevokePhotoShareMutation: vi.fn(() => ({ mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: ref(false) })),
    useRevokeFolderShareMutation: vi.fn(() => ({ mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: ref(false) })),
  }
})

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'error'),
}))

const globalPlugins = {
  plugins: [i18n],
}

describe('MySharesPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      writable: true,
      configurable: true,
    })
  })

  it('renders without errors', async () => {
    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders the shares page element', async () => {
    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })
    expect(wrapper.find('.my-shares-page').exists()).toBe(true)
  })

  it('renders share rows and buttons can be clicked', async () => {
    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })
    const buttons = wrapper.findAll('button')
    for (const btn of buttons) {
      try { await btn.trigger('click') } catch { /* ignore */ }
    }
    expect(wrapper.find('.share-row').exists()).toBe(true)
  })

  it('B1: sanitizes non-http(s) share URLs (no javascript:/data: hrefs)', async () => {
    const { ref } = await import('vue')
    const photosQueries = await import('../../src/queries/photos')
    vi.mocked(photosQueries.useMySharesQuery).mockReturnValueOnce({
      data: ref({
        photo_tokens: [{ id: 't1', photo_id: 'p1', url: 'javascript:alert(1)' }],
        folder_tokens: [{ id: 't2', folder_id: 'f1', url: 'data:text/html,<script>alert(1)</script>' }],
      }),
      isLoading: ref(false),
    } as unknown as ReturnType<typeof photosQueries.useMySharesQuery>)

    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })

    const anchors = wrapper.findAll('a')
    for (const a of anchors) {
      const href = a.attributes('href') ?? ''
      expect(href.startsWith('javascript:')).toBe(false)
      expect(href.startsWith('data:')).toBe(false)
    }
  })
})
