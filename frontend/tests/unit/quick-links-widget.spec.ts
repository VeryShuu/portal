import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

/**
 * Виджет «Быстрые ссылки» (ТЗ п.6) — на основе персональных закладок.
 * Контракты:
 * - рендерит список закладок когда они есть
 * - скрыт целиком (v-if на корне) когда закладок нет
 */
const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    ru: {
      home: {
        sections: { quickLinks: 'Быстрые ссылки', allBookmarks: 'Все закладки' },
      },
    },
  },
})

vi.mock('naive-ui', () => ({
  NButton: { template: '<button class="n-button"><slot /></button>' },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  ArrowForwardOutline: { template: '<span />' },
}))

const mockRouterPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockRouterPush }),
}))

// Мокаем links store: управляем bookmark'ами и флагом загрузки.
let mockBookmarks: any[] = []
vi.mock('../../src/stores/links', () => ({
  useLinksStore: () => ({
    get bookmarks() { return mockBookmarks },
    loadingBookmarks: false,
    loadBookmarks: vi.fn().mockResolvedValue(undefined),
  }),
}))

describe('QuickLinksWidget', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockBookmarks = []
  })

  it('рендерит список закладок когда они есть', async () => {
    mockBookmarks = [
      { id: 'b1', title: 'Корпоративный портал', url: '/' },
      { id: 'b2', title: 'Календарь событий', url: '/meetings' },
    ]

    const QuickLinksWidget = (await import('../../src/components/widgets/QuickLinksWidget.vue')).default
    const wrapper = mount(QuickLinksWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    const titles = wrapper.findAll('.quick-link__title').map((el) => el.text())
    expect(titles).toEqual(['Корпоративный портал', 'Календарь событий'])
  })

  it('скрыт (нет .widget), когда закладок нет', async () => {
    mockBookmarks = []

    const QuickLinksWidget = (await import('../../src/components/widgets/QuickLinksWidget.vue')).default
    const wrapper = mount(QuickLinksWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find('.widget').exists()).toBe(false)
    expect(wrapper.findAll('.quick-link')).toHaveLength(0)
  })

  it('внутренняя ссылка маршрутизируется через router.push', async () => {
    mockBookmarks = [{ id: 'b1', title: 'Новости', url: '/news' }]

    const QuickLinksWidget = (await import('../../src/components/widgets/QuickLinksWidget.vue')).default
    const wrapper = mount(QuickLinksWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    await wrapper.find('.quick-link').trigger('click')
    await flushPromises()
    expect(mockRouterPush).toHaveBeenCalledWith('/news')
  })

  it('внешняя ссылка НЕ маршрутизируется router (открывается как href)', async () => {
    mockBookmarks = [{ id: 'b1', title: 'Внешний сайт', url: 'https://example.com' }]

    const QuickLinksWidget = (await import('../../src/components/widgets/QuickLinksWidget.vue')).default
    const wrapper = mount(QuickLinksWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    const link = wrapper.find('.quick-link')
    expect(link.attributes('href')).toBe('https://example.com')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener noreferrer')

    await link.trigger('click')
    await flushPromises()
    expect(mockRouterPush).not.toHaveBeenCalled()
  })
})
