import { api, apiUpload } from './index'

export type FeedbackCategory = 'bug' | 'suggestion' | 'other'
export type FeedbackStatus = 'open' | 'in_progress' | 'closed'

export interface FeedbackIn {
  category: FeedbackCategory
  message: string
  page_url?: string | null
}

export interface FeedbackReplyIn {
  message: string
}

export interface FeedbackReplyOut {
  id: string
  admin_id: string | null
  admin_name: string | null
  message: string
  created_at: string
}

export interface FeedbackAttachmentOut {
  id: string
  original_name: string
  size_bytes: number
  mime_type: string | null
  created_at: string
  download_url: string
}

export interface FeedbackOut {
  id: string
  category: FeedbackCategory
  message: string
  page_url: string | null
  status: FeedbackStatus
  created_at: string
  updated_at: string
  replies: FeedbackReplyOut[]
  attachments: FeedbackAttachmentOut[]
}

export interface FeedbackAdminOut extends FeedbackOut {
  user_id: string | null
  author_name: string | null
  author_email: string | null
}

export interface FeedbackListOut {
  items: FeedbackOut[]
  total: number
}

export interface FeedbackAdminListOut {
  items: FeedbackAdminOut[]
  total: number
}

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
