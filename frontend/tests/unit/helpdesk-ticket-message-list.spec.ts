import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

import TicketMessageList from '../../src/components/helpdesk/TicketMessageList.vue'
import type { HelpdeskMessage } from '../../src/api/helpdesk'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    ru: {
      helpdesk: {
        internalNote: 'Внутренняя заметка',
        sources: { email: 'Email' },
        ccLabel: 'Копия',
      },
    },
    en: {
      helpdesk: {
        internalNote: 'Internal note',
        sources: { email: 'Email' },
        ccLabel: 'Cc',
      },
    },
  },
})

const baseMsg = {
  id: 'm1',
  visibility: 'public' as const,
  source: 'web' as const,
  author_email: 'client@company.local',
  author_name: 'Иван Петров',
  author_user_id: null,
  body_text: 'Привет',
  body_html: null,
  attachments: [],
  cc: [],
  created_at: '2026-07-01T10:00:00Z',
}

function makeMsg(overrides: Partial<HelpdeskMessage> = {}): HelpdeskMessage {
  return { ...baseMsg, ...overrides } as HelpdeskMessage
}

function mountList(messages: HelpdeskMessage[], agentMode = false) {
  return mount(TicketMessageList, {
    props: { messages, agentMode },
    global: { plugins: [i18n] },
  })
}

describe('TicketMessageList — chat UI', () => {
  beforeEach(() => {
    // DOMPurify в jsdom: отключаем CSP-зависимости.
    process.env.NODE_ENV = 'test'
  })

  it('renders one chat row per message', () => {
    const wrapper = mountList([
      makeMsg({ id: 'm1', direction: 'inbound' }),
      makeMsg({ id: 'm2', direction: 'outbound' }),
    ])
    expect(wrapper.findAll('.chat-row')).toHaveLength(2)
  })

  it('aligns inbound left, outbound right', () => {
    const wrapper = mountList([
      makeMsg({ id: 'm1', direction: 'inbound' }),
      makeMsg({ id: 'm2', direction: 'outbound' }),
    ])
    const rows = wrapper.findAll('.chat-row')
    expect(rows[0].classes()).toContain('chat-row--in')
    expect(rows[1].classes()).toContain('chat-row--out')
  })

  it('shows initials in avatar', () => {
    const wrapper = mountList([makeMsg({ author_name: 'Анна Смирнова' })])
    const avatar = wrapper.find('.chat-row__avatar')
    expect(avatar.text()).toBe('АС')
  })

  it('falls back to email local-part for initials when no name', () => {
    const wrapper = mountList([
      makeMsg({ author_name: null, author_email: 'guest@x.test' }),
    ])
    expect(wrapper.find('.chat-row__avatar').text()).toBe('G')
  })

  it('renders plain body when no html', () => {
    const wrapper = mountList([makeMsg({ body_text: 'Простой текст', body_html: null })])
    const body = wrapper.find('.chat-bubble__body--plain')
    expect(body.exists()).toBe(true)
    expect(body.text()).toBe('Простой текст')
  })

  it('renders sanitized html body', () => {
    const wrapper = mountList([
      makeMsg({ body_html: '<p>HTML <strong>тело</strong></p>' }),
    ])
    const body = wrapper.find('.chat-bubble__body')
    expect(body.html()).toContain('<strong>тело</strong>')
  })

  it('strips script tags from html body', () => {
    const wrapper = mountList([
      makeMsg({ body_html: '<p>текст</p><script>alert(1)</script>' }),
    ])
    expect(wrapper.html()).not.toContain('<script>')
    expect(wrapper.find('.chat-bubble__body').text()).toContain('текст')
  })

  it('shows internal-note tag for internal visibility', () => {
    const wrapper = mountList([
      makeMsg({ visibility: 'internal', direction: 'outbound' }),
    ])
    expect(wrapper.find('.chat-bubble--internal').exists()).toBe(true)
    expect(wrapper.find('.chat-bubble__note').exists()).toBe(true)
  })

  it('shows email source tag for email messages', () => {
    const wrapper = mountList([makeMsg({ source: 'email' })])
    expect(wrapper.find('.chat-bubble__src').exists()).toBe(true)
  })

  it('shows author email only in agent mode', () => {
    const agent = mountList([makeMsg()], true)
    const user = mountList([makeMsg()], false)
    expect(agent.find('.chat-bubble__email').exists()).toBe(true)
    expect(user.find('.chat-bubble__email').exists()).toBe(false)
  })

  it('renders attachments as download links', () => {
    const wrapper = mountList([
      makeMsg({
        attachments: [
          {
            id: 'att1',
            original_name: 'doc.pdf',
            size_bytes: 2048,
            content_type: 'application/pdf',
          },
        ],
      }),
    ])
    const link = wrapper.find('.chat-bubble__attachment')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toContain('att1')
    expect(link.text()).toContain('doc.pdf')
  })

  it('uses author name when present, email otherwise', () => {
    const w1 = mountList([makeMsg({ author_name: 'Имя', author_email: 'e@x.test' })])
    expect(w1.find('.chat-bubble__author').text()).toBe('Имя')

    const w2 = mountList([makeMsg({ author_name: null, author_email: 'e@x.test' })])
    expect(w2.find('.chat-bubble__author').text()).toBe('e@x.test')
  })

  it('assigns deterministic avatar color from email', () => {
    const w1 = mountList([makeMsg({ author_email: 'a@x.test' })])
    const w2 = mountList([makeMsg({ author_email: 'a@x.test' })])
    const c1 = w1.find('.chat-row__avatar').attributes('style') || ''
    const c2 = w2.find('.chat-row__avatar').attributes('style') || ''
    expect(c1).toContain('background')
    expect(c1).toBe(c2) // детерминированно
  })

  // ── Cc-бейдж (миграция 083) ────────────────────────────────────────────────
  it('shows cc badge in agent mode when message has cc', () => {
    const wrapper = mountList(
      [
        makeMsg({
          direction: 'outbound',
          cc: [
            { email: 'a@x.local', name: 'Иван' },
            { email: 'b@y.local', name: null },
          ],
        }),
      ],
      true,
    )
    const cc = wrapper.find('.chat-bubble__cc')
    expect(cc.exists()).toBe(true)
    // Имя первого, email второго (нет имени → fallback на email).
    expect(cc.text()).toContain('Иван')
    expect(cc.text()).toContain('b@y.local')
  })

  it('hides cc badge when cc is empty', () => {
    const wrapper = mountList([makeMsg({ cc: [] })], true)
    expect(wrapper.find('.chat-bubble__cc').exists()).toBe(false)
  })

  it('hides cc badge in requester (non-agent) mode even with cc', () => {
    // PII-минимизация: заявителю свои же Cc видеть ни к чему.
    const wrapper = mountList(
      [makeMsg({ cc: [{ email: 'a@x.local', name: null }] })],
      false,
    )
    expect(wrapper.find('.chat-bubble__cc').exists()).toBe(false)
  })
})
