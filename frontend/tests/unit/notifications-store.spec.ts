import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

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

let mockIsAuthenticated = false
vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({ get isAuthenticated() { return mockIsAuthenticated } }),
}))

const mockEventSource = {
  addEventListener: vi.fn(),
  close: vi.fn(),
  onerror: null as ((e: Event) => void) | null,
}
const mockEventSourceCtor = vi.fn()
class MockEventSource {
  constructor(...args: unknown[]) {
    mockEventSourceCtor(...args)
    return mockEventSource as unknown as MockEventSource
  }
}
vi.stubGlobal('EventSource', MockEventSource)

describe('useNotificationsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockIsAuthenticated = false
    mockEventSource.addEventListener.mockReset()
    mockEventSource.close.mockReset()
    mockEventSourceCtor.mockClear()
  })

  describe('initial state', () => {
    it('hasUnread is false initially', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      const store = useNotificationsStore()
      expect(store.hasUnread).toBe(false)
      expect(store.unreadCount).toBe(0)
    })
  })

  describe('loadUnreadCount()', () => {
    it('sets unreadCount from api', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockFetchUnreadCount.mockResolvedValueOnce({ unread_count: 5 })
      const store = useNotificationsStore()
      await store.loadUnreadCount()
      expect(store.unreadCount).toBe(5)
      expect(store.hasUnread).toBe(true)
    })

    it('silently ignores api errors', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockFetchUnreadCount.mockRejectedValueOnce(new Error('network'))
      const store = useNotificationsStore()
      await expect(store.loadUnreadCount()).resolves.toBeUndefined()
      expect(store.unreadCount).toBe(0)
    })
  })

  describe('loadNotifications()', () => {
    it('populates items, total, unreadCount', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockFetchNotifications.mockResolvedValueOnce({
        items: [{ id: 'n1', is_read: false, title: 'T', body: 'B', created_at: '' }],
        total: 1,
        unread_count: 1,
      })
      const store = useNotificationsStore()
      await store.loadNotifications()
      expect(store.items).toHaveLength(1)
      expect(store.total).toBe(1)
      expect(store.unreadCount).toBe(1)
      expect(store.loading).toBe(false)
    })

    it('sets loading=false even after error', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockFetchNotifications.mockRejectedValueOnce(new Error('fail'))
      const store = useNotificationsStore()
      await expect(store.loadNotifications()).rejects.toThrow()
      expect(store.loading).toBe(false)
    })
  })

  describe('read()', () => {
    it('marks item as read and decrements unreadCount', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockMarkRead.mockResolvedValueOnce(undefined)
      const store = useNotificationsStore()
      store.items = [{ id: 'n1', is_read: false, title: 'T', body: 'B', created_at: '' }] as any
      store.unreadCount = 3
      await store.read('n1')
      expect(store.items[0].is_read).toBe(true)
      expect(store.unreadCount).toBe(2)
    })

    it('does not decrement unreadCount for already-read item', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockMarkRead.mockResolvedValueOnce(undefined)
      const store = useNotificationsStore()
      store.items = [{ id: 'n1', is_read: true, title: 'T', body: 'B', created_at: '' }] as any
      store.unreadCount = 1
      await store.read('n1')
      expect(store.unreadCount).toBe(1)
    })
  })

  describe('readAll()', () => {
    it('marks all items read and resets unreadCount', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockMarkAllRead.mockResolvedValueOnce(undefined)
      const store = useNotificationsStore()
      store.items = [
        { id: 'n1', is_read: false, title: 'T', body: 'B', created_at: '' },
        { id: 'n2', is_read: false, title: 'T2', body: 'B2', created_at: '' },
      ] as any
      store.unreadCount = 2
      await store.readAll()
      expect(store.items.every(n => n.is_read)).toBe(true)
      expect(store.unreadCount).toBe(0)
    })
  })

  describe('remove()', () => {
    it('removes item and adjusts counters', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockDeleteNotification.mockResolvedValueOnce(undefined)
      const store = useNotificationsStore()
      store.items = [
        { id: 'n1', is_read: false, title: 'T', body: 'B', created_at: '' },
        { id: 'n2', is_read: true, title: 'T2', body: 'B2', created_at: '' },
      ] as any
      store.total = 2
      store.unreadCount = 1
      await store.remove('n1')
      expect(store.items).toHaveLength(1)
      expect(store.total).toBe(1)
      expect(store.unreadCount).toBe(0)
    })

    it('does not decrement unreadCount for read item removal', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockDeleteNotification.mockResolvedValueOnce(undefined)
      const store = useNotificationsStore()
      store.items = [{ id: 'n2', is_read: true, title: 'T', body: 'B', created_at: '' }] as any
      store.total = 1
      store.unreadCount = 0
      await store.remove('n2')
      expect(store.unreadCount).toBe(0)
      expect(store.total).toBe(0)
    })

    it('does nothing when id not found', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      mockDeleteNotification.mockResolvedValueOnce(undefined)
      const store = useNotificationsStore()
      store.items = [{ id: 'n1', is_read: false, title: 'T', body: 'B', created_at: '' }] as any
      store.total = 1
      await store.remove('missing')
      expect(store.items).toHaveLength(1)
    })
  })

  describe('reset()', () => {
    it('clears all state and closes SSE', async () => {
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      const store = useNotificationsStore()
      store.items = [{ id: 'n1', is_read: false, title: 'T', body: 'B', created_at: '' }] as any
      store.total = 5
      store.unreadCount = 3
      store.dropdownOpen = true
      store.reset()
      expect(store.items).toHaveLength(0)
      expect(store.total).toBe(0)
      expect(store.unreadCount).toBe(0)
      expect(store.dropdownOpen).toBe(false)
    })
  })

  describe('connectSSE() / disconnectSSE()', () => {
    it('creates EventSource on connect', async () => {
      mockIsAuthenticated = true
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      const store = useNotificationsStore()
      store.connectSSE()
      expect(mockEventSourceCtor).toHaveBeenCalled()
    })

    it('does not create second EventSource if already connected', async () => {
      mockIsAuthenticated = true
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      const store = useNotificationsStore()
      store.connectSSE()
      store.connectSSE()
      expect(mockEventSourceCtor).toHaveBeenCalledTimes(1)
    })

    it('closes EventSource on disconnect', async () => {
      mockIsAuthenticated = true
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      const store = useNotificationsStore()
      store.connectSSE()
      store.disconnectSSE()
      expect(mockEventSource.close).toHaveBeenCalled()
    })

    it('does not create EventSource when not authenticated', async () => {
      mockIsAuthenticated = false
      const { useNotificationsStore } = await import('../../src/stores/notifications')
      const store = useNotificationsStore()
      store.connectSSE()
      expect(mockEventSourceCtor).not.toHaveBeenCalled()
    })
  })
})
