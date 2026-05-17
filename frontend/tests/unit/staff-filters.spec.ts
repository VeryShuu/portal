import { describe, it, expect, beforeEach } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { useStaffFilters } from '../../src/composables/useStaffFilters'

type FiltersApi = ReturnType<typeof useStaffFilters>

async function setupHost(initialPath = '/staff'): Promise<{
  api: FiltersApi
  router: Router
}> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/staff', component: { template: '<div/>' } }],
  })
  await router.push(initialPath)
  await router.isReady()

  let api: FiltersApi | null = null
  const Host = defineComponent({
    setup() {
      api = useStaffFilters()
      return () => h('div')
    },
  })
  mount(Host, { global: { plugins: [router] } })
  return { api: api as unknown as FiltersApi, router }
}

function wait(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

describe('useStaffFilters', () => {
  beforeEach(() => {
    // noop
  })

  it('debounces search input and resets page to 1', async () => {
    const { api } = await setupHost('/staff?page=3')
    expect(api.page.value).toBe(3)

    api.searchInput.value = 'ivan'
    api.onSearchInput()
    expect(api.q.value).toBe('')

    await wait(350)
    await nextTick()

    expect(api.q.value).toBe('ivan')
    expect(api.page.value).toBe(1)
  })

  it('resetFilters clears all filter values', async () => {
    const { api } = await setupHost(
      '/staff?q=foo&department=Sales&office=Moscow&page=2',
    )
    expect(api.q.value).toBe('foo')
    expect(api.departmentFilter.value).toBe('Sales')
    expect(api.officeFilter.value).toBe('Moscow')
    expect(api.page.value).toBe(2)
    expect(api.hasActiveFilters.value).toBe(true)

    api.resetFilters()

    expect(api.searchInput.value).toBe('')
    expect(api.q.value).toBe('')
    expect(api.departmentFilter.value).toBe(null)
    expect(api.officeFilter.value).toBe(null)
    expect(api.page.value).toBe(1)
    expect(api.hasActiveFilters.value).toBe(false)
  })

  it('initializes state from URL query', async () => {
    const { api } = await setupHost('/staff?q=hello&department=IT&page=5')
    expect(api.searchInput.value).toBe('hello')
    expect(api.q.value).toBe('hello')
    expect(api.departmentFilter.value).toBe('IT')
    expect(api.page.value).toBe(5)
  })
})
