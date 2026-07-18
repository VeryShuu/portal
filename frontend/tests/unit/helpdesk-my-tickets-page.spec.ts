import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const ru = {
  helpdesk: {
    myTitle: 'Мои заявки',
    createButton: 'Создать заявку',
    archive: 'Архив',
    sectionWaiting: 'Ожидают принятия',
    sectionMyInWork: 'В работе у специалиста',
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

vi.mock('@vicons/ionicons5', () => ({
  AddOutline: { template: '<span />' },
}))

const messageError = vi.fn()
vi.mock('naive-ui', () => ({
  NButton: {
    // ``tag="a"`` рендерит ``<a>``, иначе ``<button>``. Для теста — единый
    // ``<button>``, но с ``data-href`` чтобы различать «Архив» (link) и обычные.
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'tag', 'href'],
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

describe('HelpdeskMyTicketsPage (двухблочный вид)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Дефолтный мок: оба блока пусты.
    fetchMyTicketsMock.mockResolvedValue({ items: [], total: 0 })
  })

  it('рендерит заголовок, кнопку создания и кнопку Архив', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('Мои заявки')
    expect(wrapper.text()).toContain('Создать заявку')
    expect(wrapper.text()).toContain('Архив')
  })

  it('рендерит оба заголовка секций (Ожидают / В работе)', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('Ожидают принятия')
    expect(wrapper.text()).toContain('В работе у специалиста')
  })

  it('показывает пустое состояние при отсутствии заявок', async () => {
    const wrapper = mountPage()
    await flushPromises()
    // Оба блока пустые → 2 n-empty.
    expect(wrapper.findAll('.n-empty')).toHaveLength(2)
    expect(wrapper.text()).toContain('Заявок нет')
  })

  it('запрашивает два блока с правильными фильтрами (unassigned/assigned)', async () => {
    mountPage()
    await flushPromises()
    // Два вызова: один для блока «ожидают» (unassigned), второй для «в работе» (assigned).
    expect(fetchMyTicketsMock).toHaveBeenCalledTimes(2)
    const calls = fetchMyTicketsMock.mock.calls.map((c: unknown[]) => c[0])
    const waitingCall = calls.find((c: Record<string, unknown>) => c.unassigned === true)
    const inWorkCall = calls.find((c: Record<string, unknown>) => c.assigned === true)
    expect(waitingCall).toBeDefined()
    expect(waitingCall).toMatchObject({ unassigned: true, limit: 20, offset: 0 })
    expect(inWorkCall).toBeDefined()
    expect(inWorkCall).toMatchObject({ assigned: true, limit: 20, offset: 0 })
  })

  it('рендерит тикеты в обоих блоках после загрузки', async () => {
    // 1-й вызов (unassigned) → 1 тикет, 2-й (assigned) → 2 тикета.
    fetchMyTicketsMock
      .mockResolvedValueOnce({ items: [makeTicket({ id: 'w1', subject: 'Ждёт агента' })], total: 1 })
      .mockResolvedValueOnce({
        items: [
          makeTicket({ id: 'a1', subject: 'В работе 1' }),
          makeTicket({ id: 'a2', subject: 'В работе 2' }),
        ],
        total: 2,
      })
    const wrapper = mountPage()
    await flushPromises()
    const rows = wrapper.findAll('.ticket-row')
    expect(rows).toHaveLength(3)
    expect(wrapper.text()).toContain('Ждёт агента')
    expect(wrapper.text()).toContain('В работе 1')
  })

  it('goToTicket пушит роут helpdesk-my-ticket с id', async () => {
    fetchMyTicketsMock.mockResolvedValueOnce({
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
    // На странице 2 кнопки (Архив-link + Создать). Создать — type=primary.
    const buttons = wrapper.findAll('.n-button')
    const createBtn = buttons.find((b) => b.text().includes('Создать заявку'))
    expect(createBtn).toBeDefined()
    await createBtn!.trigger('click')
    expect(wrapper.find('.ticket-create-modal').exists()).toBe(true)
  })
})
