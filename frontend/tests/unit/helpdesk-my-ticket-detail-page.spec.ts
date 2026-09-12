import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

const ru = {
  helpdesk: {
    backToList: 'Назад к списку',
    yourReply: 'Ваш ответ',
    closedNoReply: 'Заявка закрыта',
    replySent: 'Отправлено',
  },
  errors: { generic: 'Ошибка' },
}

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru },
})

const mockRouterPush = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'ticket-42' } }),
  useRouter: vi.fn(() => ({
    push: (...args: unknown[]) => mockRouterPush(...args),
  })),
}))

vi.mock('../../src/router', () => ({
  ROUTES: { HELPDESK_MY: '/helpdesk/my' },
}))

vi.mock('@vicons/ionicons5', () => ({
  ArrowBackOutline: { template: '<span />' },
}))

const messageError = vi.fn()
const messageSuccess = vi.fn()
vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['text'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NSpin: {
    template: '<div class="n-spin" :data-show="show"><slot /></div>',
    props: ['show'],
  },
  NCard: {
    template: '<div class="n-card"><slot /></div>',
    props: ['size', 'bordered'],
  },
  NAlert: {
    template: '<div class="n-alert"><slot /></div>',
    props: ['type', 'showIcon'],
  },
  useMessage: () => ({ error: messageError, success: messageSuccess }),
}))

const fetchMyTicketMock = vi.fn()
const replyMyTicketMock = vi.fn()
const markMyTicketReadMock = vi.fn()
vi.mock('../../src/api/helpdesk', () => ({
  fetchMyTicket: (...args: unknown[]) => fetchMyTicketMock(...args),
  replyMyTicket: (...args: unknown[]) => replyMyTicketMock(...args),
  markMyTicketRead: (...args: unknown[]) => markMyTicketReadMock(...args),
}))

import HelpdeskMyTicketDetailPage from '../../src/pages/helpdesk/HelpdeskMyTicketDetailPage.vue'
import { queryKeys } from '../../src/queries/keys'

const stubs = {
  TicketDetailHeader: { template: '<div class="ticket-header" />', props: ['ticket'] },
  TicketInfoCard: { template: '<div class="ticket-info" />', props: ['ticket'] },
  TicketMessageList: { template: '<div class="ticket-messages" />', props: ['messages'] },
  TicketReplyForm: {
    template: '<button class="reply-form" @click="$emit(\'submit\', { body_html: \'<p>текст</p>\', files: [] })" :disabled="loading">Ответить</button>',
    props: ['loading', 'ticketId'],
    emits: ['submit'],
  },
  RequesterProfileCard: { template: '<div class="requester-profile" />', props: ['profile'] },
}

function makeTicket(over: Partial<{ id: string; status: string }> = {}) {
  return {
    id: 'ticket-42',
    number: 42,
    subject: 'Тема',
    status: 'open',
    messages: [],
    requester_profile: null,
    ...over,
  } as never
}

function mountPage() {
  // Страница инвалидирует myTicketCounts после markMyTicketRead (красный
  // бейдж «Поддержка» гаснет сразу) — нужен QueryClient в контексте.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return mount(HelpdeskMyTicketDetailPage, {
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient }]], stubs },
  })
}

describe('HelpdeskMyTicketDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchMyTicketMock.mockResolvedValue(makeTicket())
    replyMyTicketMock.mockResolvedValue(undefined)
    markMyTicketReadMock.mockResolvedValue(undefined)
  })

  it('загружает тикет по id из route.params', async () => {
    mountPage()
    await flushPromises()
    expect(fetchMyTicketMock).toHaveBeenCalledWith('ticket-42')
  })

  it('рендерит форму ответа для открытого тикета', async () => {
    fetchMyTicketMock.mockResolvedValue(makeTicket({ status: 'open' }))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.reply-form').exists()).toBe(true)
    expect(wrapper.find('.n-alert').exists()).toBe(false)
  })

  it('показывает алерт вместо формы для закрытого тикета', async () => {
    fetchMyTicketMock.mockResolvedValue(makeTicket({ status: 'closed' }))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.reply-form').exists()).toBe(false)
    expect(wrapper.find('.n-alert').exists()).toBe(true)
    expect(wrapper.text()).toContain('Заявка закрыта')
  })

  it('goBack пушит роут HELPDESK_MY', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.n-button').trigger('click')
    expect(mockRouterPush).toHaveBeenCalledWith('/helpdesk/my')
  })

  it('onReply отправляет ответ и перезагружает тикет', async () => {
    const wrapper = mountPage()
    await flushPromises()
    fetchMyTicketMock.mockClear()

    await wrapper.find('.reply-form').trigger('click')
    await flushPromises()

    expect(replyMyTicketMock).toHaveBeenCalledWith(
      'ticket-42',
      { body_html: '<p>текст</p>' },
      []
    )
    expect(messageSuccess).toHaveBeenCalled()
    expect(fetchMyTicketMock).toHaveBeenCalledTimes(1) // reload после ответа
  })

  it('onReply обрабатывает ошибку через message.error', async () => {
    replyMyTicketMock.mockRejectedValue(new Error('network'))
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('.reply-form').trigger('click')
    await flushPromises()

    expect(messageError).toHaveBeenCalled()
  })

  it('обрабатывает ошибку загрузки через message.error', async () => {
    fetchMyTicketMock.mockRejectedValue(new Error('network'))
    mountPage()
    await flushPromises()
    expect(messageError).toHaveBeenCalled()
  })

  it('после markMyTicketRead инвалидирует myTicketCounts (красный бейдж гаснет)', async () => {
    const invalidateSpy = vi.spyOn(QueryClient.prototype, 'invalidateQueries')
    try {
      mountPage()
      await flushPromises()

      expect(markMyTicketReadMock).toHaveBeenCalledWith('ticket-42')
      // Read-state обновился → счётчик меню перечитывается сразу, без поллинга.
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: queryKeys.helpdesk.myTicketCounts(),
      })
    } finally {
      invalidateSpy.mockRestore()
    }
  })

  it('ошибка markMyTicketRead не валит карточку (best-effort, без инвалидации)', async () => {
    markMyTicketReadMock.mockRejectedValue(new Error('boom'))
    const invalidateSpy = vi.spyOn(QueryClient.prototype, 'invalidateQueries')
    try {
      mountPage()
      await flushPromises()

      // Карточка загружена — read-state косметика, ошибки не показываем.
      expect(fetchMyTicketMock).toHaveBeenCalledWith('ticket-42')
      expect(messageError).not.toHaveBeenCalled()
      expect(invalidateSpy).not.toHaveBeenCalled()
    } finally {
      invalidateSpy.mockRestore()
    }
  })
})
