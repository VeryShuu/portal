
import { api } from './index'

export interface NotificationItem {
  id: string
  type: string
  title: string
  body: string | null
  link: string | null
  is_read: boolean
  created_at: string
  read_at: string | null
}

export interface NotificationListOut {
  items: NotificationItem[]
  total: number
  unread_count: number
}

export function fetchNotifications(params?: { unread_only?: boolean; limit?: number; offset?: number }) {
  return api<NotificationListOut>('/notifications', { query: params })
}

export function fetchUnreadCount() {
  return api<{ unread_count: number }>('/notifications/unread-count')
}

export function markRead(id: string) {
  return api(`/notifications/${id}/read`, { method: 'POST' })
}

export function markAllRead() {
  return api('/notifications/read-all', { method: 'POST' })
}

export function deleteNotification(id: string) {
  return api(`/notifications/${id}`, { method: 'DELETE' })
}
