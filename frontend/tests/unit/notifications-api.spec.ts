import { describe, it, expect, vi, beforeEach } from 'vitest'

const apiMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
}))

import {
  fetchNotifications,
  fetchUnreadCount,
  markRead,
  markAllRead,
  deleteNotification,
} from '../../src/api/notifications'

describe('notifications API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({ ok: true })
  })

  describe('fetchNotifications', () => {
    it('GETs /notifications without query when no params', async () => {
      apiMock.mockResolvedValueOnce({ items: [], total: 0, unread_count: 0 })
      const res = await fetchNotifications()
      expect(apiMock).toHaveBeenCalledWith('/notifications', { query: undefined })
      expect(res).toEqual({ items: [], total: 0, unread_count: 0 })
    })

    it('passes query params as-is', async () => {
      await fetchNotifications({ unread_only: true, limit: 20, offset: 40 })
      expect(apiMock).toHaveBeenCalledWith('/notifications', {
        query: { unread_only: true, limit: 20, offset: 40 },
      })
    })

    it('propagates API errors', async () => {
      apiMock.mockRejectedValueOnce(new Error('network'))
      await expect(fetchNotifications()).rejects.toThrow('network')
    })
  })

  describe('fetchUnreadCount', () => {
    it('GETs /notifications/unread-count', async () => {
      apiMock.mockResolvedValueOnce({ unread_count: 7 })
      const res = await fetchUnreadCount()
      expect(apiMock).toHaveBeenCalledWith('/notifications/unread-count')
      expect(res.unread_count).toBe(7)
    })
  })

  describe('markRead', () => {
    it('POSTs /notifications/:id/read with the given id', async () => {
      await markRead('abc-123')
      expect(apiMock).toHaveBeenCalledWith('/notifications/abc-123/read', {
        method: 'POST',
      })
    })

    it('URL-encodes the id verbatim (no double-encoding)', async () => {
      await markRead('id with space')
      expect(apiMock).toHaveBeenCalledWith('/notifications/id with space/read', {
        method: 'POST',
      })
    })
  })

  describe('markAllRead', () => {
    it('POSTs /notifications/read-all', async () => {
      await markAllRead()
      expect(apiMock).toHaveBeenCalledWith('/notifications/read-all', {
        method: 'POST',
      })
    })
  })

  describe('deleteNotification', () => {
    it('DELETEs /notifications/:id', async () => {
      await deleteNotification('xyz-789')
      expect(apiMock).toHaveBeenCalledWith('/notifications/xyz-789', {
        method: 'DELETE',
      })
    })

    it('propagates 4xx errors from the API layer', async () => {
      apiMock.mockRejectedValueOnce(Object.assign(new Error('not found'), { status: 404 }))
      await expect(deleteNotification('missing')).rejects.toMatchObject({ status: 404 })
    })
  })
})
