/**
 * Unit-тесты для API-клиентов matrix-bot и messenger-outbox.
 *
 * Тонкие обёртки над ``api()`` (ofetch) — тестируем контракт вызова: URL,
 * метод, query-фильтры, body. Возврат данных — через mock-ответ (паттерн
 * helpdesk-api-counts.spec.ts).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockApi = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => mockApi(...args),
}))

// Импорт ПОСЛЕ mock — иначе модуль загрузится с реальным ``api``.
import {
  fetchMatrixBot,
  putMatrixBot,
  testMatrixBot,
} from '../../src/api/matrixBot'
import {
  fetchMessengerOutbox,
  fetchMessengerOutboxItem,
  retryMessengerOutboxItem,
  cancelMessengerOutboxItem,
} from '../../src/api/messengerOutbox'
import {
  fetchAdminNotificationPreferences,
  patchAdminNotificationPreferences,
} from '../../src/api/users'

describe('matrixBot API', () => {
  beforeEach(() => mockApi.mockReset())

  it('fetchMatrixBot → GET /admin/matrix-bot', async () => {
    mockApi.mockResolvedValueOnce({ configured: false, enabled: false })
    const result = await fetchMatrixBot()
    expect(mockApi).toHaveBeenCalledWith('/admin/matrix-bot')
    expect(result.enabled).toBe(false)
  })

  it('putMatrixBot → PUT с body (токен передаётся только при вводе)', async () => {
    mockApi.mockResolvedValueOnce({ enabled: true })
    await putMatrixBot({ enabled: true, homeserver_url: 'https://m' })
    expect(mockApi).toHaveBeenCalledWith('/admin/matrix-bot', {
      method: 'PUT',
      body: { enabled: true, homeserver_url: 'https://m' },
    })

    await putMatrixBot({ enabled: true, access_token: 'mct_x' })
    expect(mockApi).toHaveBeenLastCalledWith('/admin/matrix-bot', {
      method: 'PUT',
      body: { enabled: true, access_token: 'mct_x' },
    })
  })

  it('testMatrixBot без цели → body.target=null (админу по конвенции)', async () => {
    mockApi.mockResolvedValueOnce({ ok: true })
    const result = await testMatrixBot()
    expect(mockApi).toHaveBeenCalledWith('/admin/matrix-bot/test', {
      method: 'POST',
      body: { target: null },
    })
    expect(result.ok).toBe(true)
  })

  it('testMatrixBot с целью → body.target передан как есть', async () => {
    mockApi.mockResolvedValueOnce({ ok: true })
    await testMatrixBot('@borzihin.vs:matrix.mage.ru')
    expect(mockApi).toHaveBeenCalledWith('/admin/matrix-bot/test', {
      method: 'POST',
      body: { target: '@borzihin.vs:matrix.mage.ru' },
    })
  })
})

describe('messengerOutbox API', () => {
  beforeEach(() => mockApi.mockReset())

  it('fetchMessengerOutbox → query-фильтры (пустые значения не отправляются)', async () => {
    mockApi.mockResolvedValueOnce({ items: [], total: 0 })
    await fetchMessengerOutbox({
      status: 'DLQ',
      provider: '',
      q: undefined,
      chat_id: '@u:matrix.mage.ru',
    })
    expect(mockApi).toHaveBeenCalledWith('/admin/messenger-outbox', {
      query: { status: 'DLQ', chat_id: '@u:matrix.mage.ru' },
    })
  })

  it('fetchMessengerOutbox без фильтров → пустой query', async () => {
    mockApi.mockResolvedValueOnce({ items: [], total: 0 })
    await fetchMessengerOutbox()
    expect(mockApi).toHaveBeenCalledWith('/admin/messenger-outbox', { query: {} })
  })

  it('fetchMessengerOutboxItem → GET /{id}', async () => {
    mockApi.mockResolvedValueOnce({ id: 'x1', text: 'привет' })
    const result = await fetchMessengerOutboxItem('x1')
    expect(mockApi).toHaveBeenCalledWith('/admin/messenger-outbox/x1')
    expect(result.text).toBe('привет')
  })

  it('retryMessengerOutboxItem → POST /{id}/retry с reset_attempts', async () => {
    mockApi.mockResolvedValueOnce({ detail: 'rescheduled' })
    await retryMessengerOutboxItem('x1')
    expect(mockApi).toHaveBeenCalledWith('/admin/messenger-outbox/x1/retry?reset_attempts=true', {
      method: 'POST',
    })

    await retryMessengerOutboxItem('x1', false)
    expect(mockApi).toHaveBeenLastCalledWith(
      '/admin/messenger-outbox/x1/retry?reset_attempts=false',
      { method: 'POST' },
    )
  })

  it('cancelMessengerOutboxItem → POST /{id}/cancel', async () => {
    mockApi.mockResolvedValueOnce({ detail: 'cancelled' })
    await cancelMessengerOutboxItem('x1')
    expect(mockApi).toHaveBeenCalledWith('/admin/messenger-outbox/x1/cancel', {
      method: 'POST',
    })
  })
})

describe('admin notification-preferences API', () => {
  beforeEach(() => mockApi.mockReset())

  it('fetchAdminNotificationPreferences → GET /users/admin/{id}/notification-preferences', async () => {
    mockApi.mockResolvedValueOnce({ chat_notifications_enabled: true })
    const result = await fetchAdminNotificationPreferences('u1')
    expect(mockApi).toHaveBeenCalledWith('/users/admin/u1/notification-preferences')
    expect(result.chat_notifications_enabled).toBe(true)
  })

  it('patchAdminNotificationPreferences → PATCH с body', async () => {
    mockApi.mockResolvedValueOnce({ chat_notifications_enabled: false })
    await patchAdminNotificationPreferences('u1', { chat_notifications_enabled: false })
    expect(mockApi).toHaveBeenCalledWith('/users/admin/u1/notification-preferences', {
      method: 'PATCH',
      body: { chat_notifications_enabled: false },
    })
  })
})
