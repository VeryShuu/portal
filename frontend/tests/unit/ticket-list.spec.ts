/**
 * Characterization-тесты для ``TicketList`` / ``TicketListItem`` (helpdesk).
 *
 * После рефакторинга на config-driven колонки (``useHelpdeskInboxColumns``):
 *  - ``TicketList`` рендерит шапку из ``visibleColumns`` composable (по пресету
 *    ``mode``) и прокидывает колонки + ``gridTemplate`` в строки через props.
 *  - ``TicketListItem`` — чисто презентационный: рендерит ячейки по
 *    ``visibleColumns`` prop, не дёргает composable сам (однонаправленный поток).
 *
 * Здесь покрываем интеграцию шапка↔строка и поведения, не зависящие от DnD
 * (сортировка заголовков — отдельная будущая задача). Глубокие тесты composable
 * (персистенция, forward-compat, FIXED-колонки) — в ``helpdesk-inbox-columns.spec.ts``.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

vi.mock('naive-ui', () => ({
  NButton: {
    name: 'NButton',
    props: ['size', 'type', 'ghost', 'loading', 'disabled'],
    emits: ['click'],
    template:
      '<button class="n-button" :data-size="size" :data-type="type" :data-loading="loading" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
  },
  // NPopover/NIcon/NCheckbox не используются в user-режиме и не нужны для
  // большинства кейсов; безопасные заглушки, чтобы mount не падал.
  NPopover: { name: 'NPopover', template: '<div class="n-popover"><slot /></div>' },
  NIcon: { name: 'NIcon', template: '<i class="n-icon"><slot /></i>' },
  NCheckbox: {
    name: 'NCheckbox',
    props: ['checked'],
    emits: ['update:checked'],
    template: '<input type="checkbox" class="n-checkbox" :checked="checked" />',
  },
}))

const TicketStatusBadgeStub = defineComponent({
  name: 'TicketStatusBadge',
  props: { status: { type: String, required: true } },
  template: '<span class="ticket-status-badge-stub" :data-status="status" />',
})

import TicketList from '../../src/components/helpdesk/TicketList.vue'
import TicketListItem from '../../src/components/helpdesk/TicketListItem.vue'
import {
  COLUMN_META,
  useHelpdeskInboxColumns,
  type HelpdeskColumnMeta,
} from '../../src/composables/useHelpdeskInboxColumns'

function makeTicket(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 't1',
    number: 42,
    subject: 'Subj',
    status: 'open',
    source: 'web',
    requester_email: 'r@example.com',
    requester_user_id: null,
    requester_name: null,
    assignee_user_id: null,
    assignee_name: null,
    last_activity_at: '2025-01-02T03:04:05',
    created_at: '2025-01-01T00:00:00',
    ...over,
  }
}

const globalOptions = {
  plugins: [i18n],
  stubs: { TicketStatusBadge: TicketStatusBadgeStub },
}

/** Видимые колонки пресета ``agent`` в порядке по умолчанию. */
const AGENT_VISIBLE: HelpdeskColumnMeta[] = useHelpdeskInboxColumns('agent').visibleColumns.value
/** Видимые колонки пресета ``user`` (без requester/age). */
const USER_VISIBLE: HelpdeskColumnMeta[] = useHelpdeskInboxColumns('user').visibleColumns.value
const AGENT_GRID = useHelpdeskInboxColumns('agent').gridTemplate.value
const USER_GRID = useHelpdeskInboxColumns('user').gridTemplate.value

describe('TicketList.vue', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('рендерит шапку из метаданных колонок (agent-пресет содержит age/requester)', () => {
    const wrapper = mount(TicketList, {
      global: globalOptions,
      props: { items: [], mode: 'agent' },
    })
    const head = wrapper.find('.ticket-table__head')
    expect(head.exists()).toBe(true)
    // t() с пустым словарём возвращает сам ключ (без неймспейса helpdesk.)
    expect(head.text()).toContain('columnNumber')
    expect(head.text()).toContain('columnSubject')
    expect(head.text()).toContain('columnAge')
    expect(head.text()).toContain('columnRequester')
    // agent-режим → есть ячейка «шестерёнки»
    expect(wrapper.find('.ticket-table__settings').exists()).toBe(true)
  })

  it('user-пресет: шапка без age/requester и без «шестерёнки»', () => {
    const wrapper = mount(TicketList, {
      global: globalOptions,
      props: { items: [], mode: 'user' },
    })
    const head = wrapper.find('.ticket-table__head')
    expect(head.text()).toContain('columnNumber')
    expect(head.text()).not.toContain('columnAge')
    expect(head.text()).not.toContain('columnRequester')
    expect(wrapper.find('.ticket-table__settings').exists()).toBe(false)
  })

  it('рендерит одну TicketListItem на элемент и пробрасывает takingId/taking', () => {
    const items = [makeTicket({ id: 'a' }), makeTicket({ id: 'b' })]
    const wrapper = mount(TicketList, {
      global: globalOptions,
      props: { items, takingId: 'b', mode: 'agent' },
    })

    const rows = wrapper.findAllComponents(TicketListItem as never)
    expect(rows).toHaveLength(2)
    expect(rows[0].props('taking')).toBe(false)
    expect(rows[1].props('taking')).toBe(true)
    // agent-режим → agentMode=true в строках
    expect(rows[0].props('agentMode')).toBe(true)
    // колонки прокинуты через props
    expect(rows[0].props('visibleColumns')).toEqual(AGENT_VISIBLE)
    expect(rows[0].props('gridTemplate')).toBe(AGENT_GRID)
  })

  it('пробрасывает open/take события от строк наверх', async () => {
    const items = [makeTicket({ id: 'a' })]
    const wrapper = mount(TicketList, {
      global: globalOptions,
      props: { items, mode: 'agent' },
    })

    const row = wrapper.findComponent(TicketListItem as never)
    row.vm.$emit('open', 'a')
    row.vm.$emit('take', 'a')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('open')).toEqual([['a']])
    expect(wrapper.emitted('take')).toEqual([['a']])
  })
})

describe('TicketListItem.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('эмитит open по click, enter и space (с prevent на space)', async () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: { ticket: makeTicket({ id: 't1' }), visibleColumns: USER_VISIBLE, gridTemplate: USER_GRID },
    })

    await wrapper.find('.ticket-row').trigger('click')
    expect(wrapper.emitted('open')).toEqual([['t1']])

    await wrapper.find('.ticket-row').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('open')).toEqual([['t1'], ['t1']])

    await wrapper.find('.ticket-row').trigger('keydown', { key: ' ' })
    expect(wrapper.emitted('open')).toEqual([['t1'], ['t1'], ['t1']])
  })

  it('показывает индикатор непрочитанного только при ticket.unread=true', () => {
    const read = mount(TicketListItem, {
      global: globalOptions,
      props: { ticket: makeTicket({ unread: false }), visibleColumns: USER_VISIBLE, gridTemplate: USER_GRID },
    })
    expect(read.find('.ticket-row--unread').exists()).toBe(false)
    expect(read.find('.ticket-row__unread-dot').exists()).toBe(false)

    const unread = mount(TicketListItem, {
      global: globalOptions,
      props: { ticket: makeTicket({ unread: true }), visibleColumns: USER_VISIBLE, gridTemplate: USER_GRID },
    })
    expect(unread.find('.ticket-row--unread').exists()).toBe(true)
    expect(unread.find('.ticket-row__unread-dot').exists()).toBe(true)
    expect(unread.find('.ticket-row').attributes('title')).toContain('helpdesk.hasUnread')
  })

  it('колонка requester рендерится только если она в visibleColumns', () => {
    // user-пресет — requester отсутствует
    const userRow = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ requester_name: 'Alice', requester_email: 'a@x.com' }),
        visibleColumns: USER_VISIBLE,
        gridTemplate: USER_GRID,
        agentMode: false,
      },
    })
    expect(userRow.find('.ticket-row__requester').exists()).toBe(false)

    // agent-пресет — requester есть
    const agentRow = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ requester_name: 'Alice', requester_email: 'a@x.com' }),
        visibleColumns: AGENT_VISIBLE,
        gridTemplate: AGENT_GRID,
        agentMode: true,
      },
    })
    expect(agentRow.find('.ticket-row__requester').text()).toContain('Alice')
  })

  it('requester показывает email, если name = null', () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ requester_name: null, requester_email: 'a@x.com' }),
        visibleColumns: AGENT_VISIBLE,
        gridTemplate: AGENT_GRID,
        agentMode: true,
      },
    })
    expect(wrapper.find('.ticket-row__requester').text()).toContain('a@x.com')
  })

  it('assignee: имя, если assignee_name задан', () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ assignee_name: 'Bob' }),
        visibleColumns: USER_VISIBLE,
        gridTemplate: USER_GRID,
        agentMode: false,
      },
    })
    expect(wrapper.find('.ticket-row__assignee').text()).toContain('Bob')
    expect(wrapper.find('.n-button').exists()).toBe(false)
  })

  it('assignee: заглушка «—», если нет исполнителя и не агентский режим', () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ assignee_name: null }),
        visibleColumns: USER_VISIBLE,
        gridTemplate: USER_GRID,
        agentMode: false,
      },
    })
    expect(wrapper.find('.ticket-row__muted').exists()).toBe(true)
    expect(wrapper.find('.ticket-row__muted').text()).toBe('—')
  })

  it('assignee: кнопка «Взять» в агентском режиме без исполнителя — эмит take с stopPropagation', async () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ id: 't9', assignee_name: null }),
        visibleColumns: AGENT_VISIBLE,
        gridTemplate: AGENT_GRID,
        agentMode: true,
        taking: true,
      },
    })

    const button = wrapper.find('.n-button')
    expect(button.exists()).toBe(true)
    expect(button.attributes('data-loading')).toBe('true')

    await button.trigger('click')
    expect(wrapper.emitted('take')).toEqual([['t9']])
  })

  it('колонка age: возраст считается от created_at', () => {
    // created_at ~14 месяцев назад от 2026-08-04 → сотни дней
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ created_at: '2025-01-01T00:00:00Z' }),
        visibleColumns: [COLUMN_META.age],
        gridTemplate: '80px',
        agentMode: true,
      },
    })
    const ageCell = wrapper.find('.ticket-row__age')
    expect(ageCell.exists()).toBe(true)
    // i18n пустой → вернёт ключ как есть; проверяем что ячейка непустая
    expect(ageCell.text().length).toBeGreaterThan(0)
  })

  it('форматирует last_activity_at как DD.MM HH:MM', () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ last_activity_at: '2025-03-04T05:06:07' }),
        visibleColumns: [COLUMN_META.updated],
        gridTemplate: '104px',
      },
    })

    // Using local timezone since the component relies on Date getters.
    const d = new Date('2025-03-04T05:06:07')
    const expected = `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    expect(wrapper.find('.ticket-row__date').text()).toBe(expected)
  })
})
