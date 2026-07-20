import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('../../src/api/index', () => ({ api: (...args: unknown[]) => apiMock(...args) }))

const apiMock = vi.fn()

import {
  fetchEmailOutbox,
  fetchEmailOutboxItem,
  retryEmailOutboxItem,
  cancelEmailOutboxItem,
  fetchEmailOutboxStats,
} from '../../src/api/emailOutbox'

describe('api/emailOutbox', () => {
  beforeEach(() => {
    apiMock.mockClear()
    apiMock.mockResolvedValue({})
  })

  it('fetchEmailOutbox filters out undefined/null/empty values from the query', async () => {
    await fetchEmailOutbox({
      status: 'PENDING',
      kind: undefined,
      to_email: null,
      q: '',
      date_from: '2025-01-01',
      limit: 50,
      offset: 0,
    })

    expect(apiMock).toHaveBeenCalledWith('/admin/email-outbox', {
      query: { status: 'PENDING', date_from: '2025-01-01', limit: 50, offset: 0 },
    })
  })

  it('fetchEmailOutbox defaults to empty filters object when none are passed', async () => {
    await fetchEmailOutbox()
    expect(apiMock).toHaveBeenCalledWith('/admin/email-outbox', { query: {} })
  })

  it('fetchEmailOutboxItem requests the detail endpoint', async () => {
    await fetchEmailOutboxItem('abc')
    expect(apiMock).toHaveBeenCalledWith('/admin/email-outbox/abc')
  })

  it('retryEmailOutboxItem defaults resetAttempts to true', async () => {
    await retryEmailOutboxItem('abc')
    expect(apiMock).toHaveBeenCalledWith(
      '/admin/email-outbox/abc/retry?reset_attempts=true',
      { method: 'POST' },
    )
  })

  it('retryEmailOutboxItem respects explicit resetAttempts=false', async () => {
    await retryEmailOutboxItem('abc', false)
    expect(apiMock).toHaveBeenCalledWith(
      '/admin/email-outbox/abc/retry?reset_attempts=false',
      { method: 'POST' },
    )
  })

  it('cancelEmailOutboxItem hits the cancel endpoint', async () => {
    await cancelEmailOutboxItem('abc')
    expect(apiMock).toHaveBeenCalledWith('/admin/email-outbox/abc/cancel', { method: 'POST' })
  })

  it('fetchEmailOutboxStats hits the stats endpoint', async () => {
    await fetchEmailOutboxStats()
    expect(apiMock).toHaveBeenCalledWith('/admin/email-outbox/_/stats')
  })
})
