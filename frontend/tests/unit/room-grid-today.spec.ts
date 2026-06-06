import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, params?: Record<string, unknown>) =>
      params ? `${k}|${JSON.stringify(params)}` : k,
  }),
}))

vi.mock('../../src/composables/useBreakpoints', () => ({
  useBreakpoints: () => ({ isMobile: { value: false } }),
}))

vi.mock('naive-ui', () => ({}))

import RoomGrid from '../../src/components/meetings/RoomGrid.vue'

function localToday(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const baseProps = {
  rooms: [{ id: 'r1', name: 'Room 1', sort_order: 0 }],
  bookings: [],
  startHour: 0,
  endHour: 24,
}

describe('RoomGrid — isToday uses local date (B2)', () => {
  it('renders the now-line for the local current date', () => {
    const wrapper = mount(RoomGrid, {
      props: { ...baseProps, date: localToday() } as never,
      global: { stubs: { BookingCard: true } },
    })
    expect(wrapper.find('.room-grid__now-line').exists()).toBe(true)
  })

  it('does not render the now-line for a different date', () => {
    const wrapper = mount(RoomGrid, {
      props: { ...baseProps, date: '2000-01-01' } as never,
      global: { stubs: { BookingCard: true } },
    })
    expect(wrapper.find('.room-grid__now-line').exists()).toBe(false)
  })
})
