import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NSpin: { template: '<div class="n-spin" />', props: ['show'] },
  NModal: { template: '<div class="n-modal"><slot /><slot name="action" /></div>', props: ['show', 'title', 'preset'] },
  NForm: { template: '<form @submit.prevent="$emit(\'submit\')"><slot /></form>', props: ['model'], emits: ['submit'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type'],
    emits: ['update:value'],
  },
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'quaternary', 'circle', 'title'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('sortablejs', () => ({
  default: {
    create: vi.fn(() => ({ destroy: vi.fn() })),
  },
}))

vi.mock('@vicons/ionicons5', () => ({
  LinkOutline: { template: '<span />' },
  ShieldCheckmarkOutline: { template: '<span />' },
  OpenOutline: { template: '<span />' },
  ArrowForwardOutline: { template: '<span />' },
  CreateOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  ReorderTwoOutline: { template: '<span />' },
  BookOutline: { template: '<span />' },
}))

vi.mock('../../src/api/links', () => ({
  fetchLinks: vi.fn().mockResolvedValue({ items: [] }),
  fetchBookmarks: vi.fn().mockResolvedValue({ items: [] }),
  createBookmark: vi.fn(),
  deleteBookmark: vi.fn(),
  reorderBookmarks: vi.fn(),
  reorderLinks: vi.fn(),
}))

describe('BookmarksTab.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const BookmarksTab = (await import('../../src/components/links/BookmarksTab.vue')).default
    const wrapper = mount(BookmarksTab, { global: { plugins: [i18n] } })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows empty state when no bookmarks', async () => {
    const BookmarksTab = (await import('../../src/components/links/BookmarksTab.vue')).default
    const { useLinksStore } = await import('../../src/stores/links')
    const store = useLinksStore()
    store.bookmarks = []
    const wrapper = mount(BookmarksTab, { global: { plugins: [i18n] } })
    expect(wrapper.find('.empty-state, [class*="empty"]').exists() || wrapper.html().includes('EmptyState') || !wrapper.find('.links-grid').exists()).toBe(true)
  })

  it('does not show loading spinner when not loading', async () => {
    const BookmarksTab = (await import('../../src/components/links/BookmarksTab.vue')).default
    const { useLinksStore } = await import('../../src/stores/links')
    const store = useLinksStore()
    store.loadingBookmarks = false
    const wrapper = mount(BookmarksTab, { global: { plugins: [i18n] } })
    expect(wrapper.find('.n-spin').exists()).toBe(false)
  })
})
