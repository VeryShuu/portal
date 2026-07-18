import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const ru = {
  helpdesk: {
    myArchiveTitle: 'Архив моих заявок',
    backToList: 'К моим заявкам',
    noTickets: 'Заявок нет',
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

const messageError = vi.fn()
vi.mock('naive-ui', () => ({
  NButton: {
    template: '<a class="n-button"><slot /></a>',
    props: ['quaternary', 'tag', 'href'],
  },
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
  useMessage: () => ({ error: messageError }),
}))

const fetchMyTicketsMock = vi.fn()
vi.mock('../../src/api/helpdesk', () => ({
  fetchMyTickets: (...args: unknown[]) => fetchMyTicketsMock(...args),
}))

import HelpdeskMyArchivePage from '../../src/pages/helpdesk/HelpdeskMyArchivePage.vue'

const stubs = {
  TicketListItem: {
    template: '<div class="ticket-row" @click="$emit(\'open\', ticket.id)">{{ ticket.subject }}</div>',
    props: ['ticket'],
    emits: ['open'],
  },
}

function makeClosedTicket(over: Partial<{ id: string; subject: string }> = {}) {
  return { id: 't1', number: 42, subject: 'Закрытая', status: 'closed', ...over }
}

function mountPage() {
  return mount(HelpdeskMyArchivePage, {
    global: {
      plugins: [i18n],
      stubs,
    },
  })
}

describe('HelpdeskMyArchivePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchMyTicketsMock.mockResolvedValue({ items: [], total: 0 })
  })

  it('рендерит заголовок и кнопку «К моим заявкам»', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('Архив моих заявок')
    expect(wrapper.text()).toContain('К моим заявкам')
  })

  it('показывает пустое состояние при отсутствии закрытых заявок', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.n-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('Заявок нет')
  })

  it('запрашивает только closed тикеты (status=closed)', async () => {
    mountPage()
    await flushPromises()
    expect(fetchMyTicketsMock).toHaveBeenCalledTimes(1)
    expect(fetchMyTicketsMock.mock.calls[0][0]).toMatchObject({
      status: 'closed',
      limit: 20,
      offset: 0,
    })
  })

  it('рендерит список закрытых заявок после загрузки', async () => {
    fetchMyTicketsMock.mockResolvedValue({
      items: [
        makeClosedTicket({ id: 'c1', subject: 'Закрытая 1' }),
        makeClosedTicket({ id: 'c2', subject: 'Закрытая 2' }),
      ],
      total: 2,
    })
    const wrapper = mountPage()
    await flushPromises()
    const rows = wrapper.findAll('.ticket-row')
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain('Закрытая 1')
  })

  it('goToTicket пушит роут helpdesk-my-ticket с id', async () => {
    fetchMyTicketsMock.mockResolvedValue({
      items: [makeClosedTicket({ id: 'closed-xyz' })],
      total: 1,
    })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.ticket-row').trigger('click')
    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'helpdesk-my-ticket',
      params: { id: 'closed-xyz' },
    })
  })

  it('обрабатывает ошибку загрузки через message.error', async () => {
    fetchMyTicketsMock.mockRejectedValue(new Error('network'))
    mountPage()
    await flushPromises()
    expect(messageError).toHaveBeenCalled()
  })
})
