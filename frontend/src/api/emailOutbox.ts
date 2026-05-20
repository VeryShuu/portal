import { api } from './index'

export type EmailOutboxStatus =
  | 'PENDING'
  | 'SENDING'
  | 'SENT'
  | 'FAILED'
  | 'DLQ'
  | 'CANCELLED'

export interface EmailOutboxItem {
  id: string
  kind: string
  to_email: string
  subject: string
  status: EmailOutboxStatus
  attempts: number
  max_attempts: number
  next_attempt_at: string | null
  last_error: string | null
  last_error_type: string | null
  last_error_class: string | null
  related_resource_type: string | null
  related_resource_id: string | null
  created_at: string | null
  updated_at: string | null
  sent_at: string | null
}

export interface EmailOutboxDetail extends EmailOutboxItem {
  body_html: string
  body_text: string | null
  payload: Record<string, unknown>
}

export interface EmailOutboxListOut {
  items: EmailOutboxItem[]
  total: number
  limit: number
  offset: number
  counts_30d: Record<string, number>
}

export interface EmailOutboxFilters {
  status?: EmailOutboxStatus | ''
  kind?: string
  to_email?: string
  q?: string
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
}

export function fetchEmailOutbox(filters: EmailOutboxFilters = {}) {
  const query: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== '') query[k] = v as string | number
  }
  return api<EmailOutboxListOut>('/admin/email-outbox', { query })
}

export function fetchEmailOutboxItem(id: string) {
  return api<EmailOutboxDetail>(`/admin/email-outbox/${id}`)
}

export function retryEmailOutboxItem(id: string, resetAttempts = true) {
  return api<{ detail: string }>(
    `/admin/email-outbox/${id}/retry?reset_attempts=${resetAttempts}`,
    { method: 'POST' },
  )
}

export function cancelEmailOutboxItem(id: string) {
  return api<{ detail: string }>(`/admin/email-outbox/${id}/cancel`, { method: 'POST' })
}

export function fetchEmailOutboxStats() {
  return api<{ counts: Record<string, number>; oldest_pending_at: string | null }>(
    '/admin/email-outbox/_/stats',
  )
}
