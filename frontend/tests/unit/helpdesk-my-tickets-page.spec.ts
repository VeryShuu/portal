import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const ru = {
  helpdesk: {
    myTitle: 'Мои заявки',
    createButton: 'Создать заявку',
    noTickets: 'Заявок нет',
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
    columnAssignee: 'Ответственный',
    columnUpdated: 'Обновление',
  },
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

vi.mock('@vicons/ionicons5', () => ({
  AddOutline: { template: '<span />' },
}))

const messageError = vi.fn()
vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
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
  NRadioGroup: {
    template: '<div class="n-radio-group"><slot /></div>',
    props: ['value'],
    emits: ['update:value'],
  },
  NRadioButton: {
    template: '<label class="n-radio-button"><slot /></label>',
    props: ['value'],
  },
  useMessage: () => ({ error: messageError }),
}))

const fetchMyTicketsMock = vi.fn()
vi.mock('../../src/api/helpdesk', () => ({
  fetchMyTickets: (...args: unknown[]) => fetchMyTicketsMock(...args),
}))

import HelpdeskMyTicketsPage from '../../src/pages/helpdesk/HelpdeskMyTicketsPage.vue'

const stubs = {
  TicketListItem: {
    template: '<div class="ticket-row" @click="$emit(\'open\', ticket.id)">{{ ticket.subject }}</div>',
    props: ['ticket'],
    emits: ['open'],
  },
  TicketCreateModal: {
    template: '<div class="ticket-create-modal" v-if="show" />',
    props: ['show'],
    emits: ['update:show', 'created'],
  },
}

function makeTicket(over: Partial<{ id: string; subject: string; status: string }> = {}) {
  return { id: 't1', number: 42, subject: 'Тема', status: 'open', ...over }
}

function mountPage() {
  return mount(HelpdeskMyTicketsPage, {
    global: {
      plugins: [i18n],
      stubs,
    },
  })
}

describe('HelpdeskMyTicketsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchMyTicketsMock.mockResolvedValue({ items: [], total: 0 })
  })

  it('рендерит заголовок и кнопку создания', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('Мои заявки')
    expect(wrapper.text()).toContain('Создать заявку')
  })

  it('показывает пустое состояние при отсутствии заявок', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.n-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('Заявок нет')
  })

  it('рендерит список заявок после загрузки', async () => {
    fetchMyTicketsMock.mockResolvedValue({
      items: [makeTicket({ id: 't1', subject: 'VPN' }), makeTicket({ id: 't2', subject: 'Принтер' })],
      total: 2,
    })
    const wrapper = mountPage()
    await flushPromises()
    const rows = wrapper.findAll('.ticket-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('VPN')
  })

  it('goToTicket пушит роут helpdesk-my-ticket с id', async () => {
    fetchMyTicketsMock.mockResolvedValue({
      items: [makeTicket({ id: 'abc-123' })],
      total: 1,
    })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.ticket-row').trigger('click')
    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'helpdesk-my-ticket',
      params: { id: 'abc-123' },
    })
  })

  it('обрабатывает ошибку загрузки через message.error', async () => {
    fetchMyTicketsMock.mockRejectedValue(new Error('network'))
    mountPage()
    await flushPromises()
    expect(messageError).toHaveBeenCalled()
  })

  it('кнопка создания открывает модал', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.ticket-create-modal').exists()).toBe(false)
    await wrapper.find('.n-button').trigger('click')
    expect(wrapper.find('.ticket-create-modal').exists()).toBe(true)
  })

  it('передаёт status и pagination в fetchMyTickets', async () => {
    fetchMyTicketsMock.mockResolvedValue({ items: [], total: 0 })
    mountPage()
    await flushPromises()
    expect(fetchMyTicketsMock).toHaveBeenCalledTimes(1)
    const arg = fetchMyTicketsMock.mock.calls[0][0]
    expect(arg).toMatchObject({ limit: 20, offset: 0 })
  })
})
