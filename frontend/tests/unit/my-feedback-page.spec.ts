import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NCard: {
    name: 'NCard',
    template: '<div class="n-card" @click="$emit(\'click\')"><slot /></div>',
    props: ['bordered', 'size', 'hoverable'],
    emits: ['click'],
  },
  NPagination: {
    name: 'NPagination',
    template: '<div class="n-pagination" />',
    props: ['page', 'pageCount', 'pageSize', 'itemCount'],
    emits: ['update:page'],
  },
  NRadioButton: { name: 'NRadioButton', template: '<label class="n-radio-button"><slot /></label>', props: ['value', 'label'] },
  NRadioGroup: {
    name: 'NRadioGroup',
    template: '<div class="n-radio-group"><slot /></div>',
    props: ['value', 'size'],
    emits: ['update:value'],
  },
  NSpin: { name: 'NSpin', template: '<div class="n-spin" />', props: ['show', 'size'] },
  NTag: { name: 'NTag', template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'bordered', 'closable'], emits: ['close'] },
  useMessage: () => ({ success: mockMessageSuccess, error: mockMessageError, warning: vi.fn(), info: vi.fn() }),
}))

const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()

const mockRouteState: { query: Record<string, string | undefined>; params: Record<string, string> } = {
  query: {},
  params: {},
}

const mockRouterReplace = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn(),
    replace: (...args: unknown[]) => mockRouterReplace(...args),
  })),
  useRoute: vi.fn(() => mockRouteState),
}))

const mockGetMyFeedback = vi.fn().mockResolvedValue({ items: [], total: 0 })
const mockGetMyFeedbackById = vi.fn()

vi.mock('../../src/api/feedback', () => ({
  getMyFeedback: (...args: unknown[]) => mockGetMyFeedback(...args),
  getMyFeedbackById: (...args: unknown[]) => mockGetMyFeedbackById(...args),
}))

vi.mock('../../src/utils/formatDate', () => ({
  formatDate: vi.fn((_d: unknown, locale: string) => `formatted[${locale}]`),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'Something went wrong'),
}))

const EmptyStateStub = defineComponent({
  name: 'EmptyState',
  props: {
    variant: { type: String, default: 'default' },
    title: { type: String, default: '' },
    description: { type: String, default: '' },
    compact: { type: Boolean, default: false },
  },
  template: '<div class="empty-state-stub" :data-variant="variant" :data-title="title" />',
})

const FeedbackAttachmentListStub = defineComponent({
  name: 'FeedbackAttachmentList',
  props: { attachments: { type: Array, default: () => [] } },
  template: '<div class="feedback-attachments-stub" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    EmptyState: EmptyStateStub,
    FeedbackAttachmentList: FeedbackAttachmentListStub,
  },
}

async function mountPage() {
  const MyFeedbackPage = (await import('../../src/pages/MyFeedbackPage.vue')).default
  const wrapper = mount(MyFeedbackPage, { global: globalOptions })
  await flushPromises()
  return wrapper
}

describe('MyFeedbackPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())

    mockRouteState.query = {}
    mockRouteState.params = {}

    mockMessageSuccess.mockClear()
    mockMessageError.mockClear()
    mockRouterReplace.mockClear()

    mockGetMyFeedback.mockClear()
    mockGetMyFeedback.mockResolvedValue({ items: [], total: 0 })
    mockGetMyFeedbackById.mockReset()

    // jsdom doesn't implement scrollIntoView
    vi.stubGlobal('scrollIntoView', vi.fn())
    Element.prototype.scrollIntoView = vi.fn() as unknown as Element['scrollIntoView']
  })

  it('shows spinner while first load is in flight, then hides it', async () => {
    let resolveLoad!: (v: { items: unknown[]; total: number }) => void
    mockGetMyFeedback.mockReturnValueOnce(new Promise((res) => { resolveLoad = res }))

    const wrapper = await mountPage()

    // While pending, loader is rendered
    expect(wrapper.find('.loader').exists()).toBe(true)

    resolveLoad({ items: [], total: 0 })
    await flushPromises()

    expect(wrapper.find('.loader').exists()).toBe(false)
  })

  it('calls API with default pagination params and renders empty state when no items', async () => {
    const wrapper = await mountPage()

    expect(mockGetMyFeedback).toHaveBeenCalledWith({ limit: 20, offset: 0 })
    const empty = wrapper.find('.empty-state-stub')
    expect(empty.exists()).toBe(true)
  })

  it('renders cards for each feedback item and shows category/status tags', async () => {
    mockGetMyFeedback.mockResolvedValueOnce({
      items: [
        {
          id: 'f1',
          category: 'bug',
          message: 'Login fails',
          page_url: null,
          status: 'open',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          replies: [],
          attachments: [],
        },
        {
          id: 'f2',
          category: 'suggestion',
          message: 'Add dark mode',
          page_url: '/settings',
          status: 'in_progress',
          created_at: '2026-01-02T00:00:00Z',
          updated_at: '2026-01-02T00:00:00Z',
          replies: [],
          attachments: [],
        },
      ],
      total: 2,
    })

    const wrapper = await mountPage()

    const cards = wrapper.findAll('.fb-card')
    expect(cards).toHaveLength(2)
    // Each card head shows 2 tags (category + status)
    expect(cards[0].findAll('.n-tag')).toHaveLength(2)
    // Preview is collapsed by default
    expect(cards[0].find('.fb-card__preview').exists()).toBe(true)
    expect(cards[0].find('.fb-card__details').exists()).toBe(false)
  })

  it('expands a card on click, revealing details and attachments; click again collapses', async () => {
    mockGetMyFeedback.mockResolvedValueOnce({
      items: [
        {
          id: 'f1',
          category: 'bug',
          message: 'Login fails',
          page_url: '/login',
          status: 'open',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          replies: [],
          attachments: [{ id: 'a1', original_name: 'a.png' }],
        },
      ],
      total: 1,
    })

    const wrapper = await mountPage()
    const card = wrapper.find('.fb-card')

    await card.trigger('click')
    await nextTick()

    expect(card.find('.fb-card__details').exists()).toBe(true)
    expect(card.find('.fb-card__preview').exists()).toBe(false)
    expect(card.find('.fb-card__url').exists()).toBe(true)
    expect(card.find('.feedback-attachments-stub').exists()).toBe(true)
    expect(card.find('.fb-card__replies .muted').exists()).toBe(true)

    // Click on details block should NOT collapse (click.stop)
    await card.find('.fb-card__details').trigger('click')
    await nextTick()
    expect(card.find('.fb-card__details').exists()).toBe(true)

    // Click on card head again collapses
    await card.trigger('click')
    await nextTick()
    expect(card.find('.fb-card__preview').exists()).toBe(true)
  })

  it('shows reply list with admin name when replies exist', async () => {
    mockGetMyFeedback.mockResolvedValueOnce({
      items: [
        {
          id: 'f1',
          category: 'other',
          message: 'Question',
          page_url: null,
          status: 'closed',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          replies: [
            {
              id: 'r1',
              admin_id: 'a1',
              admin_name: 'Alice',
              message: 'Fixed',
              created_at: '2026-01-03T00:00:00Z',
            },
          ],
          attachments: [],
        },
      ],
      total: 1,
    })

    const wrapper = await mountPage()

    const card = wrapper.find('.fb-card')
    await card.trigger('click')
    await nextTick()

    expect(card.find('.reply').exists()).toBe(true)
    expect(card.find('.reply__head').text()).toContain('Alice')
    expect(card.find('.fb-card__count').exists()).toBe(true)
  })

  it('reloads with status filter when radio group value changes and resets page to 1', async () => {
    const wrapper = await mountPage()
    mockGetMyFeedback.mockClear()

    wrapper.findComponent({ name: 'NRadioGroup' }).vm.$emit('update:value', 'open')
    await flushPromises()

    expect(mockGetMyFeedback).toHaveBeenCalledWith({ status: 'open', limit: 20, offset: 0 })
  })

  it('renders pagination when total exceeds limit and loads requested page', async () => {
    mockGetMyFeedback.mockResolvedValueOnce({ items: [{ id: 'f1', category: 'bug', message: 'm', page_url: null, status: 'open', created_at: '', updated_at: '', replies: [], attachments: [] }], total: 50 })

    const wrapper = await mountPage()
    expect(wrapper.find('.pager').exists()).toBe(true)

    mockGetMyFeedback.mockClear()
    wrapper.findComponent({ name: 'NPagination' }).vm.$emit('update:page', 3)
    await flushPromises()

    expect(mockGetMyFeedback).toHaveBeenCalledWith({ limit: 20, offset: 40 })
  })

  it('shows error toast when initial load fails', async () => {
    mockGetMyFeedback.mockRejectedValueOnce(new Error('boom'))

    await mountPage()

    expect(mockMessageError).toHaveBeenCalledWith('Something went wrong')
  })

  it('opens specific ticket from ?open=<id> query and falls back to fetch by id if missing from list', async () => {
    mockGetMyFeedback.mockResolvedValueOnce({ items: [], total: 0 })
    mockGetMyFeedbackById.mockResolvedValueOnce({
      id: 'target-id',
      category: 'bug',
      message: 'Target ticket',
      page_url: null,
      status: 'open',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      replies: [],
      attachments: [],
    })

    mockRouteState.query = { open: 'target-id' }

    const wrapper = await mountPage()

    expect(mockGetMyFeedbackById).toHaveBeenCalledWith('target-id')
    const card = wrapper.find('.fb-card')
    expect(card.exists()).toBe(true)
    // Card is auto-expanded from ?open
    expect(card.find('.fb-card__details').exists()).toBe(true)
  })

  it('clears ?open query and shows notFound error when open-id fetch fails', async () => {
    mockGetMyFeedback.mockResolvedValueOnce({ items: [], total: 0 })
    mockGetMyFeedbackById.mockRejectedValueOnce(new Error('not found'))

    mockRouteState.query = { open: 'missing-id' }

    await mountPage()

    expect(mockGetMyFeedbackById).toHaveBeenCalledWith('missing-id')
    expect(mockMessageError).toHaveBeenCalledWith('feedback.notFound')
    expect(mockRouterReplace).toHaveBeenCalled()
  })
})
