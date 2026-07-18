import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

import TicketListItem from '../../src/components/helpdesk/TicketListItem.vue'
import type { HelpdeskTicketListItem } from '../../src/api/helpdesk'

// Минимальный словарь i18n — только то, что использует TicketListItem.
const ru = {
  helpdesk: {
    take: 'Взять',
    hasUnread: 'Есть новые сообщения',
    statuses: {
      new: 'Новые', open: 'В работе', pending: 'Ожидание', closed: 'Закрыто',
    },
  },
}

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru },
})

// Naive UI-заглушки: NButton → button, иначе mount падает на регистрации
// компонента (он требует предоставить глобальный NaiveProvider в тестах).
vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['size', 'type', 'ghost', 'loading'],
    emits: ['click'],
  },
  NTag: {
    template: '<span class="n-tag"><slot /></span>',
    props: ['type', 'size', 'round', 'bordered'],
  },
}))

const baseTicket: HelpdeskTicketListItem = {
  id: '00000000-0000-0000-0000-000000000001',
  number: 42,
  subject: 'Не работает VPN',
  status: 'new',
  source: 'web',
  requester_email: 'user@company.local',
  requester_user_id: '00000000-0000-0000-0000-000000000002',
  requester_name: 'Иван Иванов',
  assignee_user_id: null,
  assignee_name: null,
  last_activity_at: '2026-07-18T10:00:00Z',
  created_at: '2026-07-18T09:00:00Z',
}

function mountItem(props: Partial<typeof TicketListItem.props & { ticket: HelpdeskTicketListItem }> & Record<string, unknown> = {}) {
  return mount(TicketListItem, {
    props: { ticket: baseTicket, agentMode: true, ...props } as never,
    global: { plugins: [i18n] },
  })
}

describe('TicketListItem — unread highlight (миграция 080)', () => {
  it('renders unread-dot + unread class when ticket.unread is true', () => {
    const wrapper = mountItem({ ticket: { ...baseTicket, unread: true } })
    expect(wrapper.find('.ticket-row--unread').exists()).toBe(true)
    expect(wrapper.find('.ticket-row__unread-dot').exists()).toBe(true)
  })

  it('no unread-dot + no unread class when unread is false', () => {
    const wrapper = mountItem({ ticket: { ...baseTicket, unread: false } })
    expect(wrapper.find('.ticket-row--unread').exists()).toBe(false)
    expect(wrapper.find('.ticket-row__unread-dot').exists()).toBe(false)
  })

  it('no unread-dot when unread is undefined (requester-view, my-tickets)', () => {
    // ``unread`` не приходит с бэка в не-агентских списках (например,
    // ``/tickets/my`` у заявителя). Должно рендериться как «прочитанное».
    const wrapper = mountItem({ ticket: { ...baseTicket, unread: undefined } })
    expect(wrapper.find('.ticket-row--unread').exists()).toBe(false)
    expect(wrapper.find('.ticket-row__unread-dot').exists()).toBe(false)
  })

  it('sets title attribute "Есть новые сообщения" when unread', () => {
    const wrapper = mountItem({ ticket: { ...baseTicket, unread: true } })
    const row = wrapper.find('.ticket-row')
    expect(row.attributes('title')).toBe('Есть новые сообщения')
  })

  it('no title attribute when not unread', () => {
    const wrapper = mountItem({ ticket: { ...baseTicket, unread: false } })
    const row = wrapper.find('.ticket-row')
    expect(row.attributes('title')).toBeUndefined()
  })

  it('emits open on click', async () => {
    const wrapper = mountItem({ ticket: { ...baseTicket, unread: true } })
    await wrapper.find('.ticket-row').trigger('click')
    expect(wrapper.emitted('open')).toBeTruthy()
    expect(wrapper.emitted('open')![0]).toEqual([baseTicket.id])
  })

  it('emits open on Enter key', async () => {
    const wrapper = mountItem()
    await wrapper.find('.ticket-row').trigger('keydown.enter')
    expect(wrapper.emitted('open')).toBeTruthy()
  })
})
