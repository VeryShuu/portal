import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, params?: Record<string, unknown>) => {
      if (params && k.includes('until')) return `${k}:${JSON.stringify(params)}`
      return k
    },
    locale: { value: 'ru' },
  }),
  createI18n: () => ({ global: { t: (k: string) => k, locale: { value: 'ru' } } }),
}))

vi.mock('naive-ui', () => ({
  NModal: {
    template: '<div v-if="show" class="n-modal"><slot /><slot name="footer" /></div>',
    props: ['show', 'title', 'preset'],
    emits: ['update:show'],
  },
  NSpace: { template: '<div class="n-space"><slot /></div>', props: ['justify'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['size', 'type', 'bordered'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['component', 'size'] },
  NTooltip: {
    template: '<span class="n-tooltip"><slot name="trigger" /><slot /></span>',
    props: ['trigger', 'placement'],
  },
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'quaternary'],
    emits: ['click'],
  },
}))

vi.mock('@vicons/ionicons5', () => ({
  VideocamOutline: { template: '<span />' },
  LocationOutline: { template: '<span />' },
}))

import MeetingsList from '../../src/components/meetings/MeetingsList.vue'
import type { BookingOut } from '../../src/api/meetings'

const baseBooking = (invited: BookingOut['invited_users']): BookingOut => ({
  id: 'b1',
  title: 'Test Meeting',
  organizer_name: 'Org',
  creator_id: 'u0',
  description: null,
  start_time: '2026-08-15T10:00:00Z',
  end_time: '2026-08-15T11:00:00Z',
  rooms: [{ id: 'r1', name: 'Room A', kind: 'physical', email: null, link: null, timezone: 'Europe/Moscow', is_active: true, sort_order: 0 }],
  invited_users: invited,
  series_id: null,
  recurrence_rule: null,
  update_count: 0,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
})

const mountList = (booking: BookingOut) =>
  mount(MeetingsList, { props: { show: true, booking, canEdit: false } })

describe('MeetingsList.vue — absence presence in details', () => {
  it('renders presence note under participant name when absent', () => {
    const w = mountList(baseBooking([
      {
        user_id: 'u1', full_name: 'Ivanov Ivan', email: 'ivanov@example.com',
        absence: { category: 'vacation', start_date: '2026-08-10', end_date: '2026-08-15' },
      },
    ]))
    const presence = w.find('.booking-detail__participant-presence')
    expect(presence.exists()).toBe(true)
    expect(presence.text()).toContain('users.presence.vacation')
    expect(presence.classes()).toContain('presence--vacation')
  })

  it('does not render presence when participant has no absence', () => {
    const w = mountList(baseBooking([
      { user_id: 'u1', full_name: 'Ivanov Ivan', email: 'ivanov@example.com' },
    ]))
    expect(w.find('.booking-detail__participant-presence').exists()).toBe(false)
  })

  it('does not render presence when absence is null', () => {
    const w = mountList(baseBooking([
      { user_id: 'u1', full_name: 'Ivanov Ivan', email: 'ivanov@example.com', absence: null },
    ]))
    expect(w.find('.booking-detail__participant-presence').exists()).toBe(false)
  })

  it('renders sick presence with red class', () => {
    const w = mountList(baseBooking([
      {
        user_id: 'u1', full_name: 'Petrov Petr', email: 'petrov@example.com',
        absence: { category: 'sick', start_date: '2026-08-06', end_date: '2026-08-09' },
      },
    ]))
    const presence = w.find('.booking-detail__participant-presence')
    expect(presence.classes()).toContain('presence--sick')
  })
})
