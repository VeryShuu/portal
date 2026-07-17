import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'

const ru = {
  helpdesk: {
    inboxTitle: 'Инбокс поддержки',
    searchPlaceholder: 'Поиск',
    archive: 'Архив',
    backToInbox: 'К инбоксу',
    sectionNew: 'Новые заявки',
    sectionInWork: 'В работе',
    filterMine: 'Только мои',
    filterAllAssigned: 'Все назначенные',
    archive: 'Архив',
    sectionArchive: 'Архив заявок',
    noNewTickets: 'Неназначенных заявок нет',
    noTickets: 'Заявок нет',
    searchResults: 'Результаты поиска',
    showArchive: 'Показать архив',
    hideArchive: 'Скрыть архив',
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

// auth-store mock: пользователь с известным id (для фильтра assignee=mine).
vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 'user-me-123', role: 'admin' },
  }),
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
  NButton: {
    template: '<a class="n-button"><slot /></a>',
    props: ['tag', 'href', 'quaternary'],
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
  TicketList: {
    // Пробрасывает take/open наружу + рендерит строки из items.
    template: `
      <div class="ticket-list">
        <div v-for="t in items" :key="t.id" class="ticket-row" @click="$emit('open', t.id)">
          {{ t.subject }}
          <button class="take-btn" @click.stop="$emit('take', t.id)">Взять</button>
        </div>
      </div>`,
    props: ['items', 'takingId'],
    emits: ['open', 'take'],
  },
}

function makeTicket(over: Partial<{ id: string; subject: string; status: string }> = {}) {
  return { id: 't1', number: 42, subject: 'VPN', status: 'new', last_activity_at: '2026-07-17T00:00:00Z', ...over }
}

function mountPage() {
  return mount(HelpdeskAgentInboxPage, {
    global: { plugins: [i18n], stubs },
  })
}

describe('HelpdeskAgentInboxPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
    fetchAgentTicketsMock.mockResolvedValue({ items: [], total: 0 })
    takeTicketMock.mockResolvedValue(undefined)
  })

  it('рендерит заголовок инбокса и строку поиска', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('Инбокс поддержки')
    expect(wrapper.find('.n-input').exists()).toBe(true)
    // Два блока присутствуют в обычном режиме.
    expect(wrapper.text()).toContain('Новые заявки')
    expect(wrapper.text()).toContain('В работе')
  })

  it('при загрузке делает запросы для новых и в работе (не архив, пока скрыт)', async () => {
    mountPage()
    await flushPromises()
    // Архив скрыт по умолчанию → только 2 запроса: новые + в работе.
    expect(fetchAgentTicketsMock).toHaveBeenCalledTimes(2)
    const calls = fetchAgentTicketsMock.mock.calls.map((c) => c[0])
    expect(calls).toContainEqual(
      expect.objectContaining({ status: 'new', unassigned: true, limit: 20, offset: 0 }),
    )
    expect(calls).toContainEqual(
      expect.objectContaining({ activeOnly: true, assignee: 'user-me-123' }),
    )
  })

  it('показывает пустое состояние для нового блока', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('Неназначенных заявок нет')
  })

  it('рендерит заявки в обоих блоках после загрузки', async () => {
    // Первый вызов (новые), второй (в работе) — оба возвращают тикеты.
    fetchAgentTicketsMock
      .mockResolvedValueOnce({ items: [makeTicket({ id: 'new-1', subject: 'Новая VPN' })], total: 1 })
      .mockResolvedValueOnce({
        items: [makeTicket({ id: 'work-1', subject: 'Принтер', status: 'open' })],
        total: 1,
      })
    const wrapper = mountPage()
    await flushPromises()
    const rows = wrapper.findAll('.ticket-row')
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain('Новая VPN')
    expect(wrapper.text()).toContain('Принтер')
  })

  it('goToTicket пушит роут helpdesk-ticket с id', async () => {
    fetchAgentTicketsMock
      .mockResolvedValueOnce({ items: [makeTicket({ id: 'abc-7' })], total: 1 })
      .mockResolvedValueOnce({ items: [], total: 0 })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.ticket-row').trigger('click')
    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'helpdesk-ticket',
      params: { id: 'abc-7' },
    })
  })

  it('onTake вызывает takeTicket, success и reload', async () => {
    fetchAgentTicketsMock
      .mockResolvedValueOnce({ items: [makeTicket({ id: 'take-1' })], total: 1 })
      .mockResolvedValueOnce({ items: [], total: 0 })
    const wrapper = mountPage()
    await flushPromises()
    fetchAgentTicketsMock.mockClear()

    await wrapper.find('.take-btn').trigger('click')
    await flushPromises()

    expect(takeTicketMock).toHaveBeenCalledWith('take-1')
    expect(messageSuccess).toHaveBeenCalled()
    // reload: снова 2 запроса (новые + в работе).
    expect(fetchAgentTicketsMock).toHaveBeenCalledTimes(2)
  })

  it('onTake обрабатывает ошибку через message.error', async () => {
    takeTicketMock.mockRejectedValue(new Error('network'))
    fetchAgentTicketsMock
      .mockResolvedValueOnce({ items: [makeTicket({ id: 'take-2' })], total: 1 })
      .mockResolvedValueOnce({ items: [], total: 0 })
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('.take-btn').trigger('click')
    await flushPromises()

    expect(messageError).toHaveBeenCalled()
  })

  it('по умолчанию «Только мои» — assignee = мой id в запросе «В работе»', async () => {
    // Дефолтный scope = mine → запрос «В работе» шлёт assignee=myId.
    // (UI-механика переключателя stub↔naive-ui проверяется в E2E, не в unit.)
    mountPage()
    await flushPromises()
    const calls = fetchAgentTicketsMock.mock.calls.map((c) => c[0])
    const inWorkCall = calls.find((c) => c.activeOnly === true)
    expect(inWorkCall).toBeDefined()
    expect(inWorkCall.assignee).toBe('user-me-123')
  })

  it('scope=all из localStorage → assigned=true (без неназначенных)', async () => {
    localStorage.setItem('helpdesk.inbox.scope', 'all')
    mountPage()
    await flushPromises()
    const calls = fetchAgentTicketsMock.mock.calls.map((c) => c[0])
    const inWorkCall = calls.find((c) => c.activeOnly === true)
    expect(inWorkCall).toBeDefined()
    expect(inWorkCall.assignee).toBeUndefined()
    // «Все назначенные» → assigned=true (исключает неназначенные, которые в
    // верхнем блоке «Новые заявки»).
    expect(inWorkCall.assigned).toBe(true)
  })

  it('обрабатывает ошибку загрузки через message.error', async () => {
    fetchAgentTicketsMock.mockRejectedValue(new Error('network'))
    mountPage()
    await flushPromises()
    expect(messageError).toHaveBeenCalled()
  })
})
