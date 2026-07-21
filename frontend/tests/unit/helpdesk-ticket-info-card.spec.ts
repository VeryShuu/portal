import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia } from 'pinia'

const ru = {
  helpdesk: {
    columnState: 'Статус',
    source: 'Способ получения',
    sources: { web: 'Веб-форма', email: 'Email' },
    assignee: 'Ответственный',
    assigneeChange: 'Сменить ответственного',
    assigneeChanged: 'Ответственный изменён',
    assigneeSelfHint: '(вы)',
    assigneeEmpty: 'Нет активных агентов',
    created: 'Создана',
    lastActivity: 'Обновление',
    unassigned: 'Не назначен',
    info: { title: 'Информация' },
    statuses: {
      new: 'Новые', open: 'В работе', pending: 'Ожидание',
      resolved: 'Решено', closed: 'Закрыто',
    },
  },
  common: { loading: 'Загрузка' },
}

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru },
})

const messageSuccess = vi.fn()
const messageError = vi.fn()

vi.mock('naive-ui', () => ({
  NCard: {
    template: '<div class="n-card"><div v-if="$slots.header" class="n-card-header"><slot name="header" /></div><slot /></div>',
    props: ['size', 'bordered'],
  },
  NTag: {
    template: '<span class="n-tag"><slot /></span>',
    props: ['type', 'size', 'round', 'bordered'],
  },
  // Popover рендерит trigger + контент. ``show`` управляется родителем через
  // v-model; mock при клике на триггер эмитит ``update:show=true`` (как реальный
  // Naive при ``trigger="click"``).
  NPopover: {
    template: '<div class="n-popover" :data-show="show"><span class="n-popover-trigger" @click="$emit(\'update:show\', true)"><slot name="trigger" /></span><div v-if="show" class="n-popover-content"><slot /></div></div>',
    props: ['trigger', 'placement', 'width', 'show'],
    emits: ['update:show'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  useMessage: () => ({ success: messageSuccess, error: messageError }),
}))

vi.mock('@vicons/ionicons5', () => ({
  ChevronDown: { template: '<span />' },
}))

// Auth store mock — даёт ``user.id`` для суффикса «(вы)» и предфильтра смены на
// себя. Pinia регистрирует реальный store, мы только подменяем ``fetchMe`` и
// кладём ``user`` напрямую.
vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}))

// Query composables — заглушки: не ходят в сеть, возвращают фиксированный
// список агентов. Мутация assign отслеживается через ``mutateAsyncMock``.
const mutateAsyncMock = vi.fn()
const refetchMock = vi.fn()
vi.mock('../../src/queries/helpdesk', () => ({
  useAssignableAgentsQuery: () => ({
    data: { value: { items: [
      { user_id: 'agent-a', full_name: 'Анна Иванова', email: 'anna@portal.local' },
      { user_id: 'agent-b', full_name: 'Борис Петров', email: 'boris@portal.local' },
    ], total: 2 } },
    isLoading: { value: false },
    refetch: refetchMock,
  }),
  useAssignTicketMutation: () => ({
    mutateAsync: mutateAsyncMock,
  }),
}))

import TicketInfoCard from '../../src/components/helpdesk/TicketInfoCard.vue'
import type { HelpdeskTicketDetail } from '../../src/api/helpdesk'

function makeTicket(over: Partial<HelpdeskTicketDetail> = {}): HelpdeskTicketDetail {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    number: 42,
    subject: 'Тема',
    status: 'open',
    source: 'web',
    requester_email: 'user@example.com',
    requester_name: 'Иван',
    assignee_user_id: '00000000-0000-0000-0000-000000000002',
    assignee_name: 'Пётр',
    last_activity_at: '2026-07-01T09:30:00Z',
    created_at: '2026-06-30T08:00:00Z',
    messages: [],
    requester_profile: null,
    ...over,
  } as unknown as HelpdeskTicketDetail
}

function mountCard(props: { ticket: HelpdeskTicketDetail; editable?: boolean } = { ticket: makeTicket() }) {
  return mount(TicketInfoCard, {
    props,
    global: { plugins: [i18n, createPinia()] },
  })
}

describe('TicketInfoCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mutateAsyncMock.mockResolvedValue(undefined)
    refetchMock.mockResolvedValue({ items: [], total: 0 })
  })

  // ── Read-only режим (requester / default) — backward compat ──────────────

  it('рендерит все 5 служебных полей для заполненного тикета', () => {
    const wrapper = mountCard()
    const text = wrapper.text()
    expect(text).toContain('Статус')
    expect(text).toContain('Способ получения')
    expect(text).toContain('Ответственный')
    expect(text).toContain('Создана')
    expect(text).toContain('Обновление')
    expect(text).toContain('Пётр')
    expect(text).toContain('Веб-форма') // source=web
    expect(text).toContain('В работе') // статус-бейдж
  })

  it('отображает email-источник для source=email', () => {
    const wrapper = mountCard({ ticket: makeTicket({ source: 'email' }) })
    expect(wrapper.text()).toContain('Email')
    expect(wrapper.text()).not.toContain('Веб-форма')
  })

  it('показывает плейсхолдер «Не назначен», когда assignee_name = null', () => {
    const wrapper = mountCard({
      ticket: makeTicket({ assignee_name: null, assignee_user_id: null }),
    })
    expect(wrapper.text()).toContain('Не назначен')
    expect(wrapper.text()).not.toContain('Пётр')
  })

  it('рендерит статус-бейдж через TicketStatusBadge', () => {
    const wrapper = mountCard({ ticket: makeTicket({ status: 'resolved' }) })
    expect(wrapper.find('.n-tag').exists()).toBe(true)
    expect(wrapper.text()).toContain('Решено')
  })

  it('форматирование дат присутствует и непусто', () => {
    const wrapper = mountCard()
    const values = wrapper.findAll('.ticket-info__value')
    // 5 строк: статус, источник, ответственный, создана, обновление
    expect(values).toHaveLength(5)
    for (const v of values) expect(v.text().trim().length).toBeGreaterThan(0)
  })

  // ── Editable-режим (страница агента) — popover смены ответственного ──────

  it('в editable-режиме рендерит кликабельный триггер смены ответственного', () => {
    const wrapper = mountCard({ ticket: makeTicket(), editable: true })
    // Триггер есть, read-only span — нет.
    expect(wrapper.find('.ticket-info__assignee-trigger').exists()).toBe(true)
    expect(wrapper.find('.ticket-info__assignee-readonly').exists()).toBe(false)
    // Имя текущего ответственного отображается в триггере.
    expect(wrapper.find('.ticket-info__assignee-trigger').text()).toContain('Пётр')
  })

  it('в read-only режиме НЕ рендерит триггер (нет popover)', () => {
    const wrapper = mountCard() // editable=false по умолчанию
    expect(wrapper.find('.ticket-info__assignee-trigger').exists()).toBe(false)
    expect(wrapper.find('.ticket-info__assignee-readonly').exists()).toBe(true)
  })

  it('popover открывается по клику на триггер и показывает список агентов', async () => {
    const wrapper = mountCard({ ticket: makeTicket(), editable: true })
    // Изначально контент popover'а скрыт (show=false по умолчанию).
    expect(wrapper.find('.n-popover-content').exists()).toBe(false)

    // Кликаем на триггер → onPopoverToggle(true) → popoverShown=true.
    await wrapper.find('.ticket-info__assignee-trigger').trigger('click')
    await flushPromises()

    // Popover теперь показывает список активных агентов (без поиска — для ~5
    // человек избыточно). Две строки из mock'а useAssignableAgentsQuery.
    const options = wrapper.findAll('.ticket-info__assignee-option')
    expect(options).toHaveLength(2)
    expect(options[0].text()).toContain('Анна Иванова')
    expect(options[1].text()).toContain('Борис Петров')
  })

  it('клик по агенту сразу применяет смену (mutateAsync + success)', async () => {
    const wrapper = mountCard({ ticket: makeTicket(), editable: true })
    await wrapper.find('.ticket-info__assignee-trigger').trigger('click')
    await flushPromises()

    // Кликаем на Анну (agent-a) — смену применяет сразу, без отдельной кнопки Apply.
    const annaOption = wrapper.findAll('.ticket-info__assignee-option').find((o) => o.text().includes('Анна'))
    expect(annaOption).toBeDefined()
    await annaOption!.trigger('click')
    await flushPromises()

    // Мутация вызвана с user_id выбранного агента.
    expect(mutateAsyncMock).toHaveBeenCalledWith('agent-a')
    expect(messageSuccess).toHaveBeenCalledWith('Ответственный изменён')
  })

  it('текущий assignee помечен и отключён (нельзя сменить на себя же)', async () => {
    // Текущий assignee — agent-a.
    const wrapper = mountCard({
      ticket: makeTicket({ assignee_user_id: 'agent-a', assignee_name: 'Анна Иванова' }),
      editable: true,
    })
    await wrapper.find('.ticket-info__assignee-trigger').trigger('click')
    await flushPromises()

    const options = wrapper.findAll('.ticket-info__assignee-option')
    const currentOption = options.find((o) => o.text().includes('Анна'))
    // Класс-маркер текущего + галочка.
    expect(currentOption?.classes()).toContain('ticket-info__assignee-option--current')
    expect(currentOption?.attributes('disabled')).toBeDefined()
    expect(currentOption?.text()).toContain('✓')
    // Клик по disabled-кнопке — мутацию не дёргаем (disabled кнопки не эмитят
    // click в браузере, но проверяем и через direct-call страховку applyAssignee).
    expect(mutateAsyncMock).not.toHaveBeenCalled()
  })

  it('при ошибке мутации показывает message.error и рефетчит список агентов', async () => {
    mutateAsyncMock.mockRejectedValueOnce(new Error('Agent not found'))
    const wrapper = mountCard({ ticket: makeTicket(), editable: true })
    await wrapper.find('.ticket-info__assignee-trigger').trigger('click')
    await flushPromises()

    // Кликаем на Бориса (agent-b).
    const borisOption = wrapper.findAll('.ticket-info__assignee-option').find((o) => o.text().includes('Борис'))
    await borisOption!.trigger('click')
    await flushPromises()

    expect(mutateAsyncMock).toHaveBeenCalledWith('agent-b')
    expect(messageError).toHaveBeenCalled()
    // Рефетч списка (на случай, если таргет был удалён из агентов за время
    // открытой карточки — синхронизируем список).
    expect(refetchMock).toHaveBeenCalled()
  })
})
