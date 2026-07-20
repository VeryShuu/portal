import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'disabled', 'loading', 'block', 'text', 'ghost', 'quaternary', 'secondary', 'tertiary', 'circle'],
    emits: ['click'],
  },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'] },
  NDrawerContent: { template: '<div class="n-drawer-content"><slot /></div>', props: ['title', 'closable'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  NTabs: {
    template: '<div class="n-tabs"><slot /></div>',
    props: ['value', 'type', 'animated', 'displayDirective', 'size'],
    emits: ['update:value'],
  },
  NTab: { template: '<div class="n-tab"><slot /></div>', props: ['name'] },
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/links', name: 'links' })),
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, {
  get: () => ({ template: '<span />' }),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({ isEditor: false, isAdmin: false })),
}))

vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: vi.fn(() => ({
    is: vi.fn(() => false),
    open: vi.fn(),
    close: vi.fn(),
  })),
}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    ServiceLinksTab: { template: '<div />' },
    BookmarksTab: { template: '<div />' },
  },
}

describe('LinksAndBookmarksPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders without errors', async () => {
    const LinksAndBookmarksPage = (await import('../../src/pages/LinksAndBookmarksPage.vue')).default
    const wrapper = mount(LinksAndBookmarksPage, { global: globalPlugins })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows tabs', async () => {
    const LinksAndBookmarksPage = (await import('../../src/pages/LinksAndBookmarksPage.vue')).default
    const wrapper = mount(LinksAndBookmarksPage, { global: globalPlugins })
    expect(wrapper.find('.n-tabs').exists()).toBe(true)
  })
})
