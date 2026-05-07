
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  fetchNotifications,
  fetchUnreadCount,
  markRead,
  markAllRead,
  deleteNotification,
  type NotificationItem,
} from '../api/notifications'
import { useAuthStore } from './auth'

const SSE_URL = '/api/v1/notifications/stream'
const RECONNECT_BASE_MS = 5_000
const RECONNECT_MAX_MS = 60_000
const HEARTBEAT_TIMEOUT_MS = 90_000

export const useNotificationsStore = defineStore('notifications', () => {
  const auth = useAuthStore()

  const items = ref<NotificationItem[]>([])
  const total = ref(0)
  const unreadCount = ref(0)
  const loading = ref(false)
  const dropdownOpen = ref(false)

  let eventSource: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectAttempt = 0
  let lastEventId = ''

  const hasUnread = computed(() => unreadCount.value > 0)

  function _resetHeartbeat() {
    if (heartbeatTimer) clearTimeout(heartbeatTimer)
    heartbeatTimer = setTimeout(() => {
      _onSSEError()
    }, HEARTBEAT_TIMEOUT_MS)
  }

  async function loadUnreadCount() {
    try {
      const data = await fetchUnreadCount()
      unreadCount.value = data.unread_count
    } catch {
      // non-critical
    }
  }

  async function loadNotifications(unreadOnly = false) {
    loading.value = true
    try {
      const data = await fetchNotifications({ unread_only: unreadOnly, limit: 30 })
      items.value = data.items
      total.value = data.total
      unreadCount.value = data.unread_count
    } finally {
      loading.value = false
    }
  }

  async function read(id: string) {
    await markRead(id)
    const item = items.value.find(n => n.id === id)
    if (item && !item.is_read) {
      item.is_read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    }
  }

  async function readAll() {
    await markAllRead()
    items.value.forEach(n => { n.is_read = true })
    unreadCount.value = 0
  }

  async function remove(id: string) {
    await deleteNotification(id)
    const idx = items.value.findIndex(n => n.id === id)
    if (idx !== -1) {
      const was = items.value[idx]
      if (!was.is_read) unreadCount.value = Math.max(0, unreadCount.value - 1)
      items.value.splice(idx, 1)
      total.value = Math.max(0, total.value - 1)
    }
  }

  const _SSE_MAX_DATA_BYTES = 64 * 1024

  function _onSSEMessage(event: MessageEvent) {
    if (event.lastEventId) lastEventId = event.lastEventId
    reconnectAttempt = 0
    _resetHeartbeat()
    try {
      if (typeof event.data === 'string' && event.data.length > _SSE_MAX_DATA_BYTES) return
      const data = JSON.parse(event.data) as NotificationItem
      if (!items.value.find(n => n.id === data.id)) {
        items.value.unshift(data)
        total.value += 1
        if (!data.is_read) unreadCount.value += 1
      }
    } catch {
      // ignore malformed
    }
  }

  function _onSSEError() {
    if (heartbeatTimer) {
      clearTimeout(heartbeatTimer)
      heartbeatTimer = null
    }
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    scheduleReconnect()
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** reconnectAttempt, RECONNECT_MAX_MS)
    reconnectAttempt += 1
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (auth.isAuthenticated) connectSSE()
    }, delay)
  }

  function connectSSE() {
    if (eventSource) return
    if (!auth.isAuthenticated) return
    const url = lastEventId ? `${SSE_URL}?lastEventId=${encodeURIComponent(lastEventId)}` : SSE_URL
    eventSource = new EventSource(url, { withCredentials: true })
    eventSource.addEventListener('notification', _onSSEMessage)
    eventSource.onerror = _onSSEError
    _resetHeartbeat()
  }

  function disconnectSSE() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (heartbeatTimer) {
      clearTimeout(heartbeatTimer)
      heartbeatTimer = null
    }
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    reconnectAttempt = 0
  }

  function setUnreadCount(count: number): void {
    unreadCount.value = count
  }

  function init() {
    loadUnreadCount()
    if (auth.isAuthenticated) connectSSE()
  }

  function initSSEOnly() {
    if (auth.isAuthenticated) connectSSE()
  }

  function reset() {
    disconnectSSE()
    items.value = []
    total.value = 0
    unreadCount.value = 0
    dropdownOpen.value = false
    lastEventId = ''
  }

  return {
    items,
    total,
    unreadCount,
    loading,
    dropdownOpen,
    hasUnread,
    setUnreadCount,
    loadUnreadCount,
    loadNotifications,
    read,
    readAll,
    remove,
    connectSSE,
    disconnectSSE,
    init,
    initSSEOnly,
    reset,
  }
})
