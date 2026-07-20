import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'disabled', 'loading', 'block', 'text', 'ghost', 'quaternary', 'secondary', 'tertiary', 'circle', 'title'],
    emits: ['click'],
  },
  NSelect: { template: '<select class="n-select" />', props: ['value', 'options', 'placeholder', 'clearable', 'size'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'] },
  NDrawerContent: { template: '<div class="n-drawer-content"><slot /></div>', props: ['title', 'closable'] },
}))

const mockRouterPush = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({
    push: (...args: unknown[]) => mockRouterPush(...args),
  })),
}))

vi.mock('@vicons/ionicons5', () => ({
  TrashBinOutline: { template: '<span />' },
  PricetagsOutline: { template: '<span />' },
  MailOutline: { template: '<span />' },
}))

const mockAuthStore = {
  isEditor: false,
}

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => mockAuthStore),
}))

const mockFetchNewsList = vi.fn().mockResolvedValue({ items: [], total: 0 })

vi.mock('../../src/api/news', () => ({
  fetchNewsList: (...args: unknown[]) => mockFetchNewsList(...args),
}))

const mockNewsListState = {
  data: ref<{ items: Array<{ id: string; title: string; is_pinned?: boolean; categories?: string[] }>; total: number } | undefined>({ items: [], total: 0 }),
  isLoading: ref(false),
}

const mockCategoriesState = {
  data: ref<Array<{ name: string; color: string }>>([]),
}

vi.mock('../../src/queries/news', () => ({
  useNewsListQuery: vi.fn(() => mockNewsListState),
  useNewsCategoriesQuery: vi.fn(() => mockCategoriesState),
}))

const manageState = {
  open: vi.fn(),
  close: vi.fn(),
  is: vi.fn(() => false),
}

vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: vi.fn(() => manageState),
}))

vi.mock('../../src/components/trash/TrashNewsTab.vue', () => ({
  __esModule: true,
  __isTeleport: false,
  __isKeepAlive: false,
  default: defineComponent({ name: 'TrashNewsTab', template: '<div class="trash-tab-stub" />' }),
}))
vi.mock('../../src/pages/admin/tabs/NewsCategoriesTab.vue', () => ({
  __esModule: true,
  __isTeleport: false,
  __isKeepAlive: false,
  default: defineComponent({ name: 'NewsCategoriesTab', template: '<div class="news-categories-tab-stub" />' }),
}))
vi.mock('../../src/components/admin/MailingRecipientsSettings.vue', () => ({
  __esModule: true,
  __isTeleport: false,
  __isKeepAlive: false,
  default: defineComponent({ name: 'MailingRecipientsSettings', template: '<div class="mailing-recipients-stub" />' }),
}))

const NewsCardStub = defineComponent({
  name: 'NewsCard',
  props: {
    news: { type: Object, required: true },
    categoriesMap: { type: Object, default: () => ({}) },
  },
  emits: ['click'],
  template: '<button class="news-card-stub" @click="$emit(\'click\', news.id)">{{ news.title }}</button>',
})

const SkeletonCardStub = defineComponent({
  name: 'SkeletonCard',
  props: { variant: { type: String, default: 'news' } },
  template: '<div class="skeleton-card-stub" :data-variant="variant" />',
})

const EmptyStateStub = defineComponent({
  name: 'EmptyState',
  props: {
    variant: { type: String, default: 'default' },
    title: { type: String, default: '' },
    description: { type: String, default: '' },
  },
  template: '<div class="empty-state-stub" :data-variant="variant" :data-title="title" :data-description="description" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    NewsCard: NewsCardStub,
    SkeletonCard: SkeletonCardStub,
    EmptyState: EmptyStateStub,
  },
}

let observerCallback: ((entries: Array<{ isIntersecting: boolean }>) => void) | null = null
let observerObserveTarget: HTMLElement | null = null

class MockIntersectionObserver {
  constructor(cb: (entries: Array<{ isIntersecting: boolean }>) => void) {
    observerCallback = cb
  }
  observe(target: HTMLElement) { observerObserveTarget = target }
  unobserve() {}
  disconnect() {}
  takeRecords() { return [] }
}

async function mountPage() {
  const NewsListPage = (await import('../../src/pages/NewsListPage.vue')).default
  const wrapper = mount(NewsListPage, { global: globalOptions })
  await flushPromises()
  return wrapper
}

describe('NewsListPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockRouterPush.mockClear()

    mockAuthStore.isEditor = false

    mockFetchNewsList.mockClear()
    mockFetchNewsList.mockResolvedValue({ items: [], total: 0 })

    mockNewsListState.data.value = { items: [], total: 0 }
    mockNewsListState.isLoading.value = false
    mockCategoriesState.data.value = []

    manageState.open.mockClear()
    manageState.close.mockClear()
    manageState.is.mockClear()
    manageState.is.mockReturnValue(false)

    observerCallback = null
    observerObserveTarget = null
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
  })

  it('renders 6 skeleton cards while news list is loading', async () => {
    mockNewsListState.isLoading.value = true

    const wrapper = await mountPage()

    expect(wrapper.findAll('.news-grid .skeleton-card-stub')).toHaveLength(6)
    expect(wrapper.find('.empty-state-stub').exists()).toBe(false)
    expect(wrapper.findAllComponents(NewsCardStub)).toHaveLength(0)
  })

  it('renders empty state when not loading and filtered list is empty', async () => {
    mockNewsListState.isLoading.value = false
    mockNewsListState.data.value = { items: [], total: 0 }

    const wrapper = await mountPage()

    const empty = wrapper.find('.news-list-wrap .empty-state-stub')
    expect(empty.exists()).toBe(true)
    expect(empty.attributes('data-variant')).toBe('news')
  })

  it('renders news cards for all items by default and passes categoriesMap prop', async () => {
    mockNewsListState.data.value = {
      items: [
        { id: 'n1', title: 'First', is_pinned: false, categories: ['HR'] },
        { id: 'n2', title: 'Second', is_pinned: true, categories: [] },
      ],
      total: 2,
    }
    mockCategoriesState.data.value = [{ name: 'HR', color: '#ff0000' }]

    const wrapper = await mountPage()

    const cards = wrapper.findAllComponents(NewsCardStub)
    expect(cards).toHaveLength(2)
    expect(cards[0].props('news').id).toBe('n1')
    expect(cards[0].props('categoriesMap')).toEqual({ HR: '#ff0000' })
  })

  it('navigates to article detail when a news card emits click', async () => {
    mockNewsListState.data.value = {
      items: [{ id: 'abc-123', title: 'Clickable', is_pinned: false, categories: [] }],
      total: 1,
    }

    const wrapper = await mountPage()

    await wrapper.findComponent(NewsCardStub).trigger('click')
    expect(mockRouterPush).toHaveBeenCalledWith('/news/abc-123')
  })

  it('filters list by pinned when pinned chip clicked', async () => {
    mockNewsListState.data.value = {
      items: [
        { id: 'p1', title: 'Pinned', is_pinned: true, categories: [] },
        { id: 'r1', title: 'Regular', is_pinned: false, categories: [] },
      ],
      total: 2,
    }

    const wrapper = await mountPage()
    expect(wrapper.findAllComponents(NewsCardStub)).toHaveLength(2)

    // First 2 chips are static ("all", "pinned"); click "pinned"
    const chips = wrapper.findAll('.filters .chip')
    expect(chips.length).toBeGreaterThanOrEqual(2)
    await chips[1].trigger('click')
    await flushPromises()

    const cards = wrapper.findAllComponents(NewsCardStub)
    expect(cards).toHaveLength(1)
    expect(cards[0].props('news').id).toBe('p1')
  })

  it('renders dynamic category chips from query and filters by selected category', async () => {
    mockCategoriesState.data.value = [{ name: 'HR', color: '#10b981' }]
    mockNewsListState.data.value = {
      items: [
        { id: 'a', title: 'In HR', is_pinned: false, categories: ['HR'] },
        { id: 'b', title: 'Other', is_pinned: false, categories: ['IT'] },
      ],
      total: 2,
    }

    const wrapper = await mountPage()

    // "all" + "pinned" + 1 dynamic category chip = 3 chips
    const chips = wrapper.findAll('.filters .chip')
    expect(chips).toHaveLength(3)
    const catChip = chips[2]
    expect(catChip.text()).toBe('HR')
    // Category chip gets inline style with the category color when active
    expect(catChip.attributes('style')).toBeUndefined()

    await catChip.trigger('click')
    await flushPromises()

    const activeChip = wrapper.findAll('.filters .chip')[2]
    expect(activeChip.classes()).toContain('chip--active')

    const cards = wrapper.findAllComponents(NewsCardStub)
    expect(cards).toHaveLength(1)
    expect(cards[0].props('news').id).toBe('a')
  })

  it('hides editor action buttons when user is not editor', async () => {
    mockAuthStore.isEditor = false

    const wrapper = await mountPage()

    const actions = wrapper.find('.u-page-head__actions')
    expect(actions.findAll('.n-button')).toHaveLength(0)
    expect(wrapper.find('.n-select').exists()).toBe(false)
  })

  it('shows editor action buttons (create, categories, mailing, trash) only when isEditor is true', async () => {
    mockAuthStore.isEditor = true

    const wrapper = await mountPage()

    const buttons = wrapper.findAll('.u-page-head__actions .n-button')
    expect(buttons).toHaveLength(4)
    expect(wrapper.find('.n-select').exists()).toBe(true)

    // Create button (last) → navigate to /news/create
    await buttons[3].trigger('click')
    expect(mockRouterPush).toHaveBeenCalledWith('/news/create')

    // Categories button → manage.open('categories')
    await buttons[1].trigger('click')
    expect(manageState.open).toHaveBeenCalledWith('categories')

    // Mailing recipients button → manage.open('mailingRecipients')
    await buttons[2].trigger('click')
    expect(manageState.open).toHaveBeenCalledWith('mailingRecipients')
  })

  it('toggles trash view via trash button and renders TrashNewsTab for editors', async () => {
    mockAuthStore.isEditor = true

    const wrapper = await mountPage()
    expect(wrapper.find('.trash-tab-stub').exists()).toBe(false)

    const trashBtn = wrapper.findAll('.u-page-head__actions .n-button')[0]
    await trashBtn.trigger('click')
    await flushPromises()

    expect(wrapper.find('.trash-tab-stub').exists()).toBe(true)

    // Click again → exit trash view
    await trashBtn.trigger('click')
    await flushPromises()
    expect(wrapper.find('.trash-tab-stub').exists()).toBe(false)
  })

  it('loads more pages when sentinel becomes visible and more items exist', async () => {
    mockNewsListState.data.value = {
      items: [{ id: 'n1', title: 'First', is_pinned: false, categories: [] }],
      total: 50,
    }
    mockFetchNewsList.mockResolvedValue({
      items: [{ id: 'n2', title: 'Second', is_pinned: false, categories: [] }],
      total: 50,
    })

    const wrapper = await mountPage()

    // Sentinel observer was set up after data arrived
    expect(observerCallback).not.toBeNull()
    expect(observerObserveTarget).not.toBeNull()

    observerCallback!([{ isIntersecting: true }])
    await flushPromises()

    expect(mockFetchNewsList).toHaveBeenCalledWith(expect.objectContaining({ page: 2, page_size: 24 }))
    expect(wrapper.findAllComponents(NewsCardStub)).toHaveLength(2)
  })

  it('does not load more when no more pages available', async () => {
    mockNewsListState.data.value = {
      items: [{ id: 'n1', title: 'Only', is_pinned: false, categories: [] }],
      total: 1,
    }

    await mountPage()

    expect(observerCallback).not.toBeNull()
    observerCallback!([{ isIntersecting: true }])
    await flushPromises()

    expect(mockFetchNewsList).not.toHaveBeenCalled()
  })

  it('renders admin drawer for categories when manage.is("categories") is true for editors', async () => {
    mockAuthStore.isEditor = true
    manageState.is.mockImplementation((key: string) => key === 'categories')

    const wrapper = await mountPage()

    expect(wrapper.find('.news-categories-tab-stub').exists()).toBe(true)
    expect(wrapper.find('.mailing-recipients-stub').exists()).toBe(false)
  })

  it('renders admin drawer for mailing recipients when manage.is("mailingRecipients") is true for editors', async () => {
    mockAuthStore.isEditor = true
    manageState.is.mockImplementation((key: string) => key === 'mailingRecipients')

    const wrapper = await mountPage()

    expect(wrapper.find('.mailing-recipients-stub').exists()).toBe(true)
    expect(wrapper.find('.news-categories-tab-stub').exists()).toBe(false)
  })

  it('hides both admin drawers for non-editors even when manage.is returns true', async () => {
    mockAuthStore.isEditor = false
    manageState.is.mockImplementation(() => true)

    const wrapper = await mountPage()

    expect(wrapper.find('.news-categories-tab-stub').exists()).toBe(false)
    expect(wrapper.find('.mailing-recipients-stub').exists()).toBe(false)
  })
})
