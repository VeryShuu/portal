import { describe, it, expect, beforeEach, vi } from 'vitest'
import { reactive, nextTick } from 'vue'

// A single reactive route object so reads inside useManageDrawer's computed
// always see the latest query without needing to call useRoute() again.
const mockRoute = reactive<{ query: Record<string, any> }>({ query: {} })
const mockRouterReplace = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({ replace: mockRouterReplace }),
}))

import { useManageDrawer } from '../../src/composables/useManageDrawer'

describe('useManageDrawer (src/composables)', () => {
  beforeEach(() => {
    mockRouterReplace.mockClear()
    for (const k of Object.keys(mockRoute.query)) delete mockRoute.query[k]
  })

  it('active is null when query.manage is absent', async () => {
    const { active } = useManageDrawer()
    expect(active.value).toBe(null)
  })

  it('active is null when query.manage is non-string', async () => {
    mockRoute.query.manage = 42
    await nextTick()
    const { active } = useManageDrawer()
    expect(active.value).toBe(null)
  })

  it('active returns the string manage value when validKeys is not constrained', async () => {
    mockRoute.query.manage = 'users'
    await nextTick()
    const { active } = useManageDrawer()
    expect(active.value).toBe('users')
  })

  it('active filters out values not in validKeys when provided', async () => {
    mockRoute.query.manage = 'unknown'
    await nextTick()
    const { active } = useManageDrawer(['users', 'links'] as const)
    expect(active.value).toBe(null)

    mockRoute.query.manage = 'links'
    await nextTick()
    expect(active.value).toBe('links')
  })

  it('open() short-circuits when current manage equals the key', async () => {
    mockRoute.query.manage = 'users'
    await nextTick()
    const { open } = useManageDrawer()

    open('users')
    expect(mockRouterReplace).not.toHaveBeenCalled()
  })

  it('open() replaces the route merging manage with existing query', async () => {
    mockRoute.query.foo = 'bar'
    await nextTick()
    const { open } = useManageDrawer()

    open('users')
    expect(mockRouterReplace).toHaveBeenCalledWith({ query: { foo: 'bar', manage: 'users' } })
  })

  it('close() short-circuits when manage is already absent', async () => {
    const { close } = useManageDrawer()
    close()
    expect(mockRouterReplace).not.toHaveBeenCalled()
  })

  it('close() removes manage from query and replaces route', async () => {
    mockRoute.query.manage = 'users'
    mockRoute.query.foo = 'bar'
    await nextTick()
    const { close } = useManageDrawer()

    close()
    expect(mockRouterReplace).toHaveBeenCalledTimes(1)
    const arg = mockRouterReplace.mock.calls[0][0]
    expect(arg.query.manage).toBeUndefined()
    expect(arg.query.foo).toBe('bar')
  })

  it('is() returns true only for the active key', async () => {
    mockRoute.query.manage = 'users'
    await nextTick()
    const { is } = useManageDrawer()
    expect(is('users')).toBe(true)
    expect(is('links')).toBe(false)
  })
})
