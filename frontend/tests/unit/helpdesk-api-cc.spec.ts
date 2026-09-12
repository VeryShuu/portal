/**
 * Unit-тесты для ``replyAgentTicket`` с Cc (миграция 083 — «ответить всем»).
 *
 * Проверяет, что Cc-адреса уходят в FormData как повторяющееся Form-поле
 * ``cc`` (не JSON, не массив). Бэкенд читает ``list[str] = Form(default=[])``.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockApiUpload = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: vi.fn(),
  apiUpload: (...args: unknown[]) => mockApiUpload(...args),
}))

import { replyAgentTicket } from '../../src/api/helpdesk'

describe('replyAgentTicket — Cc (reply all)', () => {
  beforeEach(() => {
    mockApiUpload.mockReset()
    mockApiUpload.mockResolvedValue({ id: 'msg1' })
  })

  it('appends each cc email as a separate form field', async () => {
    await replyAgentTicket(
      't1',
      { body_html: '<p>hi</p>', cc: ['a@x.local', 'b@y.local'] },
      [],
    )
    expect(mockApiUpload).toHaveBeenCalledTimes(1)
    const [, fd] = mockApiUpload.mock.calls[0]
    expect(fd).toBeInstanceOf(FormData)
    expect(fd.getAll('cc')).toEqual(['a@x.local', 'b@y.local'])
  })

  it('does not append cc field when cc is undefined', async () => {
    await replyAgentTicket('t1', { body_html: '<p>hi</p>' }, [])
    const [, fd] = mockApiUpload.mock.calls[0]
    expect(fd.has('cc')).toBe(false)
  })

  it('does not append cc field when cc is empty', async () => {
    await replyAgentTicket(
      't1',
      { body_html: '<p>hi</p>', cc: [] },
      [],
    )
    const [, fd] = mockApiUpload.mock.calls[0]
    expect(fd.has('cc')).toBe(false)
  })
})
