import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, params?: Record<string, unknown>) =>
      params ? `${k}|${JSON.stringify(params)}` : k,
  }),
}))

vi.mock('naive-ui', () => {
  const stubWithSlot = { template: '<div><slot /></div>' }
  return {
    NAvatar: { template: '<div class="n-avatar"><slot /></div>' },
    NButton: {
      props: ['quaternary', 'size'],
      emits: ['click'],
      template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    },
    NSpin: { template: '<div class="n-spin" />' },
  }
})

vi.mock('../../src/api/users', () => ({
  fetchUsers: vi.fn(),
}))

import { fetchUsers, type UserPublic } from '../../src/api/users'
import DepartmentColleagues from '../../src/components/profile/DepartmentColleagues.vue'

const RouterLinkStub = {
  props: ['to'],
  template: '<a class="router-link" :data-to="JSON.stringify(to)"><slot /></a>',
}

function makeUser(overrides: Partial<UserPublic> & { id: string; full_name: string }): UserPublic {
  return {
    id: overrides.id,
    email: `${overrides.id}@example.com`,
    full_name: overrides.full_name,
    department: overrides.department ?? 'IT',
    position: overrides.position ?? null,
    phone: null,
    role: 'reader',
    avatar_url: null,
    presence_status: 'office',
    lang: 'ru',
    created_at: '2024-01-01T00:00:00Z',
    auth_source: 'local',
    last_login_at: null,
    ...overrides,
  }
}

describe('DepartmentColleagues', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does not render when department is null', async () => {
    const wrapper = mount(DepartmentColleagues, {
      props: { department: null, excludeUserId: 'me' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    await flushPromises()
    expect(wrapper.find('section').exists()).toBe(false)
    expect(fetchUsers).not.toHaveBeenCalled()
  })

  it('fetches and renders colleagues, excluding current user', async () => {
    vi.mocked(fetchUsers).mockResolvedValueOnce({
      items: [
        makeUser({ id: 'me', full_name: 'Me Self' }),
        makeUser({ id: 'a', full_name: 'Anna A', position: 'Dev' }),
        makeUser({ id: 'b', full_name: 'Boris B' }),
      ],
      total: 3,
      limit: 200,
      offset: 0,
    })

    const wrapper = mount(DepartmentColleagues, {
      props: { department: 'IT', excludeUserId: 'me' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    await flushPromises()

    expect(fetchUsers).toHaveBeenCalledWith({ department: 'IT', page: 1, page_size: 200 })

    const items = wrapper.findAll('li.colleague-item')
    expect(items).toHaveLength(2)
    const text = wrapper.text()
    expect(text).toContain('Anna A')
    expect(text).toContain('Boris B')
    expect(text).not.toContain('Me Self')
  })

  it('shows empty state when no other colleagues remain', async () => {
    vi.mocked(fetchUsers).mockResolvedValueOnce({
      items: [makeUser({ id: 'me', full_name: 'Me Self' })],
      total: 1,
      limit: 200,
      offset: 0,
    })

    const wrapper = mount(DepartmentColleagues, {
      props: { department: 'IT', excludeUserId: 'me' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    await flushPromises()

    expect(wrapper.find('.colleagues-empty').exists()).toBe(true)
    expect(wrapper.findAll('li.colleague-item')).toHaveLength(0)
  })

  it('limits to 10 colleagues initially and reveals all after click', async () => {
    const items = Array.from({ length: 15 }, (_, i) =>
      makeUser({ id: `u${i}`, full_name: `User ${i}` })
    )
    vi.mocked(fetchUsers).mockResolvedValueOnce({
      items,
      total: 15,
      limit: 200,
      offset: 0,
    })

    const wrapper = mount(DepartmentColleagues, {
      props: { department: 'IT', excludeUserId: 'me' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    await flushPromises()

    expect(wrapper.findAll('li.colleague-item')).toHaveLength(10)

    const button = wrapper.find('button.n-button')
    expect(button.exists()).toBe(true)
    await button.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('li.colleague-item')).toHaveLength(15)
  })

  it('handles API errors gracefully (empty state)', async () => {
    vi.mocked(fetchUsers).mockRejectedValueOnce(new Error('boom'))

    const wrapper = mount(DepartmentColleagues, {
      props: { department: 'IT', excludeUserId: 'me' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    await flushPromises()

    expect(wrapper.find('.colleagues-empty').exists()).toBe(true)
  })
})
