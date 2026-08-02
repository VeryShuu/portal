import { api } from './index'

export interface AuditEvent {
  id: number
  event_type: string
  user_id: string | null
  user_email: string | null
  resource_type: string | null
  resource_id: string | null
  resource_title: string | null
  ip_address: string | null
  user_agent: string | null
  metadata: Record<string, unknown>
  created_at: string | null
}

export interface AuditListOut {
  items: AuditEvent[]
  total: number
  limit: number
  offset: number
  /** audit M2: opaque курсор последнего элемента страницы (для keyset next-page).
   * null когда страница последняя (или включён OFFSET-режим без курсора). */
  next_cursor?: string | null
  /** audit M2: true когда возможно есть ещё строки (страница заполнена полностью). */
  has_more?: boolean
}

export interface AuditFilters {
  user_id?: string
  event_type?: string
  resource_type?: string
  ip_address?: string
  date_from?: string
  date_to?: string
  q?: string
  /** audit [H3]: глубокий поиск по metadata::text (Seq Scan, медленно на больших объёмах).
   * По умолчанию off — q ищет только по user_email/resource_title (btree+trgm). */
  extended_search?: boolean
  /** audit M2: opaque keyset-курсор (приоритет над offset). Передаётся как ?cursor=;
   * страница N+1 использует next_cursor из ответа страницы N. */
  cursor?: string
  limit?: number
  offset?: number
}

export function fetchAuditEvents(filters: AuditFilters = {}) {
  const query: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== '') query[k] = v as string | number
  }
  return api<AuditListOut>('/audit', { query })
}

export function fetchAuditEventTypes() {
  return api<string[]>('/audit/event-types')
}

export function fetchAuditQueueDepth() {
  return api<{ pending: number; processing: number }>('/audit/queue/depth')
}

export function buildAuditCsvUrl(filters: AuditFilters = {}): string {
  const usp = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== '') usp.set(k, String(v))
  }
  const qs = usp.toString()
  const base = (import.meta.env.VITE_API_URL ?? '/api/v1') + '/audit/export.csv'
  return qs ? `${base}?${qs}` : base
}
