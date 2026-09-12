/**
 * FE-1 (code-audit P0): XSS через ``room.link``.
 *
 * ``<a :href="room.link">`` рендерился без проверки схемы. Злоумышленный admin
 * (или скомпрометированный admin-endpoint) мог сохранить ``javascript:...`` /
 * ``data:...`` → кликабельный XSS в сетке переговорок.
 *
 * Фикс: ссылка рендерится только для безопасных http(s)/internal схем; иначе —
 * имя комнаты как plain text (как будто link=null).
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

// Мокаем тяжёлые дочерние компоненты, чтобы тест был изолированным.
vi.mock('../../src/components/meetings/BookingCard.vue', () => ({
  default: { name: 'BookingCard', template: '<div class="booking-card-stub" />' },
}))

// useBreakpoints не зависит от DOM-моков — оставляем реальным.

import RoomGrid from '../../src/components/meetings/RoomGrid.vue'
import type { MeetingRoom } from '../../src/api/meetings'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

function makeRoom(overrides: Partial<MeetingRoom> = {}): MeetingRoom {
  return {
    id: 'r1',
    name: 'Переговорка',
    kind: 'physical',
    email: null,
    link: null,
    timezone: 'Europe/Moscow',
    is_active: true,
    sort_order: 0,
    ...overrides,
  }
}

function mountGrid(rooms: MeetingRoom[]) {
  return mount(RoomGrid, {
    props: { rooms, bookings: [], date: '2026-07-11', startHour: 9, endHour: 18 },
    global: {
      plugins: [i18n],
      stubs: { BookingCard: true },
    },
  })
}

describe('RoomGrid — безопасный рендер room.link (FE-1)', () => {
  it('рендерит <a> для https-ссылки', () => {
    const wrapper = mountGrid([makeRoom({ link: 'https://meet.example.com/r1' })])
    const link = wrapper.find('.room-grid__room-name--link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://meet.example.com/r1')
  })

  it('рендерит <a> для внутренней /path-ссылки', () => {
    const wrapper = mountGrid([makeRoom({ link: '/internal/room/r1' })])
    const link = wrapper.find('.room-grid__room-name--link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/internal/room/r1')
  })

  it('НЕ рендерит ссылку для javascript: (XSS-вектор)', () => {
    const wrapper = mountGrid([makeRoom({ link: 'javascript:alert(document.cookie)' })])
    // Опасной ссылки быть не должно — fallback на plain <span>.
    expect(wrapper.find('.room-grid__room-name--link').exists()).toBe(false)
    expect(wrapper.find('span.room-grid__room-name').exists()).toBe(true)
    // Ни одного якоря с опасной схемой.
    const anchors = wrapper.findAll('a')
    expect(anchors.length).toBe(0)
  })

  it('НЕ рендерит ссылку для data: (XSS-вектор)', () => {
    const wrapper = mountGrid([
      makeRoom({ link: 'data:text/html,<script>alert(1)</script>' }),
    ])
    expect(wrapper.find('.room-grid__room-name--link').exists()).toBe(false)
    expect(wrapper.findAll('a').length).toBe(0)
  })

  it('НЕ рендерит ссылку для vbscript: и других схем', () => {
    const wrapper = mountGrid([makeRoom({ link: 'vbscript:msgbox(1)' })])
    expect(wrapper.findAll('a').length).toBe(0)
  })
})
