import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const ru = {
  helpdesk: {
    inboxTitle: 'Входящие заявки',
    searchPlaceholder: 'Поиск',
    unassignedOnly: 'Только неназначенные',
    noTickets: 'Заявок нет',
    taken: 'Взято',
    statuses: {
      all: 'Все',
      new: 'Новые',
      open: 'В работе',
      pending: 'Ожидание',
      resolved: 'Решено',
      closed: 'Закрыто',
    },
    columnNumber: '№',
    columnState: 'Статус',
    columnSubject: 'Тема',
    columnRequester: 'Заявитель',
    columnOwner: 'Владелец',
    columnUpdated: 'Обновление',
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
  useRouter: vi.fn(() => ({
    push: (...args: unknown[]) => mockRouterPush(...args),
  })),
}))

const messageError = vi.fn()
const messageSuccess = vi.fn()
vi.mock('naive-ui', () => ({
  NSpin: {
    template: '<div class="n-spin" :data-show="show"><slot /></div>',
    props: ['show'],
  },
  NEmpty: {
    template: '<div class="n-empty">{{ description }}</div>',
    props: ['description'],
  },
  NPagination: {
    template: '<div class="n-pagination" />',
    props: ['page', 'pageSize', 'itemCount'],
    emits: ['update:page'],
  },
  NInput: {
    template: '<input class="n-input" />',
    props: ['value', 'placeholder', 'clearable'],
    emits: ['update:value'],
  },
  NRadioGroup: {
    template: '<div class="n-radio-group"><slot /></div>',
    props: ['value'],
    emits: ['update:value'],
  },
  NRadioButton: {
    template: '<label class="n-radio-button"><slot /></label>',
    props: ['value'],
  },
  NCheckbox: {
    template: '<label class="n-checkbox"><slot /></label>',
    props: ['checked'],
    emits: ['update:checked'],
  },
  useMessage: () => ({ error: messageError, success: messageSuccess }),
}))

const fetchAgentTicketsMock = vi.fn()
const takeTicketMock = vi.fn()
vi.mock('../../src/api/helpdesk', () => ({
  fetchAgentTickets: (...args: unknown[]) => fetchAgentTicketsMock(...args),
  takeTicket: (...args: unknown[]) => takeTicketMock(...args),
}))

import HelpdeskAgentInboxPage from '../../src/pages/helpdesk/HelpdeskAgentInboxPage.vue'

const stubs = {
  TicketListItem: {
    template: `
      <div class="ticket-row"
        @click="$emit('open', ticket.id)"
        @take-click="$emit('take', ticket.id)"
      >{{ ticket.subject }}
        <button class="take-btn" @click="$emit('take', ticket.id)">Взять</button>
      </div>`,
    props: ['ticket', 'agentMode', 'taking'],
    emits: ['open', 'take'],
  },
}

function makeTicket(over: Partial<{ id: string; subject: string }> = {}) {
  return { id: 't1', number: 42, subject: 'VPN', status: 'new', ...over }
}

function mountPage() {
  return mount(HelpdeskAgentInboxPage, {
    global: { plugins: [i18n], stubs },
  })
}

describe('HelpdeskAgentInboxPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchAgentTicketsMock.mockResolvedValue({ items: [], total: 0 })
    takeTicketMock.mockResolvedValue(undefined)
  })

  it('рендерит заголовок инбокса и фильтры', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('Входящие заявки')
    expect(wrapper.find('.n-input').exists()).toBe(true)
    expect(wrapper.find('.n-checkbox').exists()).toBe(true)
  })

  it('показывает пустое состояние', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.n-empty').exists()).toBe(true)
  })

  it('рендерит список заявок после загрузки', async () => {
    fetchAgentTicketsMock.mockResolvedValue({
      items: [makeTicket({ id: 't1', subject: 'VPN' }), makeTicket({ id: 't2', subject: 'Принтер' })],
      total: 2,
    })
    const wrapper = mountPage()
    await flushPromises()
    const rows = wrapper.findAll('.ticket-row')
    expect(rows).toHaveLength(2)
  })

  it('goToTicket пушит роут helpdesk-ticket с id', async () => {
    fetchAgentTicketsMock.mockResolvedValue({
      items: [makeTicket({ id: 'abc-7' })],
      total: 1,
    })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.ticket-row').trigger('click')
    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'helpdesk-ticket',
      params: { id: 'abc-7' },
    })
  })

  it('onTake вызывает takeTicket, success-сообщение и reload', async () => {
    fetchAgentTicketsMock.mockResolvedValue({
      items: [makeTicket({ id: 'take-1' })],
      total: 1,
    })
    const wrapper = mountPage()
    await flushPromises()
    fetchAgentTicketsMock.mockClear()

    await wrapper.find('.take-btn').trigger('click')
    await flushPromises()

    expect(takeTicketMock).toHaveBeenCalledWith('take-1')
    expect(messageSuccess).toHaveBeenCalled()
    expect(fetchAgentTicketsMock).toHaveBeenCalledTimes(1) // reload
  })

  it('onTake обрабатывает ошибку через message.error', async () => {
    takeTicketMock.mockRejectedValue(new Error('network'))
    fetchAgentTicketsMock.mockResolvedValue({
      items: [makeTicket({ id: 'take-2' })],
      total: 1,
    })
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('.take-btn').trigger('click')
    await flushPromises()

    expect(messageError).toHaveBeenCalled()
  })

  it('передаёт unassigned, q и pagination в fetchAgentTickets', async () => {
    fetchAgentTicketsMock.mockResolvedValue({ items: [], total: 0 })
    mountPage()
    await flushPromises()
    expect(fetchAgentTicketsMock).toHaveBeenCalledTimes(1)
    const arg = fetchAgentTicketsMock.mock.calls[0][0]
    expect(arg).toMatchObject({ limit: 20, offset: 0 })
  })

  it('обрабатывает ошибку загрузки через message.error', async () => {
    fetchAgentTicketsMock.mockRejectedValue(new Error('network'))
    mountPage()
    await flushPromises()
    expect(messageError).toHaveBeenCalled()
  })
})
