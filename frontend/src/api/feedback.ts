import { api, apiUpload } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type FeedbackCategory = components['schemas']['FeedbackCategory']
export type FeedbackStatus = components['schemas']['FeedbackStatus']
export type FeedbackIn = components['schemas']['FeedbackIn']
export type FeedbackReplyIn = components['schemas']['FeedbackReplyIn']
export type FeedbackReplyOut = components['schemas']['FeedbackReplyOut']
export type FeedbackAttachmentOut = components['schemas']['FeedbackAttachmentOut']
export type FeedbackOut = components['schemas']['FeedbackOut']
export type FeedbackAdminOut = components['schemas']['FeedbackAdminOut']
export type FeedbackListOut = components['schemas']['FeedbackListOut']
export type FeedbackAdminListOut = components['schemas']['FeedbackAdminListOut']

export const createFeedback = (data: FeedbackIn) =>
  api<FeedbackOut>('/feedback', { method: 'POST', body: data })

export const getMyFeedback = (params?: {
  status?: string
  limit?: number
  offset?: number
}) => api<FeedbackListOut>('/feedback/my', { params })

export const getMyFeedbackById = (id: string) =>
  api<FeedbackOut>(`/feedback/my/${id}`)

export const getAllFeedback = (params?: {
  status?: string
  category?: string
  q?: string
  limit?: number
  offset?: number
}) => api<FeedbackAdminListOut>('/feedback', { params })

export const getFeedbackById = (id: string) =>
  api<FeedbackAdminOut>(`/feedback/${id}`)

export const replyToFeedback = (id: string, data: FeedbackReplyIn) =>
  api<FeedbackReplyOut>(`/feedback/${id}/reply`, { method: 'POST', body: data })

export const updateFeedbackStatus = (id: string, status: FeedbackStatus) =>
  api<FeedbackAdminOut>(`/feedback/${id}/status`, {
    method: 'PATCH',
    body: { status },
  })

export const uploadFeedbackAttachment = (id: string, file: File) => {
  const fd = new FormData()
  fd.append('file', file, file.name)
  return apiUpload<FeedbackAttachmentOut>(`/feedback/${id}/attachments`, fd)
}

export const deleteFeedbackAttachment = (feedbackId: string, attachmentId: string) =>
  api<void>(`/feedback/${feedbackId}/attachments/${attachmentId}`, { method: 'DELETE' })

export const FEEDBACK_ATTACHMENT_MAX_SIZE = 10 * 1024 * 1024
export const FEEDBACK_ATTACHMENT_MAX_PER_TICKET = 5
export const FEEDBACK_ATTACHMENT_ACCEPT =
  'image/png,image/jpeg,image/gif,image/webp,image/svg+xml,application/pdf,text/plain,application/zip'
