import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string) => k,
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

describe('MeetingsList.vue — RSVP badges in details', () => {
  it.each([
    ['accepted', 'rsvp--accepted', '✓'],
    ['declined', 'rsvp--declined', '−'],
    ['tentative', 'rsvp--tentative', '±'],
  ] as const)('renders %s icon with status class', (status, cls, icon) => {
    const w = mountList(baseBooking([
      {
        user_id: 'u1', full_name: 'Ivanov Ivan', email: 'ivanov@example.com', source: 'keycloak',
        rsvp: { status, updated_at: '2026-08-14T10:00:00Z' },
      },
    ]))
    const badge = w.find('.booking-detail__participant-rsvp')
    expect(badge.exists()).toBe(true)
    expect(badge.classes()).toContain(cls)
    expect(badge.text()).toBe(icon)
    expect(badge.attributes('title')).toBe(`meetings.rsvp.${status}`)
  })

  it('places the icon on the same line as the participant name', () => {
    const w = mountList(baseBooking([
      {
        user_id: 'u1', full_name: 'Ivanov Ivan', email: 'ivanov@example.com', source: 'keycloak',
        rsvp: { status: 'accepted', updated_at: '2026-08-14T10:00:00Z' },
      },
    ]))
    const main = w.find('.booking-detail__participant-main')
    expect(main.exists()).toBe(true)
    expect(main.find('.booking-detail__participant-name').exists()).toBe(true)
    expect(main.find('.booking-detail__participant-rsvp').exists()).toBe(true)
    expect(main.text()).toContain('Ivanov Ivan')
  })

  it('keeps the icon beside the name when emails are toggled on', async () => {
    const w = mountList(baseBooking([
      {
        user_id: 'u1', full_name: 'Ivanov Ivan', email: 'ivanov@example.com', source: 'keycloak',
        rsvp: { status: 'declined', updated_at: '2026-08-14T10:00:00Z' },
      },
    ]))
    await w.find('.booking-detail__toggle-emails').trigger('click')
    const email = w.find('.booking-detail__participant-email')
    expect(email.exists()).toBe(true)
    expect(email.attributes('href')).toBe('mailto:ivanov@example.com')
    const main = w.find('.booking-detail__participant-main')
    expect(main.find('.booking-detail__participant-name').text()).toBe('Ivanov Ivan')
    expect(main.find('.booking-detail__participant-rsvp').text()).toBe('−')
  })

  it('does not render badge when participant has not replied', () => {
    const w = mountList(baseBooking([
      { user_id: 'u1', full_name: 'Ivanov Ivan', email: 'ivanov@example.com', source: 'keycloak', rsvp: null },
    ]))
    expect(w.find('.booking-detail__participant-rsvp').exists()).toBe(false)
  })
})
