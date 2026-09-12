import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

/**
 * Контракты queries/learning.ts: каждая мутация маппится в ровно один вызов
 * api/learning с теми же аргументами; каждый запрос дергает свой endpoint.
 * api/learning замокан — проверяем только прокидывание.
 */

const apiMocks = {
  fetchMyCourses: vi.fn(),
  fetchAdminCourses: vi.fn(),
  fetchAdminCourse: vi.fn(),
  fetchCourseProgress: vi.fn(),
  fetchTestConfig: vi.fn(),
  fetchLearningAccounts: vi.fn(),
  fetchLearningAdmins: vi.fn(),
  assignLearningAdmin: vi.fn(),
  revokeLearningAdmin: vi.fn(),
  createCourse: vi.fn(),
  updateCourse: vi.fn(),
  setCoursePublished: vi.fn(),
  deleteCourse: vi.fn(),
  addCourseItem: vi.fn(),
  updateCourseItem: vi.fn(),
  deleteCourseItem: vi.fn(),
  reorderCourseItems: vi.fn(),
  uploadMaterialFile: vi.fn(),
  uploadCourseCover: vi.fn(),
  deleteCourseCover: vi.fn(),
  updateTestSettings: vi.fn(),
  addQuestion: vi.fn(),
  updateQuestion: vi.fn(),
  deleteQuestion: vi.fn(),
  enrollParticipant: vi.fn(),
  unenrollParticipant: vi.fn(),
  fetchParticipantItems: vi.fn(),
  resetParticipantAttempts: vi.fn(),
  createLearningAccount: vi.fn(),
  importLearningAccounts: vi.fn(),
  bulkEnrollParticipants: vi.fn(),
  previewQuestionsImport: vi.fn(),
  importQuestions: vi.fn(),
  issueLearningAccountLoginCode: vi.fn(),
  blockLearningAccount: vi.fn(),
  unblockLearningAccount: vi.fn(),
  fetchCategories: vi.fn(),
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
  reorderCategories: vi.fn(),
}

vi.mock('../../src/api/learning', () => apiMocks)

const FILE = new File(['x'], 'a.pdf', { type: 'application/pdf' })

const MUTATION_CASES: Array<{
  use: string
  payload: unknown
  apiFn: keyof typeof apiMocks
  args: unknown[]
  /** preview-мутации ничего не меняют — кэш не инвалидируют */
  noInvalidate?: boolean
}> = [
  { use: 'useCreateCourseMutation', payload: { title: 'T' }, apiFn: 'createCourse', args: [{ title: 'T' }] },
  { use: 'useUpdateCourseMutation', payload: { courseId: 'c1', body: { title: 'N' } }, apiFn: 'updateCourse', args: ['c1', { title: 'N' }] },
  { use: 'useSetCoursePublishedMutation', payload: { courseId: 'c1', published: true }, apiFn: 'setCoursePublished', args: ['c1', true] },
  { use: 'useSetCoursePublishedMutation', payload: { courseId: 'c1', published: false }, apiFn: 'setCoursePublished', args: ['c1', false] },
  { use: 'useDeleteCourseMutation', payload: 'c1', apiFn: 'deleteCourse', args: ['c1'] },
  { use: 'useAddItemMutation', payload: { courseId: 'c1', body: { type: 'test', title: 'Q' } }, apiFn: 'addCourseItem', args: ['c1', { type: 'test', title: 'Q' }] },
  { use: 'useUpdateItemMutation', payload: { courseId: 'c1', itemId: 'i1', body: { title: 'N' } }, apiFn: 'updateCourseItem', args: ['i1', { title: 'N' }] },
  { use: 'useDeleteItemMutation', payload: { courseId: 'c1', itemId: 'i1' }, apiFn: 'deleteCourseItem', args: ['i1'] },
  { use: 'useReorderItemsMutation', payload: { courseId: 'c1', orderedIds: ['b', 'a'] }, apiFn: 'reorderCourseItems', args: ['c1', ['b', 'a']] },
  { use: 'useUploadMaterialMutation', payload: { courseId: 'c1', itemId: 'i1', file: FILE }, apiFn: 'uploadMaterialFile', args: ['i1', FILE] },
  { use: 'useUploadCoverMutation', payload: { courseId: 'c1', file: FILE }, apiFn: 'uploadCourseCover', args: ['c1', FILE] },
  { use: 'useDeleteCoverMutation', payload: { courseId: 'c1' }, apiFn: 'deleteCourseCover', args: ['c1'] },
  { use: 'useUpdateTestSettingsMutation', payload: { itemId: 'i1', body: { pass_score: 50 } }, apiFn: 'updateTestSettings', args: ['i1', { pass_score: 50 }] },
  { use: 'useAddQuestionMutation', payload: { itemId: 'i1', body: { text: 'Q' } }, apiFn: 'addQuestion', args: ['i1', { text: 'Q' }] },
  { use: 'useUpdateQuestionMutation', payload: { itemId: 'i1', questionId: 'q1', body: { text: 'Q' } }, apiFn: 'updateQuestion', args: ['i1', 'q1', { text: 'Q' }] },
  { use: 'useDeleteQuestionMutation', payload: { itemId: 'i1', questionId: 'q1' }, apiFn: 'deleteQuestion', args: ['i1', 'q1'] },
  { use: 'useEnrollParticipantMutation', payload: { courseId: 'c1', body: { user_id: 'u1' } }, apiFn: 'enrollParticipant', args: ['c1', { user_id: 'u1' }] },
  { use: 'useUnenrollParticipantMutation', payload: { courseId: 'c1', participantId: 'p1' }, apiFn: 'unenrollParticipant', args: ['c1', 'p1'] },
  { use: 'useResetParticipantAttemptsMutation', payload: { courseId: 'c1', participantId: 'p1', itemId: 'i1' }, apiFn: 'resetParticipantAttempts', args: ['c1', 'p1', 'i1'] },
  { use: 'useBulkEnrollMutation', payload: { courseId: 'c1', userIds: ['u1', 'u2'] }, apiFn: 'bulkEnrollParticipants', args: ['c1', ['u1', 'u2']] },
  { use: 'useCreateAccountMutation', payload: { email: 'a@b', full_name: 'A' }, apiFn: 'createLearningAccount', args: [{ email: 'a@b', full_name: 'A' }] },
  { use: 'useImportAccountsMutation', payload: FILE, apiFn: 'importLearningAccounts', args: [FILE] },
  { use: 'usePreviewQuestionsImportMutation', payload: { itemId: 'i1', file: FILE }, apiFn: 'previewQuestionsImport', args: ['i1', FILE], noInvalidate: true },
  { use: 'useImportQuestionsMutation', payload: { itemId: 'i1', file: FILE }, apiFn: 'importQuestions', args: ['i1', FILE] },
  { use: 'useIssueAccountLoginCodeMutation', payload: 'a1', apiFn: 'issueLearningAccountLoginCode', args: ['a1'] },
  { use: 'useBlockAccountMutation', payload: { accountId: 'a1', blocked: true }, apiFn: 'blockLearningAccount', args: ['a1'] },
  { use: 'useBlockAccountMutation', payload: { accountId: 'a1', blocked: false }, apiFn: 'unblockLearningAccount', args: ['a1'] },
  { use: 'useAssignMethodistMutation', payload: 'u9', apiFn: 'assignLearningAdmin', args: [{ user_id: 'u9' }] },
  { use: 'useRevokeMethodistMutation', payload: 'u9', apiFn: 'revokeLearningAdmin', args: ['u9'] },
  { use: 'useCreateCategoryMutation', payload: { title: 'К' }, apiFn: 'createCategory', args: [{ title: 'К' }] },
  { use: 'useUpdateCategoryMutation', payload: { id: 'k1', body: { title: 'Н' } }, apiFn: 'updateCategory', args: ['k1', { title: 'Н' }] },
  { use: 'useDeleteCategoryMutation', payload: 'k1', apiFn: 'deleteCategory', args: ['k1'] },
  { use: 'useReorderCategoriesMutation', payload: { ordered_ids: ['b', 'a'] }, apiFn: 'reorderCategories', args: [{ ordered_ids: ['b', 'a'] }] },
]

describe('queries/learning mutations → api mapping', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    for (const fn of Object.values(apiMocks)) {
      fn.mockReset()
      fn.mockResolvedValue({ ok: true })
    }
  })

  for (const tc of MUTATION_CASES) {
    it(`${tc.use} → ${tc.apiFn}`, async () => {
      const composables = await import('../../src/queries/learning')
      const useFn = (composables as unknown as Record<string, (p: unknown) => { mutateAsync: (p: unknown) => Promise<unknown> }>)[tc.use]
      const Host = defineComponent({
        setup() {
          const m = useFn(undefined)
          void m.mutateAsync(tc.payload)
          return () => null
        },
      })
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
      mount(Host, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
      await flushPromises()
      expect(apiMocks[tc.apiFn]).toHaveBeenCalledWith(...tc.args)
      // каждая успешная мутация инвалидирует кэш хотя бы раз
      // (кроме read-only preview — она ничего не меняет)
      if (!tc.noInvalidate) {
        expect(invalidateSpy).toHaveBeenCalled()
      }
    })
  }
})

describe('queries/learning queries → api mapping', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    for (const fn of Object.values(apiMocks)) {
      fn.mockReset()
      fn.mockResolvedValue(undefined)
    }
  })

  function mountQuery(setup: () => unknown) {
    const Host = defineComponent({ setup, template: '<div />' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    mount(Host, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
    return queryClient
  }

  it('useMyCoursesQuery → GET /learning/me/courses', async () => {
    const { useMyCoursesQuery } = await import('../../src/queries/learning')
    mountQuery(() => {
      useMyCoursesQuery(true)
      return () => null
    })
    await flushPromises()
    expect(apiMocks.fetchMyCourses).toHaveBeenCalledTimes(1)
  })

  it('useAdminCoursesQuery passes params', async () => {
    const { useAdminCoursesQuery } = await import('../../src/queries/learning')
    mountQuery(() => {
      useAdminCoursesQuery({ q: 'test', limit: 5, offset: 5 })
      return () => null
    })
    await flushPromises()
    expect(apiMocks.fetchAdminCourses).toHaveBeenCalledWith({ q: 'test', limit: 5, offset: 5 })
  })

  it('useAdminCourseQuery disabled for null id', async () => {
    const { useAdminCourseQuery } = await import('../../src/queries/learning')
    mountQuery(() => {
      useAdminCourseQuery(null)
      return () => null
    })
    await flushPromises()
    expect(apiMocks.fetchAdminCourse).not.toHaveBeenCalled()
  })

  it('useAdminCourseQuery fetches by id', async () => {
    const { useAdminCourseQuery } = await import('../../src/queries/learning')
    mountQuery(() => {
      useAdminCourseQuery('cid')
      return () => null
    })
    await flushPromises()
    expect(apiMocks.fetchAdminCourse).toHaveBeenCalledWith('cid')
  })

  it('useAdminProgressQuery / useAdminTestQuery fetch by id', async () => {
    const { useAdminProgressQuery, useAdminTestQuery } = await import('../../src/queries/learning')
    mountQuery(() => {
      useAdminProgressQuery('c1')
      useAdminTestQuery('i1')
      return () => null
    })
    await flushPromises()
    expect(apiMocks.fetchCourseProgress).toHaveBeenCalledWith('c1')
    expect(apiMocks.fetchTestConfig).toHaveBeenCalledWith('i1')
  })

  it('useParticipantItemsQuery fetches by course+participant, disabled without participant', async () => {
    const { useParticipantItemsQuery } = await import('../../src/queries/learning')
    mountQuery(() => {
      useParticipantItemsQuery('c1', 'p1', true)
      return () => null
    })
    await flushPromises()
    expect(apiMocks.fetchParticipantItems).toHaveBeenCalledWith('c1', 'p1')

    mountQuery(() => {
      useParticipantItemsQuery('c1', '', true)
      return () => null
    })
    await flushPromises()
    // вызовов больше не стало: пустой participantId -> enabled=false
    expect(apiMocks.fetchParticipantItems).toHaveBeenCalledTimes(1)
  })

  it('useCategoriesQuery fetches the dictionary', async () => {
    const { useCategoriesQuery } = await import('../../src/queries/learning')
    mountQuery(() => {
      useCategoriesQuery()
      return () => null
    })
    await flushPromises()
    expect(apiMocks.fetchCategories).toHaveBeenCalled()
  })

  it('useAdminAccountsQuery respects enabled flag', async () => {
    const { useAdminAccountsQuery } = await import('../../src/queries/learning')
    mountQuery(() => {
      useAdminAccountsQuery({ limit: 10, offset: 0 }, false)
      return () => null
    })
    await flushPromises()
    expect(apiMocks.fetchLearningAccounts).not.toHaveBeenCalled()
  })
})
