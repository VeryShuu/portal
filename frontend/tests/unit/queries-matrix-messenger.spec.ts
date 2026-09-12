/**
 * Query-композаблы matrix-bot и messenger-outbox (queries/admin.ts).
 *
 * Харнесс — как queries-admin.spec.ts: @tanstack/vue-query замокан,
 * useQuery/useMutation опции захватываются в _capturedQueries/Mutations.
 */
import { isRef } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetchMatrixBot = vi.fn()
const mockPutMatrixBot = vi.fn()
const mockFetchMessengerOutbox = vi.fn()
const mockFetchMessengerOutboxItem = vi.fn()
const mockRetryMessengerOutboxItem = vi.fn()
const mockCancelMessengerOutboxItem = vi.fn()

vi.mock('../../src/api/matrixBot', () => ({
  fetchMatrixBot: mockFetchMatrixBot,
  putMatrixBot: mockPutMatrixBot,
  testMatrixBot: vi.fn(),
}))

vi.mock('../../src/api/messengerOutbox', () => ({
  fetchMessengerOutbox: mockFetchMessengerOutbox,
  fetchMessengerOutboxItem: mockFetchMessengerOutboxItem,
  retryMessengerOutboxItem: mockRetryMessengerOutboxItem,
  cancelMessengerOutboxItem: mockCancelMessengerOutboxItem,
}))

const _capturedQueries: any[] = []
const _capturedMutations: any[] = []
const mockInvalidate = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: unknown) => {
    _capturedQueries.push(opts)
    return {}
  }),
  useMutation: vi.fn((opts: unknown) => {
    _capturedMutations.push(opts)
    return {}
  }),
  useQueryClient: vi.fn(() => ({ invalidateQueries: mockInvalidate })),
}))

function resolveKey(k: unknown): unknown {
  if (isRef(k)) return resolveKey(k.value)
  return k
}

describe('src/queries/admin: matrix-bot + messenger-outbox', () => {
  beforeEach(() => {
    _capturedQueries.length = 0
    _capturedMutations.length = 0
    vi.clearAllMocks()
  })

  describe('useMatrixBotQuery', () => {
    it('queryFn calls fetchMatrixBot; key — admin/matrix-bot', async () => {
      const { useMatrixBotQuery } = await import('../../src/queries/admin')
      useMatrixBotQuery()
      mockFetchMatrixBot.mockResolvedValueOnce({ enabled: false })
      await _capturedQueries[0].queryFn()
      expect(mockFetchMatrixBot).toHaveBeenCalled()
      expect(JSON.stringify(resolveKey(_capturedQueries[0].queryKey))).toContain('matrix-bot')
    })
  })

  describe('usePutMatrixBotMutation', () => {
    it('mutationFn calls putMatrixBot with dto; invalidates matrix-bot', async () => {
      const { usePutMatrixBotMutation } = await import('../../src/queries/admin')
      usePutMatrixBotMutation()
      const dto = { enabled: true }
      mockPutMatrixBot.mockResolvedValueOnce({ enabled: true })
      await _capturedMutations[0].mutationFn(dto)
      expect(mockPutMatrixBot).toHaveBeenCalledWith(dto)
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useMessengerOutboxQuery', () => {
    it('queryFn passes filters; key — messenger-outbox namespace', async () => {
      const { useMessengerOutboxQuery } = await import('../../src/queries/admin')
      useMessengerOutboxQuery({ status: 'DLQ', provider: 'matrix', limit: 50 })
      mockFetchMessengerOutbox.mockResolvedValueOnce({ items: [], total: 0 })
      await _capturedQueries[0].queryFn()
      expect(mockFetchMessengerOutbox).toHaveBeenCalledWith({ status: 'DLQ', provider: 'matrix', limit: 50 })
      expect(JSON.stringify(resolveKey(_capturedQueries[0].queryKey))).toContain('messenger-outbox')
    })
  })

  describe('useMessengerOutboxItemQuery', () => {
    it('queryFn calls fetchMessengerOutboxItem; disabled без id', async () => {
      const { useMessengerOutboxItemQuery } = await import('../../src/queries/admin')
      useMessengerOutboxItemQuery(null)
      expect(resolveKey(_capturedQueries[0].enabled)).toBe(false)

      useMessengerOutboxItemQuery('abc')
      mockFetchMessengerOutboxItem.mockResolvedValueOnce({ id: 'abc' })
      await _capturedQueries[1].queryFn()
      expect(mockFetchMessengerOutboxItem).toHaveBeenCalledWith('abc')
      expect(resolveKey(_capturedQueries[1].enabled)).toBe(true)
    })
  })

  describe('useRetry/useCancelMessengerOutboxMutation', () => {
    it('retry: mutationFn + invalidate', async () => {
      const { useRetryMessengerOutboxMutation } = await import('../../src/queries/admin')
      useRetryMessengerOutboxMutation()
      mockRetryMessengerOutboxItem.mockResolvedValueOnce({ detail: 'ok' })
      await _capturedMutations[0].mutationFn('row-1')
      expect(mockRetryMessengerOutboxItem).toHaveBeenCalledWith('row-1', true)
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })

    it('cancel: mutationFn + invalidate', async () => {
      const { useCancelMessengerOutboxMutation } = await import('../../src/queries/admin')
      useCancelMessengerOutboxMutation()
      mockCancelMessengerOutboxItem.mockResolvedValueOnce({ detail: 'ok' })
      await _capturedMutations[0].mutationFn('row-1')
      expect(mockCancelMessengerOutboxItem).toHaveBeenCalledWith('row-1')
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })
})
