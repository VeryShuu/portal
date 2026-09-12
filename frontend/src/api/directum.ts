/**
 * API-клиент для интеграции с Directum (docs/directum.md).
 *
 * Задача «Просроченные задачи»: OData-опрос IAssignments → матчинг ФИО →
 * дайджесты в Matrix. Пароль сервисной учётки write-only (password_set).
 */
import { api } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

// auth_username/notify_emails бэкенд сериализует всегда (Pydantic-дефолты
// попадают в ответ) — в generated они optional как артефакт дефолтов.
export type DirectumSettingsOut = Omit<
  components['schemas']['DirectumSettingsOut'],
  'auth_username' | 'notify_emails'
> & {
  auth_username: string | null
  notify_emails: string[] | null
}
export type DirectumSettingsIn = components['schemas']['DirectumSettingsIn']
export type DirectumTestResult = components['schemas']['DirectumTestResult']
export type DirectumRunList = components['schemas']['DirectumRunList']
export type DirectumRunNowResponse = components['schemas']['DirectumRunNowResponse']

// ── Runs (история прогонов) ────────────────────────────────────────────────

/**
 * Структура report-блока (JSONB). Бэкенд отдаёт его как untyped dict
 * (DirectumRunOut.report) без публикации схемы в OpenAPI — рендер в
 * DirectumRuns.vue типизируется здесь.
 */
export interface DirectumRunReport {
  notified?: DirectumReportPair[]
  skipped_opt_in?: DirectumReportPair[]
  unmatched?: DirectumReportPair[]
  ambiguous?: DirectumReportAmbiguous[]
  matrix_disabled?: boolean
  skipped_matrix_disabled?: string[]
  error?: string
  error_class?: string
  truncated?: boolean
}

export interface DirectumReportPair {
  fio: string
  tasks?: number
}

export interface DirectumReportAmbiguous extends DirectumReportPair {
  candidates: { id: string; full_name: string; department: string | null }[]
}

/** Generated DirectumRunOut с уточнениями: status/triggered_by — известные
 * литералы, report — типизированный blob (бэкенд кладёт его для каждого прогона). */
export type DirectumRun = Omit<
  components['schemas']['DirectumRunOut'],
  'status' | 'triggered_by' | 'report'
> & {
  status: 'success' | 'partial' | 'failed' | 'skipped'
  triggered_by: 'cron' | 'manual'
  report: DirectumRunReport
}

// ── Endpoints ──────────────────────────────────────────────────────────────

export function fetchDirectumSettings(): Promise<DirectumSettingsOut> {
  return api<DirectumSettingsOut>('/directum/settings')
}

export function putDirectumSettings(dto: DirectumSettingsIn): Promise<DirectumSettingsOut> {
  return api<DirectumSettingsOut>('/directum/settings', { method: 'PUT', body: dto })
}

export function testDirectumConnection(): Promise<DirectumTestResult> {
  return api<DirectumTestResult>('/directum/test', { method: 'POST' })
}

export function runDirectumNow(): Promise<DirectumRunNowResponse> {
  return api<DirectumRunNowResponse>('/directum/run', { method: 'POST' })
}

export function fetchDirectumRuns(
  params: { limit?: number; offset?: number } = {},
): Promise<DirectumRunList> {
  const query: Record<string, number> = {}
  if (params.limit !== undefined) query.limit = params.limit
  if (params.offset !== undefined) query.offset = params.offset
  return api<DirectumRunList>('/directum/runs', { query })
}
