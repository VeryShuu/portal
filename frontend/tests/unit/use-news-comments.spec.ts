import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

const mockCreateMutate = vi.fn()
const mockUpdateMutate = vi.fn()
const mockDeleteMutate = vi.fn()
const mockMessageError = vi.fn()
const mockMessageSuccess = vi.fn()

const commentsDataRef = ref<any>(null)
const createPendingRef = ref(false)

vi.mock('../../src/queries/news', () => ({
  useNewsCommentsQuery: () => ({ data: commentsDataRef }),
  useCreateNewsCommentMutation: () => ({
    mutateAsync: mockCreateMutate,
    isPending: createPendingRef,
  }),
  useUpdateNewsCommentMutation: () => ({ mutateAsync: mockUpdateMutate }),
  useDeleteNewsCommentMutation: () => ({ mutateAsync: mockDeleteMutate }),
}))

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({
  useMessage: () => ({ error: mockMessageError, success: mockMessageSuccess }),
}))

import { useNewsComments } from '../../src/composables/useNewsComments'

describe('useNewsComments (src/composables)', () => {
  beforeEach(() => {
    mockCreateMutate.mockClear()
    mockUpdateMutate.mockClear()
    mockDeleteMutate.mockClear()
    mockMessageError.mockClear()
    mockMessageSuccess.mockClear()
    mockCreateMutate.mockResolvedValue(undefined)
    mockUpdateMutate.mockResolvedValue(undefined)
    mockDeleteMutate.mockResolvedValue(undefined)
    commentsDataRef.value = null
    createPendingRef.value = false
  })

  it('exposes empty list/total defaults when query has no data and reflects pending flag', () => {
    createPendingRef.value = true
    const state = useNewsComments(ref('n1'))

    expect(state.comments.value).toEqual([])
    expect(state.total.value).toBe(0)
    expect(state.submitting.value).toBe(true)
    expect(state.newComment.value).toBe('')
  })

  it('maps commentsQuery.data.items/total onto computed values', () => {
    commentsDataRef.value = { items: [{ id: 'c1' }, { id: 'c2' }], total: 2 }
    const state = useNewsComments(ref('n1'))

    expect(state.comments.value).toHaveLength(2)
    expect(state.total.value).toBe(2)
  })

  it('submit() early-returns when comment is blank after trim', async () => {
    const state = useNewsComments(ref('n1'))
    state.newComment.value = '   '
    await state.submit()
    expect(mockCreateMutate).not.toHaveBeenCalled()
  })

  it('submit() creates the comment and clears the field on success', async () => {
    const state = useNewsComments(ref('n42'))
    state.newComment.value = ' hello '
    await state.submit()

    expect(mockCreateMutate).toHaveBeenCalledWith({ newsId: 'n42', body: 'hello' })
    expect(state.newComment.value).toBe('')
  })

  it('submit() shows error toast and keeps draft on mutation failure', async () => {
    mockCreateMutate.mockRejectedValueOnce(new Error('boom'))
    const state = useNewsComments(ref('n1'))
    state.newComment.value = 'hi'
    await state.submit()

    expect(mockMessageError).toHaveBeenCalledWith('common.error')
    expect(state.newComment.value).toBe('hi')
  })

  it('edit() returns false when body is empty after trim', async () => {
    const state = useNewsComments(ref('n1'))
    const ok = await state.edit('c1', '   ')
    expect(ok).toBe(false)
    expect(mockUpdateMutate).not.toHaveBeenCalled()
  })

  it('edit() trims body, calls update mutation and returns true on success', async () => {
    const state = useNewsComments(ref('n9'))
    const ok = await state.edit('c1', ' edited body ')

    expect(mockUpdateMutate).toHaveBeenCalledWith({ newsId: 'n9', commentId: 'c1', body: 'edited body' })
    expect(ok).toBe(true)
  })

  it('edit() shows error and returns false on mutation failure', async () => {
    mockUpdateMutate.mockRejectedValueOnce(new Error('boom'))
    const state = useNewsComments(ref('n1'))
    const ok = await state.edit('c1', 'x')

    expect(ok).toBe(false)
    expect(mockMessageError).toHaveBeenCalledWith('common.error')
  })

  it('remove() calls delete mutation and silently swallows failure to toast', async () => {
    mockDeleteMutate.mockRejectedValueOnce(new Error('boom'))
    const state = useNewsComments(ref('n1'))

    await state.remove('c1')
    expect(mockDeleteMutate).toHaveBeenCalledWith({ newsId: 'n1', commentId: 'c1' })
    expect(mockMessageError).toHaveBeenCalledWith('common.error')
  })

  it('remove() succeeds silently (no toast) when delete resolves', async () => {
    const state = useNewsComments(ref('n1'))
    await state.remove('c1')
    expect(mockDeleteMutate).toHaveBeenCalledWith({ newsId: 'n1', commentId: 'c1' })
    expect(mockMessageError).not.toHaveBeenCalled()
  })
})
