import { api } from './index'

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────
// Outbox-эндпоинты отдают untyped dict (нет Pydantic response-model) — в
// types.gen.d.ts схем для них нет.

// нет в OpenAPI — фронтовый тип (зеркалит ответ /admin/messenger-outbox)
export type MessengerOutboxStatus =
  | 'PENDING'
  | 'SENDING'
  | 'SENT'
  | 'FAILED'
  | 'DLQ'
  | 'CANCELLED'

// нет в OpenAPI — фронтовый тип (union из ответа /admin/messenger-outbox)
export type MessengerProvider = 'max' | 'matrix'

// нет в OpenAPI — фронтовый тип (зеркалит ответ /admin/messenger-outbox)
export interface MessengerOutboxItem {
  id: string
  provider: MessengerProvider
  chat_id: string
  text_preview: string
  status: MessengerOutboxStatus
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

// нет в OpenAPI — фронтовый тип (зеркалит ответ /admin/messenger-outbox/{id})
export interface MessengerOutboxDetail extends MessengerOutboxItem {
  text: string
  payload: Record<string, unknown>
}

// нет в OpenAPI — фронтовый тип (зеркалит ответ /admin/messenger-outbox)
export interface MessengerOutboxListOut {
  items: MessengerOutboxItem[]
  total: number
  limit: number
  offset: number
  counts_30d: Record<string, number>
  /** opaque keyset-курсор (см. EmailOutboxListOut.next_cursor). */
  next_cursor?: string | null
  has_more?: boolean
}

// нет в OpenAPI — фронтовый тип (набор query-параметров /admin/messenger-outbox)
export interface MessengerOutboxFilters {
  status?: MessengerOutboxStatus | ''
  provider?: MessengerProvider | ''
  chat_id?: string
  q?: string
  date_from?: string
  date_to?: string
  cursor?: string
  limit?: number
  offset?: number
}

export function fetchMessengerOutbox(filters: MessengerOutboxFilters = {}) {
  const query: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== '') query[k] = v as string | number
  }
  return api<MessengerOutboxListOut>('/admin/messenger-outbox', { query })
}

export function fetchMessengerOutboxItem(id: string) {
  return api<MessengerOutboxDetail>(`/admin/messenger-outbox/${id}`)
}

export function retryMessengerOutboxItem(id: string, resetAttempts = true) {
  return api<{ detail: string }>(
    `/admin/messenger-outbox/${id}/retry?reset_attempts=${resetAttempts}`,
    { method: 'POST' },
  )
}

export function cancelMessengerOutboxItem(id: string) {
  return api<{ detail: string }>(`/admin/messenger-outbox/${id}/cancel`, { method: 'POST' })
}
