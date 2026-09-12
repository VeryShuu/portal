import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
}))

import {
  fetchMailingRecipients,
  createMailingRecipient,
  updateMailingRecipient,
  deleteMailingRecipient,
} from '../../src/api/mailingRecipients'
import { shareNewsEmail } from '../../src/api/news'

describe('mailing recipients API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({})
  })

  it('fetchMailingRecipients GETs /mailing-recipients with params', async () => {
    await fetchMailingRecipients({ q: 'al', limit: 50, offset: 0 })
    expect(apiMock).toHaveBeenCalledWith('/mailing-recipients', {
      params: { q: 'al', limit: 50, offset: 0 },
    })
  })

  it('fetchMailingRecipients GETs without params', async () => {
    await fetchMailingRecipients()
    expect(apiMock).toHaveBeenCalledWith('/mailing-recipients', { params: undefined })
  })

  it('createMailingRecipient POSTs dto', async () => {
    const dto = { name: 'Alice', email: 'a@x.local', label: 'HR' }
    await createMailingRecipient(dto)
    expect(apiMock).toHaveBeenCalledWith('/mailing-recipients', { method: 'POST', body: dto })
  })

  it('updateMailingRecipient PUTs dto to /:id', async () => {
    await updateMailingRecipient('r-1', { name: 'Bob' })
    expect(apiMock).toHaveBeenCalledWith('/mailing-recipients/r-1', {
      method: 'PUT',
      body: { name: 'Bob' },
    })
  })

  it('deleteMailingRecipient DELETEs /:id', async () => {
    await deleteMailingRecipient('r-2')
    expect(apiMock).toHaveBeenCalledWith('/mailing-recipients/r-2', { method: 'DELETE' })
  })

  it('propagates 409 errors from create', async () => {
    apiMock.mockRejectedValueOnce(Object.assign(new Error('dup'), { status: 409 }))
    await expect(createMailingRecipient({ name: 'A', email: 'a@x.local' })).rejects.toMatchObject({
      status: 409,
    })
  })
})

describe('news shareNewsEmail API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({ enqueued: 2 })
  })

  it('POSTs recipient_ids + message to /news/:id/share-email', async () => {
    const dto = { recipient_ids: ['r-1', 'r-2'], message: 'hi' }
    const res = await shareNewsEmail('n-1', dto)
    expect(apiMock).toHaveBeenCalledWith('/news/n-1/share-email', { method: 'POST', body: dto })
    expect(res.enqueued).toBe(2)
  })

  it('propagates 409 for non-published news', async () => {
    apiMock.mockRejectedValueOnce(Object.assign(new Error('conflict'), { status: 409 }))
    await expect(shareNewsEmail('n-2', { recipient_ids: ['r-1'] })).rejects.toMatchObject({
      status: 409,
    })
  })
})
