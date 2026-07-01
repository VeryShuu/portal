import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const ru = {
  helpdesk: {
    columnState: 'Статус',
    source: 'Способ получения',
    sources: { web: 'Веб-форма', email: 'Email' },
    assignee: 'Ответственный',
    created: 'Создана',
    lastActivity: 'Обновление',
    unassigned: 'Не назначен',
    info: { title: 'Информация' },
    statuses: {
      new: 'Новые', open: 'В работе', pending: 'Ожидание',
      resolved: 'Решено', closed: 'Закрыто',
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

vi.mock('naive-ui', () => ({
  NCard: {
    template: '<div class="n-card"><div v-if="$slots.header" class="n-card-header"><slot name="header" /></div><slot /></div>',
    props: ['size', 'bordered'],
  },
  NTag: {
    template: '<span class="n-tag"><slot /></span>',
    props: ['type', 'size', 'round', 'bordered'],
  },
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

describe('TicketInfoCard', () => {
  it('рендерит все 5 служебных полей для заполненного тикета', () => {
    const wrapper = mount(TicketInfoCard, {
      props: { ticket: makeTicket() },
      global: { plugins: [i18n] },
    })
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
    const wrapper = mount(TicketInfoCard, {
      props: { ticket: makeTicket({ source: 'email' }) },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Email')
    expect(wrapper.text()).not.toContain('Веб-форма')
  })

  it('показывает плейсхолдер «Не назначен», когда assignee_name = null', () => {
    const wrapper = mount(TicketInfoCard, {
      props: { ticket: makeTicket({ assignee_name: null, assignee_user_id: null }) },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Не назначен')
    expect(wrapper.text()).not.toContain('Пётр')
  })

  it('рендерит статус-бейдж через TicketStatusBadge', () => {
    const wrapper = mount(TicketInfoCard, {
      props: { ticket: makeTicket({ status: 'resolved' }) },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-tag').exists()).toBe(true)
    expect(wrapper.text()).toContain('Решено')
  })

  it('форматирование дат присутствует и непусто', () => {
    const wrapper = mount(TicketInfoCard, {
      props: { ticket: makeTicket() },
      global: { plugins: [i18n] },
    })
    const values = wrapper.findAll('.ticket-info__value')
    // 5 строк: статус, источник, ответственный, создана, обновление
    expect(values).toHaveLength(5)
    for (const v of values) expect(v.text().trim().length).toBeGreaterThan(0)
  })
})
