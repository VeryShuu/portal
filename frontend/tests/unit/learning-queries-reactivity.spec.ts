import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

/**
 * Регрессия ревью 2026-08-28: learning-запросы обязаны оставаться реактивными
 * к ref-параметрам. Прежняя реализация делала `unref(courseId)` один раз при
 * создании опций — queryKey и enabled «замораживались» (обычно со значением
 * null/false на момент маунта drawer'а), и карточки курса/теста никогда
 * не загружались.
 */

const apiMocks = {
  fetchAdminCourse: vi.fn(),
  fetchAdminProgress: vi.fn(),
  fetchCourseProgress: vi.fn(),
  fetchTestConfig: vi.fn(),
  fetchLearningAccounts: vi.fn(),
}

vi.mock('../../src/api/learning', () => apiMocks)

describe('learning queries: реактивность ключей и enabled', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    for (const fn of Object.values(apiMocks)) {
      fn.mockReset()
      fn.mockResolvedValue(undefined)
    }
  })

  function mountWith(setup: () => void) {
    const Host = defineComponent({ setup, template: '<div />' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    mount(Host, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
  }

  it('useAdminCourseQuery: null → id запускает загрузку', async () => {
    const { useAdminCourseQuery } = await import('../../src/queries/learning')
    const courseId = ref<string | null>(null)
    mountWith(() => {
      useAdminCourseQuery(courseId)
    })
    await flushPromises()
    expect(apiMocks.fetchAdminCourse).not.toHaveBeenCalled()

    courseId.value = 'course-1'
    await flushPromises()
    expect(apiMocks.fetchAdminCourse).toHaveBeenCalledWith('course-1')
  })

  it('useAdminCourseQuery: смена id → запрос по новому ключу', async () => {
    const { useAdminCourseQuery } = await import('../../src/queries/learning')
    const courseId = ref<string | null>('a')
    mountWith(() => {
      useAdminCourseQuery(courseId)
    })
    await flushPromises()
    courseId.value = 'b'
    await flushPromises()
    expect(apiMocks.fetchAdminCourse).toHaveBeenCalledWith('b')
  })

  it('useAdminTestQuery: null → id запускает загрузку', async () => {
    const { useAdminTestQuery } = await import('../../src/queries/learning')
    const itemId = ref<string | null>(null)
    mountWith(() => {
      useAdminTestQuery(itemId)
    })
    await flushPromises()
    expect(apiMocks.fetchTestConfig).not.toHaveBeenCalled()

    itemId.value = 'item-9'
    await flushPromises()
    expect(apiMocks.fetchTestConfig).toHaveBeenCalledWith('item-9')
  })

  it('useAdminAccountsQuery: enabled ref false → true запускает загрузку', async () => {
    const { useAdminAccountsQuery } = await import('../../src/queries/learning')
    const enabled = ref(false)
    mountWith(() => {
      useAdminAccountsQuery({ limit: 100, offset: 0 }, enabled)
    })
    await flushPromises()
    expect(apiMocks.fetchLearningAccounts).not.toHaveBeenCalled()

    enabled.value = true
    await flushPromises()
    expect(apiMocks.fetchLearningAccounts).toHaveBeenCalled()
  })
})
