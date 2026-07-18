/**
 * Unit-тесты для новых helpdesk API-функций (counts + markTicketRead).
 *
 * ``api/helpdesk.ts`` — тонкие обёртки над ``api()`` (ofetch), поэтому тестируем
 * контракт вызова: правильный URL, метод, отсутствие/наличие body. Возврат
 * данных проверяем через mock-ответ — это даёт защиту от регрессии при
 * переименовании функций/URL.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockApi = vi.fn()
const mockApiUpload = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => mockApi(...args),
  apiUpload: (...args: unknown[]) => mockApiUpload(...args),
}))

// Импорт ПОСЛЕ mock — иначе модуль загрузится с реальным ``api``.
import {
  fetchMyTicketCounts,
  fetchAgentTicketCounts,
  markTicketRead,
} from '../../src/api/helpdesk'

describe('helpdesk ticket-counts API (меню badges)', () => {
  beforeEach(() => {
    mockApi.mockReset()
    mockApiUpload.mockReset()
  })

  it('fetchMyTicketCounts → GET /helpdesk/tickets/my/counts', async () => {
    mockApi.mockResolvedValueOnce({ active: 3 })
    const result = await fetchMyTicketCounts()
    expect(mockApi).toHaveBeenCalledWith('/helpdesk/tickets/my/counts')
    expect(result).toEqual({ active: 3 })
  })

  it('fetchAgentTicketCounts → GET /helpdesk/tickets/counts', async () => {
    mockApi.mockResolvedValueOnce({ active: 7 })
    const result = await fetchAgentTicketCounts()
    expect(mockApi).toHaveBeenCalledWith('/helpdesk/tickets/counts')
    expect(result).toEqual({ active: 7 })
  })

  it('markTicketRead → POST /helpdesk/tickets/{id}/read', async () => {
    mockApi.mockResolvedValueOnce(undefined)
    await markTicketRead('abc-123')
    expect(mockApi).toHaveBeenCalledWith('/helpdesk/tickets/abc-123/read', {
      method: 'POST',
    })
  })

  it('fetchMyTicketCounts returns zero correctly (badge hides)', async () => {
    // Бейдж скрывается при 0 — проверяем, что ответ парсится без сюрпризов.
    mockApi.mockResolvedValueOnce({ active: 0 })
    const result = await fetchMyTicketCounts()
    expect(result.active).toBe(0)
  })
})
