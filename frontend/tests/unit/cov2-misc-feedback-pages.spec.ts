import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref, defineComponent, nextTick } from 'vue'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const routeState = ref<any>({ query: {}, params: {}, path: '/feedback/my', name: 'my-feedback' })
const routerReplace = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => routeState.value,
  useRouter: () => ({ replace: routerReplace, push: vi.fn(), back: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

const messageApi = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }

const NDataTableStub = defineComponent({
  name: 'NDataTable',
  props: ['columns', 'data', 'loading', 'pagination', 'remote', 'rowKey', 'rowProps'],
  emits: ['update:page'],
  methods: {
    clickRow(row: any) {
      const p = (this as any).rowProps ? (this as any).rowProps(row) : null
      if (p?.onClick) p.onClick()
    },
  },
  template: '<div class="n-data-table"><div class="row" v-for="row in (data || [])" :key="row.id"><button class="row-open" @click="clickRow(row)">open</button></div><button class="emit-page" @click="$emit(\'update:page\', 2)">page</button></div>',
})

vi.mock('naive-ui', () => ({
  NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'disabled', 'loading'], emits: ['click'] },
  NCard: { template: '<div class="n-card" @click="$emit(\'click\')"><slot /></div>', props: ['hoverable'], emits: ['click'] },
  NPagination: { template: '<div class="n-pagination"><button class="go-page" @click="$emit(\'update:page\', 2)">p2</button></div>', props: ['page', 'pageSize', 'itemCount'], emits: ['update:page'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value', 'size'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value'] },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size'] },
  NInput: { template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'type', 'rows', 'placeholder', 'maxlength', 'clearable', 'size'], emits: ['update:value'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'preset', 'title'], emits: ['update:show'] },
  NSelect: { template: '<select @change="$emit(\'update:value\', $event.target.value)"><option value=""></option></select>', props: ['value', 'options', 'size', 'placeholder', 'clearable'], emits: ['update:value'] },
  NDataTable: NDataTableStub,
  useMessage: () => messageApi,
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

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

const getMyFeedback = vi.fn()
const getMyFeedbackById = vi.fn()
const getAllFeedback = vi.fn()
const getFeedbackById = vi.fn()
const replyToFeedback = vi.fn()
const updateFeedbackStatus = vi.fn()

vi.mock('../../src/api/feedback', () => ({
  getMyFeedback: (...args: unknown[]) => getMyFeedback(...args),
  getMyFeedbackById: (...args: unknown[]) => getMyFeedbackById(...args),
  getAllFeedback: (...args: unknown[]) => getAllFeedback(...args),
  getFeedbackById: (...args: unknown[]) => getFeedbackById(...args),
  replyToFeedback: (...args: unknown[]) => replyToFeedback(...args),
  updateFeedbackStatus: (...args: unknown[]) => updateFeedbackStatus(...args),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'parsed-error'),
}))

vi.mock('../../src/utils/formatDate', () => ({
  formatDate: vi.fn((v: string) => v),
}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
    EmptyState: { template: '<div class="empty-state"><slot /><slot name="action" /></div>', props: ['title', 'description', 'variant'] },
    FeedbackAttachmentList: { template: '<div class="attachments" />', props: ['attachments'] },
  },
}

const itemBase = {
  id: 'f1',
  category: 'bug',
  status: 'open',
  message: 'Long message here',
  created_at: '2024-01-01T10:00:00Z',
  page_url: '',
  attachments: [],
  replies: [],
  author_name: 'User A',
  author_email: 'u@example.com',
}

describe('MyFeedbackPage.vue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { value: vi.fn(), configurable: true })
    messageApi.error.mockClear()
    routeState.value = { query: {}, params: {}, path: '/feedback/my', name: 'my-feedback' }
    getMyFeedback.mockReset()
    getMyFeedbackById.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders empty state when API returns no items', async () => {
    getMyFeedback.mockResolvedValue({ items: [], total: 0 })
    const MyFeedbackPage = (await import('../../src/pages/MyFeedbackPage.vue')).default
    const wrapper = mount(MyFeedbackPage, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.find('.empty-state').exists()).toBe(true)
  })

  it('renders cards, toggles details and handles pagination branch', async () => {
    getMyFeedback.mockResolvedValue({ items: [{ ...itemBase, id: 'f1', replies: [{ id: 'r1', admin_name: 'Admin', created_at: '2024', message: 'ok' }] }], total: 45 })
    const MyFeedbackPage = (await import('../../src/pages/MyFeedbackPage.vue')).default
    const wrapper = mount(MyFeedbackPage, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.findAll('.fb-card').length).toBe(1)
    await wrapper.find('.fb-card').trigger('click')
    expect(wrapper.find('.fb-card__details').exists()).toBe(true)

    await wrapper.find('.go-page').trigger('click')
    await flushPromises()
    expect(getMyFeedback).toHaveBeenCalledTimes(2)
  })

  it('handles open query by loading missing item via getMyFeedbackById', async () => {
    routeState.value = { query: { open: 'f2' }, params: {}, path: '/feedback/my', name: 'my-feedback' }
    getMyFeedback.mockResolvedValue({ items: [{ ...itemBase, id: 'f1' }], total: 1 })
    getMyFeedbackById.mockResolvedValue({ ...itemBase, id: 'f2' })

    const MyFeedbackPage = (await import('../../src/pages/MyFeedbackPage.vue')).default
    const wrapper = mount(MyFeedbackPage, { global: globalPlugins })
    await flushPromises()
    await nextTick()

    expect(getMyFeedbackById).toHaveBeenCalledWith('f2')
    expect(wrapper.findAll('.fb-card').length).toBe(2)
  })

  it('shows error toast when list API fails', async () => {
    getMyFeedback.mockRejectedValue(new Error('fail'))
    const MyFeedbackPage = (await import('../../src/pages/MyFeedbackPage.vue')).default
    mount(MyFeedbackPage, { global: globalPlugins })
    await flushPromises()

    expect(messageApi.error).toHaveBeenCalled()
  })
})

describe('FeedbackTab.vue', () => {
  beforeEach(() => {
    messageApi.error.mockClear()
    getAllFeedback.mockReset()
    getFeedbackById.mockReset()
    replyToFeedback.mockReset()
    updateFeedbackStatus.mockReset()
    getAllFeedback.mockResolvedValue({ items: [{ ...itemBase, id: 'a1', message: 'x'.repeat(120) }], total: 1 })
    getFeedbackById.mockResolvedValue({ ...itemBase, id: 'a1', replies: [] })
    updateFeedbackStatus.mockResolvedValue({ ...itemBase, id: 'a1', status: 'closed', replies: [] })
    replyToFeedback.mockResolvedValue(undefined)
  })

  it('loads table data on mount and opens detail through row click', async () => {
    const FeedbackTab = (await import('../../src/pages/admin/tabs/FeedbackTab.vue')).default
    const wrapper = mount(FeedbackTab, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.find('.n-data-table').exists()).toBe(true)
    await wrapper.find('.row-open').trigger('click')
    await flushPromises()

    expect(getFeedbackById).toHaveBeenCalledWith('a1')
    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('updates status and submits reply from modal', async () => {
    const FeedbackTab = (await import('../../src/pages/admin/tabs/FeedbackTab.vue')).default
    const wrapper = mount(FeedbackTab, { global: globalPlugins })
    await flushPromises()
    await wrapper.find('.row-open').trigger('click')
    await flushPromises()

    const selects = wrapper.findAll('select')
    await selects[2].trigger('change')
    await flushPromises()

    const inputs = wrapper.findAll('input')
    await inputs[1].setValue('Admin reply')
    await wrapper.findAll('.n-modal button')[1].trigger('click')
    await flushPromises()

    expect(updateFeedbackStatus).toHaveBeenCalled()
    expect(replyToFeedback).toHaveBeenCalledWith('a1', { message: 'Admin reply' })
  })

  it('shows error when list loading fails', async () => {
    getAllFeedback.mockRejectedValueOnce(new Error('boom'))
    const FeedbackTab = (await import('../../src/pages/admin/tabs/FeedbackTab.vue')).default
    mount(FeedbackTab, { global: globalPlugins })
    await flushPromises()

    expect(messageApi.error).toHaveBeenCalled()
  })
})
