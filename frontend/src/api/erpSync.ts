/**
 * API-клиент для ERP-синхронизации (docs/erp-sync.md).
 *
 * Per-module настройки (фильтры писём + переключатели). IMAP-приёмка общая —
 * во вкладке Email (ADR-048). Ручной запуск импорта + история runs.
 */
import { api, apiUpload } from './index'

// ── Settings (singleton, per-module) ───────────────────────────────────────

export interface ErpSyncSettingsOut {
  enabled: boolean
  poll_interval_seconds: number
  expected_interval_days: number
  notify_emails: string[] | null
  poll_enabled: boolean
  mail_subject_filter: string | null
  mail_sender_filter: string | null
  mail_attachment_filter: string | null
  delete_after_fetch: boolean
  // Миграция 092: второй поток — отсутствия. Настройки общие с днями рождения
  // (enabled/poll_interval/notify_emails), per-потоковые — ниже.
  absences_poll_enabled: boolean
  mail_absences_subject_filter: string | null
  mail_absences_sender_filter: string | null
  mail_absences_attachment_filter: string | null
  absences_expected_interval_days: number
  updated_at: string | null
}

export interface ErpSyncSettingsIn {
  enabled: boolean
  poll_interval_seconds: number
  expected_interval_days: number
  notify_emails: string[] | null
  poll_enabled: boolean
  mail_subject_filter: string | null
  mail_sender_filter: string | null
  mail_attachment_filter: string | null
  delete_after_fetch: boolean
  absences_poll_enabled: boolean
  mail_absences_subject_filter: string | null
  mail_absences_sender_filter: string | null
  mail_absences_attachment_filter: string | null
  absences_expected_interval_days: number
}

// ── Runs (история импортов) ─────────────────────────────────────────────────

export interface ErpSyncRun {
  id: number
  message_id: string | null
  attachment_name: string | null
  triggered_by: 'cron' | 'manual'
  started_at: string
  finished_at: string | null
  status: 'success' | 'partial' | 'failed' | 'skipped'
  rows_total: number | null
  rows_matched: number | null
  rows_updated: number | null
  rows_unmatched: number | null
  rows_ambiguous: number | null
  conflicts: number | null
  errors: number | null
  report: ErpSyncRunReport
}

export interface ErpSyncRunReport {
  changed?: ErpSyncReportChanged[]
  unmatched?: ErpSyncReportUnmatched[]
  ambiguous?: ErpSyncReportAmbiguous[]
  conflicts?: ErpSyncReportConflict[]
  errors?: ErpSyncReportError[]
  truncated?: Record<string, number>
}

export interface ErpSyncReportChanged {
  fio: string
  user_id?: string
  fields: Record<string, { old: unknown; new: unknown }>
}

export interface ErpSyncReportUnmatched {
  fio: string
  birth_date: string
  gender: string
}

export interface ErpSyncReportAmbiguous {
  fio: string
  candidates: { id: string; full_name: string; department: string | null }[]
}

export interface ErpSyncReportConflict {
  fio: string
  occurrences: number
  variants: { birth_date: string; gender: string }[]
}

export interface ErpSyncReportError {
  raw: string
  reason: string
}

export interface ErpSyncRunList {
  items: ErpSyncRun[]
  total: number
}

export interface ErpSyncRunNowResponse {
  status: string // 'queued' | 'processed'
  job_id?: string | null
  run_id?: number | null
}

// ── Endpoints ───────────────────────────────────────────────────────────────

export function fetchErpSyncSettings(): Promise<ErpSyncSettingsOut> {
  return api<ErpSyncSettingsOut>('/erp-sync/settings')
}

export function putErpSyncSettings(dto: ErpSyncSettingsIn): Promise<ErpSyncSettingsOut> {
  return api<ErpSyncSettingsOut>('/erp-sync/settings', { method: 'PUT', body: dto })
}

export function runErpSyncNow(): Promise<ErpSyncRunNowResponse> {
  return api<ErpSyncRunNowResponse>('/erp-sync/run', { method: 'POST' })
}

export function importErpSyncFile(file: File): Promise<ErpSyncRunNowResponse> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<ErpSyncRunNowResponse>('/erp-sync/import-file', form)
}

export function fetchErpSyncRuns(
  params: { limit?: number; offset?: number } = {},
): Promise<ErpSyncRunList> {
  const query: Record<string, number> = {}
  if (params.limit !== undefined) query.limit = params.limit
  if (params.offset !== undefined) query.offset = params.offset
  return api<ErpSyncRunList>('/erp-sync/runs', { query })
}

// ── Absences (второй поток: отпуска/отгулы/болезни/командировки) ────────────

/** Canonical kind отсутствия (согласован с ABSENCE_KIND_VALUES в backend). */
export type ErpAbsenceKind =
  | 'vacation_main'
  | 'vacation_extra'
  | 'unpaid_leave'
  | 'sick'
  | 'business_trip'
  | 'day_off_paid'
  | 'day_off_unpaid'

export interface ErpAbsencesRun {
  id: number
  message_id: string | null
  attachment_name: string | null
  triggered_by: 'cron' | 'manual'
  started_at: string
  finished_at: string | null
  status: 'success' | 'partial' | 'failed' | 'skipped'
  rows_total: number | null
  rows_matched: number | null
  rows_inserted: number | null
  rows_unmatched: number | null
  rows_ambiguous: number | null
  errors: number | null
  report: ErpAbsencesRunReport
}

export interface ErpAbsencesRunReport {
  inserted?: ErpAbsencesReportInserted[]
  unmatched?: ErpAbsencesReportUnmatched[]
  ambiguous?: ErpSyncReportAmbiguous[]
  errors?: ErpSyncReportError[]
  truncated?: Record<string, number>
}

export interface ErpAbsencesReportInserted {
  fio: string
  user_id?: string
  kind: ErpAbsenceKind
  position: string | null
  department: string | null
  start_date: string
  end_date: string
}

export interface ErpAbsencesReportUnmatched {
  fio: string
  kind: ErpAbsenceKind
  start_date: string
  end_date: string
}

export interface ErpAbsencesRunList {
  items: ErpAbsencesRun[]
  total: number
}

export function runErpAbsencesNow(): Promise<ErpSyncRunNowResponse> {
  return api<ErpSyncRunNowResponse>('/erp-sync/absences/run', { method: 'POST' })
}

export function importErpAbsencesFile(file: File): Promise<ErpSyncRunNowResponse> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<ErpSyncRunNowResponse>('/erp-sync/absences/import-file', form)
}

export function fetchErpAbsencesRuns(
  params: { limit?: number; offset?: number } = {},
): Promise<ErpAbsencesRunList> {
  const query: Record<string, number> = {}
  if (params.limit !== undefined) query.limit = params.limit
  if (params.offset !== undefined) query.offset = params.offset
  return api<ErpAbsencesRunList>('/erp-sync/absences/runs', { query })
}
