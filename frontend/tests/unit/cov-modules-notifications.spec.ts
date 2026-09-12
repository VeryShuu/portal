import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

let listeners: Record<string, (e: any) => void> = {}
const mockEventSource = {
  addEventListener: vi.fn((name: string, cb: (e: any) => void) => {
    listeners[name] = cb
  }),
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

describe('useNotificationsStore (coverage)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
    listeners = {}
    mockIsAuthenticated = false
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('setUnreadCount and loadNotifications unreadOnly argument work', async () => {
    const { useNotificationsStore } = await import('../../src/stores/notifications')
    const store = useNotificationsStore()

    store.setUnreadCount(9)
    expect(store.unreadCount).toBe(9)

    mockFetchNotifications.mockResolvedValueOnce({ items: [], total: 0, unread_count: 0 })
    await store.loadNotifications(true)
    expect(mockFetchNotifications).toHaveBeenCalledWith({ unread_only: true, limit: 30 })
  })

  it('connectSSE wires listeners and processes notification events branches', async () => {
    mockIsAuthenticated = true
    const { useNotificationsStore } = await import('../../src/stores/notifications')
    const store = useNotificationsStore()

    store.connectSSE()
    expect(mockEventSourceCtor).toHaveBeenCalledWith('/api/v1/notifications/stream', { withCredentials: true })

    listeners.notification({ data: '{"id":"n1","is_read":false,"title":"T","body":"B","created_at":""}', lastEventId: 'evt-1' })
    expect(store.items[0].id).toBe('n1')
    expect(store.total).toBe(1)
    expect(store.unreadCount).toBe(1)

    listeners.notification({ data: '{"id":"n1","is_read":false,"title":"T","body":"B","created_at":""}', lastEventId: 'evt-2' })
    expect(store.items).toHaveLength(1)

    listeners.notification({ data: '{bad json', lastEventId: '' })
    expect(store.items).toHaveLength(1)

    listeners.notification({ data: 'x'.repeat(70000), lastEventId: '' })
    expect(store.items).toHaveLength(1)
  })

  it('meeting_changed and photo_processed branches dispatch events and ignore invalid payloads', async () => {
    mockIsAuthenticated = true
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    const { useNotificationsStore } = await import('../../src/stores/notifications')
    const store = useNotificationsStore()
    store.connectSSE()

    listeners.meeting_changed({})
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'meetings:changed' }))

    listeners.photo_processed({ data: 123 })
    listeners.photo_processed({ data: 'x'.repeat(70000) })
    listeners.photo_processed({ data: '{"folder_id":"f1"}' })
    expect(dispatchSpy).toHaveBeenCalledTimes(1)

    listeners.photo_processed({ data: '{"photo_id":"p1","folder_id":"f1","blurhash":"abc"}', lastEventId: 'p-evt' })
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'photos:processed' }))
  })

  it('onerror closes connection, schedules reconnect once, and reconnects when authenticated', async () => {
    mockIsAuthenticated = true
    const { useNotificationsStore } = await import('../../src/stores/notifications')
    const store = useNotificationsStore()

    store.connectSSE()
    expect(mockEventSource.onerror).toBeTypeOf('function')

    mockEventSource.onerror?.({} as Event)
    mockEventSource.onerror?.({} as Event)
    expect(mockEventSource.close).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(5000)
    expect(mockEventSourceCtor).toHaveBeenCalledTimes(2)
  })

  it('reconnect uses lastEventId query parameter after receiving event ids', async () => {
    mockIsAuthenticated = true
    const { useNotificationsStore } = await import('../../src/stores/notifications')
    const store = useNotificationsStore()

    store.connectSSE()
    listeners.notification({ data: '{"id":"n1","is_read":true,"title":"T","body":"B","created_at":""}', lastEventId: 'last id/1' })
    mockEventSource.onerror?.({} as Event)
    vi.advanceTimersByTime(5000)

    expect(mockEventSourceCtor).toHaveBeenLastCalledWith('/api/v1/notifications/stream?lastEventId=last%20id%2F1', { withCredentials: true })
  })

  it('init and initSSEOnly follow auth gate; reset clears state', async () => {
    const { useNotificationsStore } = await import('../../src/stores/notifications')
    const store = useNotificationsStore()

    mockFetchUnreadCount.mockResolvedValueOnce({ unread_count: 4 })
    mockIsAuthenticated = false
    store.init()
    await Promise.resolve()
    expect(store.unreadCount).toBe(4)
    expect(mockEventSourceCtor).not.toHaveBeenCalled()

    mockIsAuthenticated = true
    store.initSSEOnly()
    expect(mockEventSourceCtor).toHaveBeenCalledTimes(1)

    store.items = [{ id: 'n9', is_read: false, title: 't', body: 'b', created_at: '' }] as any
    store.total = 2
    store.unreadCount = 1
    store.dropdownOpen = true
    store.reset()
    expect(store.items).toEqual([])
    expect(store.total).toBe(0)
    expect(store.unreadCount).toBe(0)
    expect(store.dropdownOpen).toBe(false)
  })

  it('read/readAll/remove keep unread count non-negative', async () => {
    const { useNotificationsStore } = await import('../../src/stores/notifications')
    const store = useNotificationsStore()

    store.items = [{ id: 'n1', is_read: false, title: 't', body: 'b', created_at: '' }] as any
    store.unreadCount = 0
    store.total = 1

    mockMarkRead.mockResolvedValueOnce(undefined)
    await store.read('n1')
    expect(store.unreadCount).toBe(0)

    mockMarkAllRead.mockResolvedValueOnce(undefined)
    await store.readAll()
    expect(store.unreadCount).toBe(0)

    mockDeleteNotification.mockResolvedValueOnce(undefined)
    await store.remove('n1')
    expect(store.unreadCount).toBe(0)
    expect(store.total).toBe(0)
  })
})
