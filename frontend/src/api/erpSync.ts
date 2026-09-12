/**
 * API-клиент для ERP-синхронизации (docs/erp-sync.md).
 *
 * Per-module настройки (фильтры писём + переключатели). IMAP-приёмка общая —
 * во вкладке Email (ADR-048). Ручной запуск импорта + история runs.
 */
import { api, apiUpload } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

/**
 * OpenAPI помечает поля с дефолтами как optional, но FastAPI-сериализация
 * модели всегда включает их в ответ — нормализуем через `Required<>`.
 * Миграция 092: второй поток — отсутствия. Настройки общие с днями рождения
 * (enabled/poll_interval/notify_emails), per-потоковые — `absences_*`/`mail_absences_*`.
 */
export type ErpSyncSettingsOut = Required<components['schemas']['ErpSyncSettingsOut']>

export type ErpSyncSettingsIn = components['schemas']['ErpSyncSettingsIn']

/**
 * `report` — JSONB без Pydantic-схемы (в OpenAPI это `{[key: string]: unknown}`),
 * поэтому типизируется вручную ниже; остальные поля — из generated-схемы.
 */
export type ErpSyncRun = Omit<components['schemas']['ErpSyncRunOut'], 'report'> & {
  report: ErpSyncRunReport
}

export type ErpSyncRunList = Omit<components['schemas']['ErpSyncRunList'], 'items'> & {
  items: ErpSyncRun[]
}

export type ErpSyncRunNowResponse = components['schemas']['ErpSyncRunNowResponse']

export type ErpAbsencesRun = Omit<components['schemas']['ErpAbsencesRunOut'], 'report'> & {
  report: ErpAbsencesRunReport
}

export type ErpAbsencesRunList = Omit<components['schemas']['ErpAbsencesRunList'], 'items'> & {
  items: ErpAbsencesRun[]
}

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────

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

// нет в OpenAPI — фронтовый тип (в generated `ErpAbsenceOut['kind']` — просто string)
/** Canonical kind отсутствия (согласован с ABSENCE_KIND_VALUES в backend). */
export type ErpAbsenceKind =
  | 'vacation_main'
  | 'vacation_extra'
  | 'unpaid_leave'
  | 'sick'
  | 'business_trip'
  | 'day_off_paid'
  | 'day_off_unpaid'

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
