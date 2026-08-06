import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, params?: Record<string, unknown>) =>
      params ? `${k}|${JSON.stringify(params)}` : k,
    locale: { value: 'ru' },
  }),
}))

vi.mock('../../src/utils/formatDate', () => ({
  formatDateShort: (iso: string) => `FMT(${iso})`,
}))

vi.mock('naive-ui', () => ({
  NAvatar: {
    props: ['size', 'src', 'round'],
    template: '<div class="n-avatar" :data-size="size" :data-src="src"><slot /></div>',
  },
}))

import UserAvatar from '../../src/components/UserAvatar.vue'

describe('UserAvatar', () => {
  it('renders initials when no avatar_url', () => {
    const wrapper = mount(UserAvatar, {
      props: { user: { full_name: 'Иванов Иван', avatar_url: null }, size: 40 },
    })
    expect(wrapper.text()).toContain('ИИ')
  })

  it('renders avatar img when avatar_url present', () => {
    const wrapper = mount(UserAvatar, {
      props: { user: { full_name: 'Иванов Иван', avatar_url: 'http://x/a.png' }, size: 40 },
    })
    expect(wrapper.find('.n-avatar').attributes('data-src')).toBe('http://x/a.png')
    // initials не рендерятся (есть src)
    expect(wrapper.text()).not.toContain('ИИ')
  })

  it('draws vacation ring class for non-working status', () => {
    const wrapper = mount(UserAvatar, {
      props: {
        user: { full_name: 'A B', current_status: 'vacation', current_status_until: null },
        size: 48,
      },
    })
    expect(wrapper.classes()).toContain('user-avatar--vacation')
  })

  it('draws sick ring class', () => {
    const wrapper = mount(UserAvatar, {
      props: { user: { full_name: 'A B', current_status: 'sick' }, size: 48 },
    })
    expect(wrapper.classes()).toContain('user-avatar--sick')
  })

  it('draws business_trip ring class', () => {
    const wrapper = mount(UserAvatar, {
      props: { user: { full_name: 'A B', current_status: 'business_trip' }, size: 48 },
    })
    expect(wrapper.classes()).toContain('user-avatar--business_trip')
  })

  it('no ring class for working by default', () => {
    const wrapper = mount(UserAvatar, {
      props: { user: { full_name: 'A B', current_status: 'working' }, size: 48 },
    })
    expect(wrapper.classes()).not.toContain('user-avatar--working')
  })

  it('shows working ring when showWorkingRing prop is true', () => {
    const wrapper = mount(UserAvatar, {
      props: {
        user: { full_name: 'A B', current_status: 'working' },
        size: 48,
        showWorkingRing: true,
      },
    })
    expect(wrapper.classes()).toContain('user-avatar--working')
  })

  it('no ring when current_status absent (e.g. helpdesk message)', () => {
    const wrapper = mount(UserAvatar, {
      props: { user: { full_name: 'A B' }, size: 48 },
    })
    expect(wrapper.classes('user-avatar')).toBe(true)
    expect(wrapper.classes().filter((c) => c.startsWith('user-avatar--'))).toEqual([])
  })

  it('tooltip includes category label and until date', () => {
    const wrapper = mount(UserAvatar, {
      props: {
        user: {
          full_name: 'A B',
          current_status: 'vacation',
          current_status_until: '2026-08-15',
        },
        size: 48,
      },
    })
    const title = wrapper.attributes('title')
    expect(title).toContain('users.presence.vacation')
    expect(title).toContain('users.presence.until')
    expect(title).toContain('FMT(2026-08-15)')
  })

  it('tooltip empty for working without ring', () => {
    const wrapper = mount(UserAvatar, {
      props: { user: { full_name: 'A B', current_status: 'working' }, size: 48 },
    })
    expect(wrapper.attributes('title')).toBe('')
  })
})
