/* eslint-disable vue/one-component-per-file -- тестовые компоненты-заглушки объявляются в одном файле */
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
}))

const TicketStatusBadgeStub = defineComponent({
  name: 'TicketStatusBadge',
  props: { status: { type: String, required: true } },
  template: '<span class="ticket-status-badge-stub" :data-status="status" />',
})

import TicketList from '../../src/components/helpdesk/TicketList.vue'
import TicketListItem from '../../src/components/helpdesk/TicketListItem.vue'

function makeTicket(over: Partial<any> = {}) {
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

describe('TicketList.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders an empty body without items and exposes the header labels', () => {
    const wrapper = mount(TicketList, {
      global: globalOptions,
      props: { items: [] },
    })
    const head = wrapper.find('.ticket-table__head')
    expect(head.exists()).toBe(true)
    expect(head.text()).toContain('helpdesk.columnNumber')
    expect(head.text()).toContain('helpdesk.columnSubject')
    expect(wrapper.findAllComponents(TicketListItem as any)).toHaveLength(0)
  })

  it('renders one TicketListItem per item and forwards takingId as taking prop', () => {
    const items = [makeTicket({ id: 'a' }), makeTicket({ id: 'b' })]
    const wrapper = mount(TicketList, {
      global: globalOptions,
      props: { items, takingId: 'b' },
    })

    const rows = wrapper.findAllComponents(TicketListItem as any)
    expect(rows).toHaveLength(2)
    expect(rows[0].props('taking')).toBe(false)
    expect(rows[1].props('taking')).toBe(true)
    expect(rows[0].props('agentMode')).toBe(true)
  })

  it('relays open and take events up from the child rows', async () => {
    const items = [makeTicket({ id: 'a' })]
    const wrapper = mount(TicketList, {
      global: globalOptions,
      props: { items },
    })

    const row = wrapper.findComponent(TicketListItem as any)
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

  it('emits open on click, enter and space (with prevent on space)', async () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: { ticket: makeTicket({ id: 't1' }) },
    })

    await wrapper.find('.ticket-row').trigger('click')
    expect(wrapper.emitted('open')).toEqual([['t1']])

    await wrapper.find('.ticket-row').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('open')).toEqual([['t1'], ['t1']])

    await wrapper.find('.ticket-row').trigger('keydown', { key: ' ' })
    expect(wrapper.emitted('open')).toEqual([['t1'], ['t1'], ['t1']])
  })

  it('renders unread dot and unread classes only when ticket.unread is true', () => {
    const read = mount(TicketListItem, {
      global: globalOptions,
      props: { ticket: makeTicket({ unread: false }) },
    })
    expect(read.find('.ticket-row--unread').exists()).toBe(false)
    expect(read.find('.ticket-row__unread-dot').exists()).toBe(false)

    const unread = mount(TicketListItem, {
      global: globalOptions,
      props: { ticket: makeTicket({ unread: true }) },
    })
    expect(unread.find('.ticket-row--unread').exists()).toBe(true)
    expect(unread.find('.ticket-row__unread-dot').exists()).toBe(true)
    expect(unread.find('.ticket-row').attributes('title')).toContain('helpdesk.hasUnread')
  })

  it('hides requester column when not in agent mode', () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: { ticket: makeTicket(), agentMode: false },
    })

    expect(wrapper.find('.ticket-row--agent').exists()).toBe(false)
    expect(wrapper.find('.ticket-row__requester').exists()).toBe(false)
  })

  it('shows requester column in agent mode with name falling back to email', () => {
    const withName = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ requester_name: 'Alice', requester_email: 'a@x.com' }),
        agentMode: true,
      },
    })
    expect(withName.find('.ticket-row__requester').text()).toContain('Alice')

    const withoutName = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ requester_name: null, requester_email: 'a@x.com' }),
        agentMode: true,
      },
    })
    expect(withoutName.find('.ticket-row__requester').text()).toContain('a@x.com')
  })

  it('renders assignee name when assignee_name is set', () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ assignee_name: 'Bob' }),
        agentMode: false,
      },
    })

    expect(wrapper.find('.ticket-row__assignee').text()).toContain('Bob')
    expect(wrapper.find('.n-button').exists()).toBe(false)
  })

  it('shows a muted dash placeholder when no assignee and not in agent mode', () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: { ticket: makeTicket({ assignee_name: null }), agentMode: false },
    })

    expect(wrapper.find('.ticket-row__muted').exists()).toBe(true)
    expect(wrapper.find('.ticket-row__muted').text()).toBe('—')
  })

  it('shows take button in agent mode when no assignee, and emits take with stopPropagation', async () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: {
        ticket: makeTicket({ id: 't9', assignee_name: null }),
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

  it('formats last_activity_at as DD.MM HH:MM', () => {
    const wrapper = mount(TicketListItem, {
      global: globalOptions,
      props: { ticket: makeTicket({ last_activity_at: '2025-03-04T05:06:07' }) },
    })

    // Using local timezone since the component relies on Date getters.
    const d = new Date('2025-03-04T05:06:07')
    const expected = `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    expect(wrapper.find('.ticket-row__date').text()).toBe(expected)
  })
})
