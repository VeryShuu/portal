import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'disabled', 'loading', 'tertiary'],
    emits: ['click'],
  },
  NDropdown: { template: '<div class="n-dropdown"><slot /></div>', props: ['options', 'trigger'] },
  NResult: { template: '<div class="n-result"><slot name="footer" /></div>', props: ['status', 'title', 'description'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => ({ params: { id: '1' }, query: {}, path: '/news/1', name: 'news-detail' })),
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, {
  get: () => ({ template: '<span />' }),
}))

vi.mock('@/utils/markdown', () => ({
  mdUnsafe: { render: vi.fn(() => '') },
}))

vi.mock('@/utils/sanitize', () => ({
  sanitizeHtmlAllowIframe: vi.fn((s: string) => s),
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: vi.fn(() => ({ confirm: vi.fn().mockResolvedValue(false) })),
}))

vi.mock('../../src/composables/useLayoutHeader', () => ({
  useLayoutHeader: vi.fn(() => ({ setHeader: vi.fn(), clearHeader: vi.fn() })),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({ isEditor: false })),
}))

vi.mock('../../src/stores/branding', () => ({
  useBrandingStore: vi.fn(() => ({
    settings: { allowed_iframe_origins: [] },
  })),
}))

vi.mock('../../src/queries/news', () => ({
  useNewsDetailQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false } })),
  useNewsGalleryQuery: vi.fn(() => ({ data: { value: undefined } })),
  useNewsAttachmentsQuery: vi.fn(() => ({ data: { value: undefined } })),
  useDeleteNewsMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'error'),
}))

vi.mock('../../src/utils/coverFocal', () => ({
  focalImageStyle: vi.fn(() => ({})),
}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    NewsGalleryViewer: { template: '<div />' },
    NewsAttachmentsViewer: { template: '<div />' },
    NewsPoll: { template: '<div />' },
    NewsLikeButton: { template: '<div />' },
    NewsComments: { template: '<div />' },
    NewsShareEmailModal: { template: '<div />' },
  },
}

describe('NewsDetailPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders without errors (no news = spinner)', async () => {
    const NewsDetailPage = (await import('../../src/pages/NewsDetailPage.vue')).default
    const wrapper = mount(NewsDetailPage, { global: globalPlugins })
    expect(wrapper.exists()).toBe(true)
  })
})
