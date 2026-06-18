import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, defineComponent, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const routeState = { params: { id: 'news-1' as string } }
const routerPush = vi.fn()
const manageOpen = vi.fn()
const manageClose = vi.fn()
const manageState = ref<string | null>(null)

const newsListState = {
  loading: false,
  data: { items: [] as any[], total: 0 },
}

const categoriesState = {
  data: [] as Array<{ name: string; color: string }>,
}

const authState = {
  isEditor: true,
}

const newsDetailState = {
  loading: false,
  data: null as any,
}

const newsGalleryState = {
  data: [] as any[],
}

const newsAttachmentsState = {
  data: [] as any[],
}

const deleteMutateAsync = vi.fn()
const confirmFn = vi.fn(async () => true)
const messageSuccess = vi.fn()
const messageError = vi.fn()
const setHeader = vi.fn()
const clearHeader = vi.fn()
const fetchNewsListMock = vi.fn(async () => ({ items: [], total: 0 }))

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'disabled', 'quaternary', 'circle', 'title', 'tertiary'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['component', 'size'] },
  NSelect: {
    template: '<select class="n-select" @change="$emit(\'update:value\', $event.target.value)"><slot /></select>',
    props: ['value', 'options', 'size', 'clearable', 'placeholder'],
    emits: ['update:value'],
  },
  NDrawer: { template: '<div v-if="show" class="n-drawer"><slot /></div>', props: ['show', 'width', 'placement', 'onUpdateShow'] },
  NDrawerContent: { template: '<div class="n-drawer-content"><slot /></div>', props: ['title', 'closable'] },
  NDropdown: { name: 'NDropdown', template: '<div class="n-dropdown"><slot /></div>', props: ['trigger', 'options'], emits: ['select'] },
  NSpin: { template: '<div class="n-spin" />', props: ['show'] },
  NResult: { template: '<div class="n-result"><slot /><slot name="footer" /></div>', props: ['status', 'title', 'description'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /></div>', props: ['show', 'title', 'preset', 'maskClosable'], emits: ['update:show'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules', 'labelPlacement'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path', 'feedback', 'validationStatus'] },
  NInput: { template: '<textarea class="n-input" :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'type', 'autosize', 'maxlength', 'showCount', 'placeholder'], emits: ['update:value'] },
  useMessage: () => ({ success: messageSuccess, error: messageError, warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => routeState),
  useRouter: vi.fn(() => ({ push: routerPush, replace: vi.fn(), back: vi.fn() })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false }, isFetching: { value: false }, error: { value: null }, refetch: vi.fn() })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn(), setQueryData: vi.fn() })),
  useInfiniteQuery: vi.fn(() => ({ data: { value: { pages: [] } }, isLoading: { value: false }, fetchNextPage: vi.fn(), hasNextPage: { value: false } })),
  keepPreviousData: undefined,
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ data: {} }),
  apiUpload: vi.fn().mockResolvedValue({ data: {} }),
  BASE_URL: '/api/v1',
}))

vi.mock('@vicons/ionicons5', () => ({
  EyeOutline: { template: '<span />' },
  StarOutline: { template: '<span />' },
  LinkOutline: { template: '<span />' },
  CreateOutline: { template: '<span />' },
  DownloadOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  TrashBinOutline: { template: '<span />' },
  PricetagsOutline: { template: '<span />' },
  ChatbubbleOutline: { template: '<span />' },
  Heart: { template: '<span />' },
  HeartOutline: { template: '<span />' },
}))
vi.mock('@vicons/fluent', () => ({}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => authState),
}))

vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: vi.fn(() => ({
    open: (k: string) => { manageState.value = k; manageOpen(k) },
    close: () => { manageState.value = null; manageClose() },
    is: (k: string) => manageState.value === k,
  })),
}))

vi.mock('../../src/api/news', () => ({
  fetchNewsList: (...args: unknown[]) => fetchNewsListMock(...args),
}))

vi.mock('../../src/queries/news', () => ({
  useNewsCategoriesQuery: vi.fn(() => ({ data: ref(categoriesState.data) })),
  useNewsListQuery: vi.fn(() => ({ data: ref(newsListState.data), isLoading: ref(newsListState.loading) })),
  useNewsDetailQuery: vi.fn(() => ({ data: ref(newsDetailState.data), isLoading: ref(newsDetailState.loading) })),
  useNewsGalleryQuery: vi.fn(() => ({ data: ref(newsGalleryState.data), isLoading: ref(false) })),
  useNewsAttachmentsQuery: vi.fn(() => ({ data: ref(newsAttachmentsState.data), isLoading: ref(false) })),
  useDeleteNewsMutation: vi.fn(() => ({ mutateAsync: deleteMutateAsync })),
  useShareNewsEmailMutation: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: ref(false) })),
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: vi.fn(() => ({ confirm: (...args: unknown[]) => confirmFn(...args) })),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'parse-error'),
}))

vi.mock('../../src/stores/branding', () => ({
  useBrandingStore: vi.fn(() => ({ settings: { allowed_iframe_origins: [] } })),
}))

vi.mock('../../src/composables/useLayoutHeader', () => ({
  useLayoutHeader: vi.fn(() => ({ setHeader, clearHeader })),
}))

vi.mock('@/utils/markdown', () => ({
  mdUnsafe: { render: (v: string) => `<p>${v}</p>` },
}))

vi.mock('@/utils/sanitize', () => ({
  sanitizeHtmlAllowIframe: vi.fn((v: string) => v),
}))

vi.mock('../../src/components/news/NewsCard.vue', () => ({
  default: defineComponent({
    name: 'NewsCard',
    props: ['news'],
    emits: ['click'],
    template: '<button class="news-card" @click="$emit(\'click\', news.id)">{{ news.title }}</button>',
  }),
}))

vi.mock('../../src/components/news/NewsLikeButton.vue', () => ({
  default: defineComponent({ name: 'NewsLikeButton', template: '<button class="news-like" />', props: ['newsId', 'likeCount', 'liked', 'compact'] }),
}))

vi.mock('../../src/components/news/NewsComments.vue', () => ({
  default: defineComponent({ name: 'NewsComments', template: '<div class="news-comments" />', props: ['newsId'] }),
}))

vi.mock('../../src/components/SkeletonCard.vue', () => ({
  default: defineComponent({ name: 'SkeletonCard', template: '<div class="skeleton-card" />', props: ['variant'] }),
}))

vi.mock('../../src/components/EmptyState.vue', () => ({
  default: defineComponent({ name: 'EmptyState', template: '<div class="empty-state">empty</div>', props: ['variant', 'title', 'description'] }),
}))

vi.mock('../../src/components/trash/TrashNewsTab.vue', () => ({
  default: defineComponent({ name: 'TrashNewsTab', template: '<div class="trash-news-tab" />' }),
  name: 'TrashNewsTab',
  __isTeleport: false,
  __isKeepAlive: false,
  __v_isVNode: false,
}))

vi.mock('../../src/pages/admin/tabs/NewsCategoriesTab.vue', () => ({
  default: defineComponent({ name: 'NewsCategoriesTab', template: '<div class="news-categories-tab" />' }),
  name: 'NewsCategoriesTab',
  __isTeleport: false,
  __isKeepAlive: false,
  __v_isVNode: false,
}))

vi.mock('../../src/components/news/NewsGalleryViewer.vue', () => ({
  default: defineComponent({ name: 'NewsGalleryViewer', template: '<div class="gallery-viewer" />', props: ['images'] }),
}))

vi.mock('../../src/components/news/NewsAttachmentsViewer.vue', () => ({
  default: defineComponent({ name: 'NewsAttachmentsViewer', template: '<div class="attachments-viewer" />', props: ['attachments'] }),
}))

vi.mock('../../src/components/news/poll/NewsPoll.vue', () => ({
  default: defineComponent({ name: 'NewsPoll', template: '<div class="news-poll" />', props: ['newsId', 'newsAuthorId'] }),
}))

describe('cov2 NewsListPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routeState.params.id = 'news-1'
    authState.isEditor = true
    newsListState.loading = false
    newsListState.data = {
      items: [
        { id: 'n1', title: 'Pinned', is_pinned: true, categories: ['HR'] },
        { id: 'n2', title: 'Tech', is_pinned: false, categories: ['IT'] },
      ],
      total: 2,
    }
    categoriesState.data = [{ name: 'HR', color: '#ffffff' }, { name: 'IT', color: '#111111' }]
    manageState.value = null
    routerPush.mockReset()
    manageOpen.mockReset()
    fetchNewsListMock.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('mounts with loaded list and filters by chips', async () => {
    class IO {
      observe = vi.fn()
      disconnect = vi.fn()
      constructor(_cb: IntersectionObserverCallback, _opts?: IntersectionObserverInit) {}
    }
    vi.stubGlobal('IntersectionObserver', IO as unknown as typeof IntersectionObserver)

    const Cmp = (await import('../../src/pages/NewsListPage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.exists()).toBe(true)
    expect(w.findAll('.news-card')).toHaveLength(2)

    const chips = w.findAll('.chip')
    await chips[1].trigger('click')
    await nextTick()
    expect(w.findAll('.news-card')).toHaveLength(1)

    await chips[2].trigger('click')
    await nextTick()
    expect(w.findAll('.news-card')).toHaveLength(1)
  })

  it('shows loading skeletons and trash chip view for editor', async () => {
    newsListState.loading = true
    class IO {
      observe = vi.fn()
      disconnect = vi.fn()
      constructor(_cb: IntersectionObserverCallback, _opts?: IntersectionObserverInit) {}
    }
    vi.stubGlobal('IntersectionObserver', IO as unknown as typeof IntersectionObserver)

    const Cmp = (await import('../../src/pages/NewsListPage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.findAll('.skeleton-card').length).toBeGreaterThan(0)

    const iconBtns = w.findAll('button.n-button')
    expect(iconBtns.length).toBeGreaterThan(1)
  })

  it('hides editor actions for non-editor and opens details on card click', async () => {
    authState.isEditor = false
    class IO {
      observe = vi.fn()
      disconnect = vi.fn()
      constructor(_cb: IntersectionObserverCallback, _opts?: IntersectionObserverInit) {}
    }
    vi.stubGlobal('IntersectionObserver', IO as unknown as typeof IntersectionObserver)

    const Cmp = (await import('../../src/pages/NewsListPage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.find('.n-select').exists()).toBe(false)
    await w.find('.news-card').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/news/n1')
  })

  it('renders empty state when loaded data is empty', async () => {
    newsListState.data = { items: [], total: 0 }
    class IO {
      observe = vi.fn()
      disconnect = vi.fn()
      constructor(_cb: IntersectionObserverCallback, _opts?: IntersectionObserverInit) {}
    }
    vi.stubGlobal('IntersectionObserver', IO as unknown as typeof IntersectionObserver)

    const Cmp = (await import('../../src/pages/NewsListPage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.find('.empty-state').exists()).toBe(true)
  })
})

describe('cov2 NewsDetailPage.vue', () => {
  const originalCreate = document.createElement

  beforeEach(() => {
    setActivePinia(createPinia())
    routeState.params.id = 'news-1'
    newsDetailState.loading = false
    newsDetailState.data = {
      id: 'news-1',
      title: 'Detail title',
      body: 'hello',
      categories: ['IT'],
      is_pinned: true,
      status: 'draft',
      view_count: 11,
      has_poll: true,
      author_id: 'u1',
      cover_image_url: '',
      cover_focal_x: null,
      cover_focal_y: null,
      published_at: '2026-01-01T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
    }
    newsGalleryState.data = [{ id: 'g1' }]
    newsAttachmentsState.data = [{ id: 'a1' }]
    authState.isEditor = true
    deleteMutateAsync.mockReset()
    deleteMutateAsync.mockResolvedValue(undefined)
    confirmFn.mockReset()
    confirmFn.mockResolvedValue(true)
    routerPush.mockReset()
    messageError.mockReset()
    messageSuccess.mockReset()
    setHeader.mockReset()
    clearHeader.mockReset()
  })

  afterEach(() => {
    document.createElement = originalCreate
    vi.unstubAllGlobals()
  })

  it('renders loading and not-found branches', async () => {
    newsDetailState.loading = true
    const Cmp = (await import('../../src/pages/NewsDetailPage.vue')).default
    const w1 = mount(Cmp, { global: { plugins: [i18n] } })
    expect(w1.find('.n-spin').exists()).toBe(true)

    newsDetailState.loading = false
    newsDetailState.data = null
    const w2 = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w2.find('.n-result').exists()).toBe(true)
  })

  it('renders article branch and handles export/copy success', async () => {
    const anchor = originalCreate.call(document, 'a')
    const clickSpy = vi.fn()
    anchor.click = clickSpy
    document.createElement = vi.fn((tag: string) => {
      if (tag === 'a') return anchor
      return originalCreate.call(document, tag)
    }) as unknown as typeof document.createElement

    const appendSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node: Node) => node)
    const removeSpy = vi.spyOn(document.body, 'removeChild').mockImplementation((node: Node) => node)
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })

    const Cmp = (await import('../../src/pages/NewsDetailPage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.find('.article').exists()).toBe(true)
    const dropdown = w.findComponent({ name: 'NDropdown' })
    dropdown.vm.$emit('select', 'pdf')
    expect(clickSpy).toHaveBeenCalled()
    expect(appendSpy).toHaveBeenCalled()
    expect(removeSpy).toHaveBeenCalled()

    const btns = w.findAll('button.n-button')
    await btns[0].trigger('click')
    await flushPromises()
    expect(messageSuccess).toHaveBeenCalled()

    appendSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it('handles copy failure and delete success/failure branches', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('x')) } })

    const Cmp = (await import('../../src/pages/NewsDetailPage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    const btns = w.findAll('button.n-button')
    await btns[0].trigger('click')
    await flushPromises()
    expect(messageError).toHaveBeenCalled()

    confirmFn.mockResolvedValue(false)
    await btns[3].trigger('click')
    await flushPromises()
    expect(deleteMutateAsync).not.toHaveBeenCalled()

    confirmFn.mockResolvedValue(true)
    deleteMutateAsync.mockResolvedValueOnce(undefined)
    await btns[3].trigger('click')
    await flushPromises()
    expect(deleteMutateAsync).toHaveBeenCalledWith('news-1')
    expect(routerPush).toHaveBeenCalledWith('/news')

    deleteMutateAsync.mockRejectedValueOnce(new Error('no'))
    await btns[3].trigger('click')
    await flushPromises()
    expect(messageError).toHaveBeenCalled()
  })
})
