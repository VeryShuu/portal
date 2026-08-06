import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

type SortableCall = { el: HTMLElement; options: any }

const sortableDestroy = vi.fn()
const sortableCreateCalls: SortableCall[] = []
class FakeSortable {
  destroy = sortableDestroy
}

vi.mock('sortablejs', () => ({
  default: {
    create: (el: HTMLElement, options: any) => {
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
  useMessage: () => ({ success: mockMessageSuccess, error: mockMessageError, warning: vi.fn(), info: vi.fn() }),
  useDialog: () => ({ warning: (...args: unknown[]) => mockDialogWarning(...args) }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const mockInvalidateQueries = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ invalidateQueries: (...args: unknown[]) => mockInvalidateQueries(...args) }),
}))

vi.mock('../../src/api/index', () => ({ api: vi.fn() }))

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

async function setupHost(withRoot = true): Promise<{ api: EditApi; el: HTMLElement; router: Router }> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()

  const editRootRef = ref<HTMLElement | null>(null)
  let api: EditApi | null = null

  const Host = defineComponent({
    setup() {
      api = useStaffEdit({ editRootRef })
      return () =>
        withRoot
          ? h('div', { ref: (el) => (editRootRef.value = el as HTMLElement) })
          : h('span', 'no-root')
    },
  })

  const wrapper = mount(Host, { global: { plugins: [router] } })
  return { api: api as unknown as EditApi, el: wrapper.element as HTMLElement, router }
}

describe('cov-media useStaffEdit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sortableCreateCalls.length = 0
  })

  it('buildGroupsFromList keeps first-seen department order and trims names', async () => {
    const { api } = await setupHost()
    const groups = api.buildGroupsFromList([
      makeUser('u1', ' Sales '),
      makeUser('u2', 'Sales'),
      makeUser('u3', null),
      makeUser('u4', 'IT'),
    ])

    expect(groups.map((g) => g.department)).toEqual(['Sales', '', 'IT'])
    expect(groups[0].users.map((u) => u.id)).toEqual(['u1', 'u2'])
  })

  it('bindSortables returns early when root is not available', async () => {
    const { api } = await setupHost(false)

    api.bindSortables()

    expect(sortableCreateCalls).toHaveLength(0)
  })

  it('enterEdit handles loading guard and fetch error branch', async () => {
    let resolveFetch: ((v: any) => void) | null = null
    mockFetchUsers.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve
        }),
    )

    const { api } = await setupHost()
    const p1 = api.enterEdit()
    const p2 = api.enterEdit()

    expect(api.entering.value).toBe(true)
    expect(mockFetchUsers).toHaveBeenCalledTimes(1)

    resolveFetch?.({ items: [makeUser('a1', 'A')], total: 1 })
    await p1
    await p2

    mockFetchUsers.mockRejectedValueOnce(new Error('load-fail'))
    api.editMode.value = false
    await api.enterEdit()

    expect(mockMessageError).toHaveBeenCalledWith('staff.edit.loadError')
    expect(api.entering.value).toBe(false)
  })

  it('cancelEdit finalizes immediately when not dirty and via dialog when dirty', async () => {
    mockFetchUsers.mockResolvedValueOnce({
      items: [makeUser('a1', 'Sales')],
      total: 1,
    })

    const { api } = await setupHost()
    await api.enterEdit()

    const createdCount = sortableCreateCalls.length
    api.cancelEdit()
    expect(api.editMode.value).toBe(false)
    expect(api.dirty.value).toBe(false)
    expect(api.editGroups.value).toEqual([])
    expect(sortableDestroy).toHaveBeenCalledTimes(createdCount)

    mockFetchUsers.mockResolvedValueOnce({
      items: [makeUser('b1', 'Sales')],
      total: 1,
    })
    await api.enterEdit()
    api.dirty.value = true

    api.cancelEdit()
    expect(mockDialogWarning).toHaveBeenCalledTimes(1)

    const arg = mockDialogWarning.mock.calls[0][0]
    expect(typeof arg.onPositiveClick).toBe('function')

    arg.onPositiveClick()
    expect(api.editMode.value).toBe(false)
    expect(api.editGroups.value).toEqual([])
  })

  it('department drag onEnd handles guard and reorder branches', async () => {
    mockFetchUsers.mockResolvedValueOnce({
      items: [makeUser('u1', 'A'), makeUser('u2', 'B')],
      total: 2,
    })

    const { api, el } = await setupHost()
    el.innerHTML =
      '<div class="staff-edit__group">A</div>' +
      '<div class="staff-edit__group">B</div>' +
      '<ul class="staff-edit__user-list" data-dept-idx="0"></ul>' +
      '<ul class="staff-edit__user-list" data-dept-idx="1"></ul>'

    await api.enterEdit()
    await nextTick()

    const deptOptions = sortableCreateCalls[0].options
    deptOptions.onStart()
    expect(el.classList.contains('is-dragging-dept')).toBe(true)

    deptOptions.onEnd({ oldIndex: 0, newIndex: 0, item: el.children[0], from: el })
    expect(api.dirty.value).toBe(false)

    deptOptions.onEnd({ oldIndex: null, newIndex: 1, item: el.children[0], from: el })
    expect(api.dirty.value).toBe(false)

    deptOptions.onEnd({ oldIndex: 0, newIndex: 1, item: el.children[0], from: el })
    expect(api.editGroups.value.map((g) => g.department)).toEqual(['B', 'A'])
    expect(api.dirty.value).toBe(true)
    expect(el.classList.contains('is-dragging-dept')).toBe(false)
  })

  it('user drag onEnd covers invalid indices, no-op, move inside and across groups', async () => {
    mockFetchUsers.mockResolvedValueOnce({
      items: [makeUser('u1', 'A'), makeUser('u2', 'A'), makeUser('u3', 'B')],
      total: 3,
    })

    const { api, el } = await setupHost()
    el.innerHTML =
      '<div class="staff-edit__group">A</div>' +
      '<div class="staff-edit__group">B</div>' +
      '<ul class="staff-edit__user-list" data-dept-idx="0"><li class="staff-edit__user">u1</li><li class="staff-edit__user">u2</li></ul>' +
      '<ul class="staff-edit__user-list" data-dept-idx="1"><li class="staff-edit__user">u3</li></ul>'

    await api.enterEdit()
    await nextTick()

    const userSortable1 = sortableCreateCalls[1].options
    const lists = el.querySelectorAll<HTMLElement>('.staff-edit__user-list')
    const from = lists[0]
    const to = lists[1]
    const item = document.createElement('li')

    userSortable1.onEnd({ from, to, item, oldIndex: null, newIndex: 0 })
    expect(api.dirty.value).toBe(false)

    userSortable1.onEnd({ from, to: from, item, oldIndex: 0, newIndex: 0 })
    expect(api.dirty.value).toBe(false)

    const invalidFrom = document.createElement('ul')
    invalidFrom.setAttribute('data-dept-idx', 'x')
    userSortable1.onEnd({
      from: invalidFrom,
      to,
      item,
      oldIndex: 0,
      newIndex: 0,
    })
    expect(api.dirty.value).toBe(false)

    userSortable1.onEnd({ from, to: from, item, oldIndex: 0, newIndex: 1 })
    expect(api.editGroups.value[0].users.map((u) => u.id)).toEqual(['u2', 'u1'])
    expect(api.dirty.value).toBe(true)

    api.dirty.value = false
    const crossItem = document.createElement('li')
    to.appendChild(crossItem)
    userSortable1.onEnd({ from, to, item: crossItem, oldIndex: 0, newIndex: 1 })

    expect(api.editGroups.value[1].users.some((u) => u.id === 'u2')).toBe(true)
    const moved = api.editGroups.value[1].users.find((u) => u.id === 'u2')
    expect(moved?.department).toBe('B')
    expect(api.dirty.value).toBe(true)
  })

  it('toggleUserHidden flips a user and saveEdit covers guard, success and error', async () => {
    mockFetchUsers.mockResolvedValueOnce({
      items: [makeUser('a1', 'A'), makeUser('a2', null, true)],
      total: 2,
    })

    const { api } = await setupHost()
    await api.enterEdit()

    api.toggleUserHidden('a1')
    expect(api.editGroups.value[0].users[0].staff_hidden).toBe(true)
    expect(api.dirty.value).toBe(true)

    api.saving.value = true
    await api.saveEdit()
    expect(mockSaveStaffOrder).not.toHaveBeenCalled()

    api.saving.value = false
    mockSaveStaffOrder.mockResolvedValueOnce({})
    await api.saveEdit()

    expect(mockSaveStaffOrder).toHaveBeenCalledTimes(1)
    const payload = mockSaveStaffOrder.mock.calls[0][0]
    expect(payload.departments).toEqual(['A'])
    expect(payload.hidden_user_ids.sort()).toEqual(['a1', 'a2'])
    expect(mockInvalidateQueries).toHaveBeenCalled()
    expect(api.editMode.value).toBe(false)
    expect(api.saving.value).toBe(false)

    mockFetchUsers.mockResolvedValueOnce({
      items: [makeUser('x1', 'X')],
      total: 1,
    })
    await api.enterEdit()
    mockSaveStaffOrder.mockRejectedValueOnce(new Error('fail'))

    await api.saveEdit()

    expect(mockMessageError).toHaveBeenCalledWith('staff.edit.saveError')
    expect(api.saving.value).toBe(false)
  })
})
