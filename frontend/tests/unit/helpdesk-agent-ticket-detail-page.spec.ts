import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const ru = {
  helpdesk: {
    backToInbox: 'Назад к входящим',
    take: 'Взять',
    reopen: 'Переоткрыть',
    reopened: 'Переоткрыто',
    taken: 'Взято',
    statusChanged: 'Статус изменён',
    agentReply: 'Ответ агенту',
    replySent: 'Отправлено',
    statuses: {
      open: 'В работе',
      pending: 'Ожидание',
      closed: 'Закрыто',
    },
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
  useRoute: () => ({ params: { id: 'ticket-99' } }),
  useRouter: vi.fn(() => ({
    push: (...args: unknown[]) => mockRouterPush(...args),
  })),
}))

vi.mock('../../src/router', () => ({
  ROUTES: { HELPDESK_INBOX: '/helpdesk' },
}))

vi.mock('@vicons/ionicons5', () => ({
  ArrowBackOutline: { template: '<span />' },
}))

const messageError = vi.fn()
const messageSuccess = vi.fn()
vi.mock('naive-ui', () => ({
  NButton: {
    template:
      '<button class="n-button" :data-loading="loading" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['text', 'size', 'type', 'ghost', 'loading'],
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
  NSelect: {
    template: '<select class="n-select" @change="$emit(\'update:value\', $event.target.value)"><option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select>',
    props: ['value', 'options', 'size', 'loading'],
    emits: ['update:value'],
  },
  useMessage: () => ({ error: messageError, success: messageSuccess }),
}))

const fetchAgentTicketMock = vi.fn()
const takeTicketMock = vi.fn()
const changeTicketStatusMock = vi.fn()
const reopenTicketMock = vi.fn()
const replyAgentTicketMock = vi.fn()
vi.mock('../../src/api/helpdesk', () => ({
  fetchAgentTicket: (...args: unknown[]) => fetchAgentTicketMock(...args),
  takeTicket: (...args: unknown[]) => takeTicketMock(...args),
  changeTicketStatus: (...args: unknown[]) => changeTicketStatusMock(...args),
  reopenTicket: (...args: unknown[]) => reopenTicketMock(...args),
  replyAgentTicket: (...args: unknown[]) => replyAgentTicketMock(...args),
}))

import HelpdeskAgentTicketDetailPage from '../../src/pages/helpdesk/HelpdeskAgentTicketDetailPage.vue'

const stubs = {
  TicketDetailHeader: {
    template: '<div class="ticket-header"><slot name="actions" /></div>',
    props: ['ticket'],
  },
  TicketInfoCard: { template: '<div class="ticket-info" />', props: ['ticket'] },
  TicketMessageList: { template: '<div class="ticket-messages" />', props: ['messages', 'agentMode'] },
  TicketReplyForm: {
    template: '<button class="reply-form" @click="$emit(\'submit\', { body_html: \'<p>ответ</p>\', files: [] })">Ответить</button>',
    props: ['agentMode', 'loading', 'ticketId'],
    emits: ['submit'],
  },
  RequesterProfileCard: { template: '<div class="requester-profile" />', props: ['profile'] },
}

function makeTicket(
  over: Partial<{ id: string; status: string; assignee_user_id: string | null }> = {},
) {
  return {
    id: 'ticket-99',
    number: 99,
    subject: 'Тема',
    status: 'open',
    assignee_user_id: null,
    messages: [],
    requester_profile: null,
    ...over,
  } as never
}

function mountPage() {
  return mount(HelpdeskAgentTicketDetailPage, {
    global: { plugins: [i18n], stubs },
  })
}

describe('HelpdeskAgentTicketDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchAgentTicketMock.mockResolvedValue(makeTicket())
    takeTicketMock.mockResolvedValue(undefined)
    changeTicketStatusMock.mockResolvedValue(undefined)
    reopenTicketMock.mockResolvedValue(undefined)
    replyAgentTicketMock.mockResolvedValue(undefined)
  })

  it('загружает тикет по id из route.params', async () => {
    mountPage()
    await flushPromises()
    expect(fetchAgentTicketMock).toHaveBeenCalledWith('ticket-99')
  })

  it('показывает кнопку Take для неназначенного тикета', async () => {
    fetchAgentTicketMock.mockResolvedValue(makeTicket({ assignee_user_id: null }))
    const wrapper = mountPage()
    await flushPromises()
    const buttons = wrapper.findAll('.n-button')
    const takeBtn = buttons.find((b) => b.text().includes('Взять'))
    expect(takeBtn).toBeDefined()
    expect(wrapper.find('.n-select').exists()).toBe(false)
  })

  it('показывает n-select статусов для назначенного тикета', async () => {
    fetchAgentTicketMock.mockResolvedValue(makeTicket({ assignee_user_id: 'agent-1' }))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.n-select').exists()).toBe(true)
    // Кнопки Take нет (есть assignee).
    const buttons = wrapper.findAll('.n-button')
    expect(buttons.find((b) => b.text().includes('Взять'))).toBeUndefined()
  })

  it('onTake вызывает takeTicket, success и reload', async () => {
    fetchAgentTicketMock.mockResolvedValue(makeTicket({ assignee_user_id: null }))
    const wrapper = mountPage()
    await flushPromises()
    fetchAgentTicketMock.mockClear()

    const takeBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('Взять'))!
    await takeBtn.trigger('click')
    await flushPromises()

    expect(takeTicketMock).toHaveBeenCalledWith('ticket-99')
    expect(messageSuccess).toHaveBeenCalled()
    expect(fetchAgentTicketMock).toHaveBeenCalledTimes(1) // reload
  })

  it('onStatusChange вызывает changeTicketStatus', async () => {
    fetchAgentTicketMock.mockResolvedValue(makeTicket({ assignee_user_id: 'agent-1' }))
    const wrapper = mountPage()
    await flushPromises()
    changeTicketStatusMock.mockClear()

    await wrapper.find('.n-select').setValue('closed')
    await wrapper.find('.n-select').trigger('change')
    await flushPromises()

    expect(changeTicketStatusMock).toHaveBeenCalledWith('ticket-99', 'closed')
    expect(messageSuccess).toHaveBeenCalled()
  })

  it('кнопка Reopen видна только для закрытого тикета', async () => {
    // Не закрыт — кнопки Reopen нет.
    fetchAgentTicketMock.mockResolvedValue(makeTicket({ status: 'open', assignee_user_id: 'a' }))
    let wrapper = mountPage()
    await flushPromises()
    expect(wrapper.findAll('.n-button').find((b) => b.text().includes('Переоткрыть'))).toBeUndefined()

    // Закрыт — кнопка появляется.
    fetchAgentTicketMock.mockResolvedValue(makeTicket({ status: 'closed', assignee_user_id: 'a' }))
    wrapper = mountPage()
    await flushPromises()
    const reopenBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('Переоткрыть'))
    expect(reopenBtn).toBeDefined()
  })

  it('onReopen вызывает reopenTicket', async () => {
    fetchAgentTicketMock.mockResolvedValue(makeTicket({ status: 'closed', assignee_user_id: 'a' }))
    const wrapper = mountPage()
    await flushPromises()
    reopenTicketMock.mockClear()

    const reopenBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('Переоткрыть'))!
    await reopenBtn.trigger('click')
    await flushPromises()

    expect(reopenTicketMock).toHaveBeenCalledWith('ticket-99')
    expect(messageSuccess).toHaveBeenCalled()
  })

  it('onReply отправляет ответ агента', async () => {
    const wrapper = mountPage()
    await flushPromises()
    fetchAgentTicketMock.mockClear()

    await wrapper.find('.reply-form').trigger('click')
    await flushPromises()

    expect(replyAgentTicketMock).toHaveBeenCalledWith(
      'ticket-99',
      { body_html: '<p>ответ</p>' },
      [],
    )
    expect(messageSuccess).toHaveBeenCalled()
  })

  it('goBack пушит роут HELPDESK_INBOX', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.n-button').trigger('click')
    expect(mockRouterPush).toHaveBeenCalledWith('/helpdesk')
  })

  it('обрабатывает ошибку загрузки через message.error', async () => {
    fetchAgentTicketMock.mockRejectedValue(new Error('network'))
    mountPage()
    await flushPromises()
    expect(messageError).toHaveBeenCalled()
  })
})
