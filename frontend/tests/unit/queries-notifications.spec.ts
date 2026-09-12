import { isRef } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetchNotifications = vi.fn()
const mockFetchUnreadCount = vi.fn()
const mockMarkRead = vi.fn()
const mockMarkAllRead = vi.fn()
const mockDeleteNotification = vi.fn()

vi.mock('../../src/api/notifications', () => ({
  fetchNotifications: mockFetchNotifications,
  fetchUnreadCount: mockFetchUnreadCount,
  markRead: mockMarkRead,
  markAllRead: mockMarkAllRead,
  deleteNotification: mockDeleteNotification,
}))

const _capturedQueries: any[] = []
const _capturedMutations: any[] = []
const mockInvalidate = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    _capturedQueries.push(opts)
    return { data: { value: undefined }, isLoading: { value: false }, isPending: { value: false } }
  }),
  useMutation: vi.fn((opts: any) => {
    _capturedMutations.push(opts)
    return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: { value: false } }
  }),
  useQueryClient: vi.fn(() => ({ invalidateQueries: mockInvalidate })),
}))

function resolveKey(k: unknown): unknown {
  if (isRef(k)) return resolveKey(k.value)
  return k
}

describe('src/queries/notifications', () => {
  beforeEach(() => {
    _capturedQueries.length = 0
    _capturedMutations.length = 0
    vi.clearAllMocks()
  })

  describe('useNotificationsQuery', () => {
    it('registers a query and queryFn calls fetchNotifications', async () => {
      const { useNotificationsQuery } = await import('../../src/queries/notifications')
      useNotificationsQuery()
      expect(_capturedQueries).toHaveLength(1)
      mockFetchNotifications.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchNotifications).toHaveBeenCalledWith({})
    })

    it('passes params to fetchNotifications', async () => {
      const { useNotificationsQuery } = await import('../../src/queries/notifications')
      useNotificationsQuery({ unread_only: true, limit: 20 })
      mockFetchNotifications.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchNotifications).toHaveBeenCalledWith({ unread_only: true, limit: 20 })
    })

    it('queryKey contains notifications namespace', async () => {
      const { useNotificationsQuery } = await import('../../src/queries/notifications')
      useNotificationsQuery()
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('notifications')
    })
  })

  describe('useUnreadCountQuery', () => {
    it('registers a query with unread-count key', async () => {
      const { useUnreadCountQuery } = await import('../../src/queries/notifications')
      useUnreadCountQuery()
      expect(_capturedQueries).toHaveLength(1)
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('unread')
    })

    it('queryFn calls fetchUnreadCount', async () => {
      const { useUnreadCountQuery } = await import('../../src/queries/notifications')
      useUnreadCountQuery()
      mockFetchUnreadCount.mockResolvedValueOnce(5)
      await _capturedQueries[0].queryFn()
      expect(mockFetchUnreadCount).toHaveBeenCalled()
    })
  })

  describe('useMarkReadMutation', () => {
    it('registers a mutation', async () => {
      const { useMarkReadMutation } = await import('../../src/queries/notifications')
      useMarkReadMutation()
      expect(_capturedMutations).toHaveLength(1)
    })

    it('mutationFn calls markRead with id', async () => {
      const { useMarkReadMutation } = await import('../../src/queries/notifications')
      useMarkReadMutation()
      mockMarkRead.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn('notif-1')
      expect(mockMarkRead).toHaveBeenCalledWith('notif-1')
    })

    it('onSuccess invalidates notifications queries', async () => {
      const { useMarkReadMutation } = await import('../../src/queries/notifications')
      useMarkReadMutation()
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: expect.anything() }),
      )
    })
  })

  describe('useMarkAllReadMutation', () => {
    it('registers a mutation', async () => {
      const { useMarkAllReadMutation } = await import('../../src/queries/notifications')
      useMarkAllReadMutation()
      expect(_capturedMutations).toHaveLength(1)
    })

    it('mutationFn calls markAllRead', async () => {
      const { useMarkAllReadMutation } = await import('../../src/queries/notifications')
      useMarkAllReadMutation()
      mockMarkAllRead.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn()
      expect(mockMarkAllRead).toHaveBeenCalled()
    })

    it('onSuccess invalidates notifications queries', async () => {
      const { useMarkAllReadMutation } = await import('../../src/queries/notifications')
      useMarkAllReadMutation()
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useDeleteNotificationMutation', () => {
    it('registers a mutation', async () => {
      const { useDeleteNotificationMutation } = await import('../../src/queries/notifications')
      useDeleteNotificationMutation()
      expect(_capturedMutations).toHaveLength(1)
    })

    it('mutationFn calls deleteNotification with id', async () => {
      const { useDeleteNotificationMutation } = await import('../../src/queries/notifications')
      useDeleteNotificationMutation()
      mockDeleteNotification.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn('notif-42')
      expect(mockDeleteNotification).toHaveBeenCalledWith('notif-42')
    })

    it('onSuccess invalidates notifications queries', async () => {
      const { useDeleteNotificationMutation } = await import('../../src/queries/notifications')
      useDeleteNotificationMutation()
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })
})
