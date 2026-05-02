
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
const RECONNECT_DELAY_MS = 5000

export const useNotificationsStore = defineStore('notifications', () => {
  const auth = useAuthStore()

  const items = ref<NotificationItem[]>([])
  const total = ref(0)
  const unreadCount = ref(0)
  const loading = ref(false)
  const dropdownOpen = ref(false)

  let eventSource: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let lastEventId = ''

  const hasUnread = computed(() => unreadCount.value > 0)

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

  function _onSSEMessage(event: MessageEvent) {
    if (event.lastEventId) lastEventId = event.lastEventId
    try {
      const data = JSON.parse(event.data) as NotificationItem
      if (!items.value.find(n => n.id === data.id)) {
        items.value.unshift(data)
        total.value += 1
        unreadCount.value += 1
      }
    } catch {
      // ignore malformed
    }
  }

  function _onSSEError() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    scheduleReconnect()
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (auth.isAuthenticated) connectSSE()
    }, RECONNECT_DELAY_MS)
  }

  function connectSSE() {
    if (eventSource) return
    const url = lastEventId ? `${SSE_URL}?lastEventId=${encodeURIComponent(lastEventId)}` : SSE_URL
    eventSource = new EventSource(url, { withCredentials: true })
    eventSource.addEventListener('notification', _onSSEMessage)
    eventSource.onerror = _onSSEError
  }

  function disconnectSSE() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  function init() {
    loadUnreadCount()
    connectSSE()
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
    loadUnreadCount,
    loadNotifications,
    read,
    readAll,
    remove,
    connectSSE,
    disconnectSSE,
    init,
    reset,
  }
})
