import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()
const apiUploadMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
  apiUpload: (...args: unknown[]) => apiUploadMock(...args),
}))

import {
  createFeedback,
  deleteFeedbackAttachment,
  getAllFeedback,
  getFeedbackById,
  getMyFeedback,
  getMyFeedbackById,
  replyToFeedback,
  updateFeedbackStatus,
  uploadFeedbackAttachment,
  FEEDBACK_ATTACHMENT_MAX_PER_TICKET,
  FEEDBACK_ATTACHMENT_MAX_SIZE,
} from '../../src/api/feedback'

describe('feedback API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiUploadMock.mockReset()
    apiMock.mockResolvedValue({})
    apiUploadMock.mockResolvedValue({})
  })

  it('createFeedback POSTs payload', async () => {
    await createFeedback({ category: 'bug', message: 'm', page_url: '/x' })
    expect(apiMock).toHaveBeenCalledWith('/feedback', {
      method: 'POST',
      body: { category: 'bug', message: 'm', page_url: '/x' },
    })
  })

  it('getMyFeedback passes params', async () => {
    await getMyFeedback({ status: 'open', limit: 10, offset: 0 })
    expect(apiMock).toHaveBeenCalledWith('/feedback/my', {
      params: { status: 'open', limit: 10, offset: 0 },
    })
  })

  it('getMyFeedback omits params when undefined', async () => {
    await getMyFeedback()
    expect(apiMock).toHaveBeenCalledWith('/feedback/my', { params: undefined })
  })

  it('getMyFeedbackById builds URL from id', async () => {
    await getMyFeedbackById('id-1')
    expect(apiMock).toHaveBeenCalledWith('/feedback/my/id-1')
  })

  it('getAllFeedback (admin) passes filters', async () => {
    await getAllFeedback({ status: 'open', q: 'bug', limit: 5 })
    expect(apiMock).toHaveBeenCalledWith('/feedback', {
      params: { status: 'open', q: 'bug', limit: 5 },
    })
  })

  it('getFeedbackById hits admin URL', async () => {
    await getFeedbackById('zzz')
    expect(apiMock).toHaveBeenCalledWith('/feedback/zzz')
  })

  it('replyToFeedback POSTs reply', async () => {
    await replyToFeedback('id-2', { message: 'hi' })
    expect(apiMock).toHaveBeenCalledWith('/feedback/id-2/reply', {
      method: 'POST',
      body: { message: 'hi' },
    })
  })

  it('updateFeedbackStatus PATCHes status', async () => {
    await updateFeedbackStatus('id-3', 'closed')
    expect(apiMock).toHaveBeenCalledWith('/feedback/id-3/status', {
      method: 'PATCH',
      body: { status: 'closed' },
    })
  })

  it('uploadFeedbackAttachment sends FormData via apiUpload', async () => {
    const file = new File(['x'], 'a.txt', { type: 'text/plain' })
    await uploadFeedbackAttachment('tid', file)
    expect(apiUploadMock).toHaveBeenCalledTimes(1)
    const [path, fd] = apiUploadMock.mock.calls[0]
    expect(path).toBe('/feedback/tid/attachments')
    expect(fd).toBeInstanceOf(FormData)
    expect((fd as FormData).get('file')).toBeInstanceOf(File)
  })

  it('deleteFeedbackAttachment issues DELETE on nested URL', async () => {
    await deleteFeedbackAttachment('fid', 'aid')
    expect(apiMock).toHaveBeenCalledWith('/feedback/fid/attachments/aid', { method: 'DELETE' })
  })

  it('exposes attachment limit constants', () => {
    expect(FEEDBACK_ATTACHMENT_MAX_SIZE).toBe(10 * 1024 * 1024)
    expect(FEEDBACK_ATTACHMENT_MAX_PER_TICKET).toBe(5)
  })

  it('propagates errors from api()', async () => {
    apiMock.mockRejectedValueOnce(new Error('boom'))
    await expect(createFeedback({ category: 'bug', message: '' })).rejects.toThrow('boom')
  })
})
