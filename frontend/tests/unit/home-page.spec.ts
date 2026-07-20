import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'text', 'loading', 'disabled'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
}))

const mockRouterPush = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({
    push: (...args: unknown[]) => mockRouterPush(...args),
  })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  ChevronForwardOutline: { template: '<span />' },
}))

const mockAuthStore = {
  isEditor: false,
}

const mockLinksStore = {
  loadingLinks: false,
  links: [] as Array<{ id: string; title: string; icon_url: string | null }>,
  openLink: vi.fn(),
  loadLinks: vi.fn(),
}

const mockBrandingStore = {
  isBannerActive: false,
  settings: {
    banner_type: 'info',
    banner_text: '',
    banner_expires_at: null as string | null,
  },
}

const mockHomeNewsState = {
  loadingNews: ref(false),
  pinned: ref<Array<{ id: string; title: string }>>([]),
  regular: ref<Array<{ id: string; title: string }>>([]),
  categoriesMap: ref<Record<string, string>>({}),
  goToNews: vi.fn(),
}

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => mockAuthStore),
}))

vi.mock('../../src/stores/links', () => ({
  useLinksStore: vi.fn(() => mockLinksStore),
}))

vi.mock('../../src/stores/branding', () => ({
  useBrandingStore: vi.fn(() => mockBrandingStore),
}))

vi.mock('../../src/composables/useHomeNews', () => ({
  useHomeNews: vi.fn(() => mockHomeNewsState),
}))

const HeroBlockStub = defineComponent({
  name: 'HeroBlock',
  template: '<div class="hero-block-stub" />',
})

const NewsCardStub = defineComponent({
  name: 'NewsCard',
  props: {
    news: { type: Object, required: true },
    featured: { type: Boolean, default: false },
    categoriesMap: { type: Object, default: () => ({}) },
  },
  emits: ['click'],
  template: '<button class="news-card-stub" @click="$emit(\'click\', news.id)">{{ news.title }}</button>',
})

const EmptyStateStub = defineComponent({
  name: 'EmptyState',
  props: {
    variant: { type: String, default: 'default' },
    title: { type: String, default: '' },
    compact: { type: Boolean, default: false },
  },
  template: '<div class="empty-state-stub" :data-variant="variant" :data-title="title" :data-compact="compact" />',
})

const SkeletonCardStub = defineComponent({
  name: 'SkeletonCard',
  props: {
    variant: { type: String, default: 'news' },
  },
  template: '<div class="skeleton-card-stub" :data-variant="variant" />',
})

const WorldClockWidgetStub = defineComponent({
  name: 'WorldClockWidget',
  template: '<div class="world-clock-widget-stub" />',
})

const MeetingsWidgetStub = defineComponent({
  name: 'MeetingsWidget',
  template: '<div class="meetings-widget-stub" />',
})

const PhotosWidgetStub = defineComponent({
  name: 'PhotosWidget',
  template: '<div class="photos-widget-stub" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    HeroBlock: HeroBlockStub,
    NewsCard: NewsCardStub,
    EmptyState: EmptyStateStub,
    SkeletonCard: SkeletonCardStub,
    WorldClockWidget: WorldClockWidgetStub,
    MeetingsWidget: MeetingsWidgetStub,
    PhotosWidget: PhotosWidgetStub,
  },
}

async function mountPage() {
  const HomePage = (await import('../../src/pages/HomePage.vue')).default
  const wrapper = mount(HomePage, { global: globalOptions })
  await flushPromises()
  return wrapper
}

describe('HomePage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockRouterPush.mockClear()
    mockAuthStore.isEditor = false
    mockLinksStore.loadingLinks = false
    mockLinksStore.links = []
    mockLinksStore.openLink.mockClear()
    mockLinksStore.loadLinks.mockClear()

    mockBrandingStore.isBannerActive = false
    mockBrandingStore.settings.banner_type = 'info'
    mockBrandingStore.settings.banner_text = ''
    mockBrandingStore.settings.banner_expires_at = null

    mockHomeNewsState.loadingNews.value = false
    mockHomeNewsState.pinned.value = []
    mockHomeNewsState.regular.value = []
    mockHomeNewsState.categoriesMap.value = {}
    mockHomeNewsState.goToNews.mockClear()

    sessionStorage.clear()
  })

  it('renders portal banner and dismisses it to sessionStorage', async () => {
    mockBrandingStore.isBannerActive = true
    mockBrandingStore.settings.banner_type = 'warning'
    mockBrandingStore.settings.banner_text = 'Banner text'
    mockBrandingStore.settings.banner_expires_at = '2099-01-01T00:00:00.000Z'

    const wrapper = await mountPage()

    const banner = wrapper.find('.portal-banner')
    expect(banner.exists()).toBe(true)
    expect(banner.classes()).toContain('portal-banner--warning')
    expect(banner.text()).toContain('Banner text')

    await wrapper.find('.portal-banner__close').trigger('click')
    await nextTick()

    expect(sessionStorage.getItem('home_banner_dismissed')).toBe('Banner text|2099-01-01T00:00:00.000Z')
    expect(wrapper.find('.portal-banner').exists()).toBe(false)
  })

  it('does not render banner when same banner key is already dismissed in sessionStorage', async () => {
    mockBrandingStore.isBannerActive = true
    mockBrandingStore.settings.banner_text = 'Already dismissed'
    mockBrandingStore.settings.banner_expires_at = null
    sessionStorage.setItem('home_banner_dismissed', 'Already dismissed|')

    const wrapper = await mountPage()

    expect(wrapper.find('.portal-banner').exists()).toBe(false)
  })

  it('shows featured and main skeleton branches while news is loading', async () => {
    mockHomeNewsState.loadingNews.value = true

    const wrapper = await mountPage()

    expect(wrapper.find('.section--featured').exists()).toBe(true)
    expect(wrapper.find('.featured-skeleton').exists()).toBe(true)
    expect(wrapper.findAll('.news-grid .skeleton-card-stub')).toHaveLength(4)
  })

  it('hides featured section when not loading and there are no pinned items', async () => {
    mockHomeNewsState.loadingNews.value = false
    mockHomeNewsState.pinned.value = []

    const wrapper = await mountPage()

    expect(wrapper.find('.section--featured').exists()).toBe(false)
  })

  it('renders featured and regular news cards and wires click to goToNews with payload', async () => {
    mockHomeNewsState.loadingNews.value = false
    mockHomeNewsState.pinned.value = [{ id: 'pin-1', title: 'Pinned news' }]
    mockHomeNewsState.regular.value = [{ id: 'reg-1', title: 'Regular 1' }, { id: 'reg-2', title: 'Regular 2' }]
    mockHomeNewsState.categoriesMap.value = { HR: '#ff0000' }

    const wrapper = await mountPage()

    const cards = wrapper.findAllComponents(NewsCardStub)
    expect(cards).toHaveLength(3)
    expect(cards[0].props('featured')).toBe(true)
    expect(cards[1].props('categoriesMap')).toEqual({ HR: '#ff0000' })

    await cards[1].trigger('click')
    expect(mockHomeNewsState.goToNews).toHaveBeenCalledWith('reg-1')
  })

  it('shows news empty state branch when not loading and regular list is empty', async () => {
    mockHomeNewsState.loadingNews.value = false
    mockHomeNewsState.regular.value = []

    const wrapper = await mountPage()

    const empty = wrapper.find('.home__main .empty-state-stub')
    expect(empty.exists()).toBe(true)
    expect(empty.attributes('data-variant')).toBe('news')
    expect(empty.attributes('data-title')).toBe('news.noNews')
  })

  it('shows create news button only for editors and navigates via header action buttons', async () => {
    mockAuthStore.isEditor = true

    const wrapper = await mountPage()

    const actionButtons = wrapper.findAll('.news-header .n-button')
    expect(actionButtons).toHaveLength(2)

    await actionButtons[0].trigger('click')
    await actionButtons[1].trigger('click')

    expect(mockRouterPush).toHaveBeenCalledWith('/news/create')
    expect(mockRouterPush).toHaveBeenCalledWith('/news')
  })

  it('renders services loading skeletons, then top 6 links and delegates openLink on tile click', async () => {
    mockLinksStore.loadingLinks = true
    const loadingWrapper = await mountPage()
    expect(loadingWrapper.findAll('.quick-skeleton')).toHaveLength(6)

    mockLinksStore.loadingLinks = false
    mockLinksStore.links = [
      { id: 'l1', title: 'calendar', icon_url: null },
      { id: 'l2', title: 'wiki', icon_url: '/icons/wiki.svg' },
      { id: 'l3', title: 'jira', icon_url: null },
      { id: 'l4', title: 'git', icon_url: null },
      { id: 'l5', title: 'mail', icon_url: null },
      { id: 'l6', title: 'vpn', icon_url: null },
      { id: 'l7', title: 'extra', icon_url: null },
    ]

    const wrapper = await mountPage()

    const tiles = wrapper.findAll('.quick-grid .quick-tile')
    expect(tiles).toHaveLength(6)
    expect(wrapper.find('.quick-tile__icon img').exists()).toBe(true)
    expect(wrapper.find('.quick-tile__letter').text()).toBe('C')

    await tiles[0].trigger('click')
    expect(mockLinksStore.openLink).toHaveBeenCalledWith(mockLinksStore.links[0])
  })

  it('shows services empty state when links are not loading and list is empty', async () => {
    mockLinksStore.loadingLinks = false
    mockLinksStore.links = []

    const wrapper = await mountPage()

    const emptyStates = wrapper.findAll('.empty-state-stub')
    const servicesEmpty = emptyStates.find((node) => node.attributes('data-title') === 'links.empty')
    expect(servicesEmpty).toBeDefined()
    expect(servicesEmpty!.attributes('data-variant')).toBe('default')
    expect(servicesEmpty!.attributes('data-compact')).toBe('true')
  })

  it('navigates to links page from services header action', async () => {
    const wrapper = await mountPage()

    const servicesHeaderButton = wrapper.findAll('.widget .n-button').find((btn) => btn.text() === 'common.all')
    expect(servicesHeaderButton).toBeDefined()

    await servicesHeaderButton!.trigger('click')

    expect(mockRouterPush).toHaveBeenCalledWith('/links')
  })
})
