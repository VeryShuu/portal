
import { api } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type NotificationItem = components['schemas']['NotificationOut']
export type NotificationListOut = components['schemas']['NotificationListOut']

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
