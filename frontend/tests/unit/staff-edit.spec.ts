import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const sortableDestroy = vi.fn()
const sortableCreateCalls: Array<{ el: HTMLElement; options: unknown }> = []
class FakeSortable {
  destroy = sortableDestroy
}
vi.mock('sortablejs', () => ({
  default: {
    create: (el: HTMLElement, options: unknown) => {
      sortableCreateCalls.push({ el, options })
      return new FakeSortable()
    },
  },
}))

const mockFetchUsers = vi.fn()
const mockSaveStaffOrder = vi.fn()
vi.mock('../../src/api/users', () => ({
  fetchUsers: (...args: unknown[]) => mockFetchUsers(...args),
  saveStaffOrder: (...args: unknown[]) => mockSaveStaffOrder(...args),
}))

const mockMessageError = vi.fn()
const mockMessageSuccess = vi.fn()
const mockDialogWarning = vi.fn()
vi.mock('naive-ui', () => ({
  useMessage: () => ({
    error: mockMessageError,
    success: mockMessageSuccess,
    info: vi.fn(),
    warning: vi.fn(),
  }),
  useDialog: () => ({
    warning: mockDialogWarning,
  }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const mockInvalidateQueries = vi.fn()
vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}))

import { useStaffEdit } from '../../src/composables/useStaffEdit'

type EditApi = ReturnType<typeof useStaffEdit>

function makeUser(id: string, dept: string | null, hidden = false) {
  return {
    id,
    email: `${id}@x.test`,
    full_name: `User ${id}`,
    department: dept,
    position: 'pos',
    phone: null,
    role: 'reader' as const,
    avatar_url: null,
    current_status: 'working', current_status_until: null as const,
    lang: 'ru' as const,
    created_at: '',
    auth_source: 'local' as const,
    last_login_at: null,
    staff_hidden: hidden,
  }
}

function setupHost(): { api: EditApi; el: HTMLElement } {
  const editRootRef = ref<HTMLElement | null>(null)
  let api: EditApi | null = null

  const Host = defineComponent({
    setup() {
      api = useStaffEdit({ editRootRef })
      return () => h('div', { ref: (el) => (editRootRef.value = el as HTMLElement) })
    },
  })
  const wrapper = mount(Host)
  return { api: api as unknown as EditApi, el: wrapper.element as HTMLElement }
}

describe('useStaffEdit', () => {
  beforeEach(() => {
    mockFetchUsers.mockReset()
    mockSaveStaffOrder.mockReset()
    mockMessageError.mockReset()
    mockMessageSuccess.mockReset()
    mockDialogWarning.mockReset()
    mockInvalidateQueries.mockReset()
    sortableDestroy.mockReset()
    sortableCreateCalls.length = 0
  })

  it('enterEdit fetches users, builds groups in order, and creates sortable instances', async () => {
    mockFetchUsers.mockResolvedValue({
      items: [
        makeUser('a1', 'Sales'),
        makeUser('a2', 'Sales'),
        makeUser('b1', 'Engineering'),
        makeUser('c1', null),
      ],
      total: 4,
    })

    const { api, el } = setupHost()
    el.innerHTML =
      '<ul class="staff-edit__user-list" data-dept-idx="0"></ul>' +
      '<ul class="staff-edit__user-list" data-dept-idx="1"></ul>' +
      '<ul class="staff-edit__user-list" data-dept-idx="2"></ul>'

    await api.enterEdit()
    await nextTick()

    expect(api.editMode.value).toBe(true)
    expect(api.dirty.value).toBe(false)
    expect(api.editGroups.value.map((g) => g.department)).toEqual([
      'Sales',
      'Engineering',
      '',
    ])
    expect(api.editGroups.value[0].users.map((u) => u.id)).toEqual(['a1', 'a2'])
    expect(api.editGroups.value[1].users.map((u) => u.id)).toEqual(['b1'])
    expect(api.editGroups.value[2].users.map((u) => u.id)).toEqual(['c1'])
    expect(sortableCreateCalls.length).toBeGreaterThanOrEqual(1)
  })

  it('saveEdit submits departments in order, sort_order per group, and hidden user ids', async () => {
    mockFetchUsers.mockResolvedValue({
      items: [
        makeUser('a1', 'Sales'),
        makeUser('a2', 'Sales'),
        makeUser('b1', 'Engineering', true),
      ],
      total: 3,
    })
    mockSaveStaffOrder.mockResolvedValue({ departments: [], hidden_user_ids: [] })

    const { api } = setupHost()
    await api.enterEdit()
    await nextTick()

    const groups = api.editGroups.value
    const reordered = [groups[1], groups[0]]
    api.editGroups.value = reordered.map((g) => ({
      ...g,
      users: [...g.users],
    }))
    api.dirty.value = true

    await api.saveEdit()

    expect(mockSaveStaffOrder).toHaveBeenCalledTimes(1)
    const payload = mockSaveStaffOrder.mock.calls[0][0]
    expect(payload.departments).toEqual(['Engineering', 'Sales'])
    expect(payload.users).toEqual([
      { id: 'b1', sort_order: 0 },
      { id: 'a1', sort_order: 0 },
      { id: 'a2', sort_order: 1 },
    ])
    expect(payload.hidden_user_ids).toEqual(['b1'])
    expect(api.editMode.value).toBe(false)
    expect(api.dirty.value).toBe(false)
    expect(mockInvalidateQueries).toHaveBeenCalled()
  })

  it('toggleUserHidden flips staff_hidden and marks dirty', async () => {
    mockFetchUsers.mockResolvedValue({
      items: [makeUser('a1', 'Sales'), makeUser('a2', 'Sales', true)],
      total: 2,
    })

    const { api } = setupHost()
    await api.enterEdit()
    await nextTick()

    expect(api.dirty.value).toBe(false)
    api.toggleUserHidden('a1')
    expect(api.dirty.value).toBe(true)
    const a1 = api.editGroups.value[0].users.find((u) => u.id === 'a1')!
    const a2 = api.editGroups.value[0].users.find((u) => u.id === 'a2')!
    expect(a1.staff_hidden).toBe(true)
    expect(a2.staff_hidden).toBe(true)

    api.toggleUserHidden('a2')
    const a2b = api.editGroups.value[0].users.find((u) => u.id === 'a2')!
    expect(a2b.staff_hidden).toBe(false)
  })
})
