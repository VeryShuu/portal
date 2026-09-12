/**
 * API-клиент модуля «Согласование документов» (docs/approvals.md).
 *
 * Прокси к 1С: список DocumentsForApproval, карточка, вложения (base64 →
 * стрим на бэке), согласование/отклонение, массовое согласование, настройки
 * подключения (admin, пароль write-only).
 */
import { api } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type ApprovalDocument = components['schemas']['ApprovalDocument']
export type ApprovalDocumentDetail = components['schemas']['ApprovalDocumentDetail']
export type ApprovalDocumentList = components['schemas']['ApprovalDocumentList']
export type ApprovalAttachmentInfo = components['schemas']['ApprovalAttachmentInfo']
export type ApproveIn = components['schemas']['ApproveIn']
export type RejectIn = components['schemas']['RejectIn']
export type ActionOut = components['schemas']['ActionOut']
export type BulkApproveOut = components['schemas']['BulkApproveOut']
export type ApprovalsSettingsOut = components['schemas']['ApprovalsSettingsOut']
export type ApprovalsSettingsIn = components['schemas']['ApprovalsSettingsIn']
export type ApprovalsTestResult = components['schemas']['ApprovalsTestResult']

// Максимум документов в одной партии массового согласования — зеркало
// BULK_APPROVE_MAX в backend/app/schemas/approvals.py: партия идёт строго
// последовательно с паузами (каждый вызов проводит документ в 1С), лимит 50
// не укладывался в таймаут интерфейса (ревью 2026-09-05).
export const BULK_APPROVE_MAX = 20

// Таймаут bulk-запроса: общий таймаут клиента 30с меньше реального времени
// партии (паузы 0.5с × документов + проведение каждого в 1С) — пользователь
// видел ошибку сети, когда партия на самом деле выполнялась.
export const BULK_APPROVE_TIMEOUT_MS = 120_000

// ── Documents (все авторизованные сотрудники) ──────────────────────────────

export function fetchApprovals(): Promise<ApprovalDocumentList> {
  return api<ApprovalDocumentList>('/approvals')
}

export function fetchApprovalDetail(uuid: string): Promise<ApprovalDocumentDetail> {
  return api<ApprovalDocumentDetail>(`/approvals/${encodeURIComponent(uuid)}`)
}

export function approveDocument(uuid: string, dto: ApproveIn): Promise<ActionOut> {
  return api<ActionOut>(`/approvals/${encodeURIComponent(uuid)}/approve`, {
    method: 'POST',
    body: dto,
  })
}

export function rejectDocument(uuid: string, dto: RejectIn): Promise<ActionOut> {
  return api<ActionOut>(`/approvals/${encodeURIComponent(uuid)}/reject`, {
    method: 'POST',
    body: dto,
  })
}

export function bulkApprove(uuids: string[]): Promise<BulkApproveOut> {
  return api<BulkApproveOut>('/approvals/bulk-approve', {
    method: 'POST',
    body: { uuids },
    timeout: BULK_APPROVE_TIMEOUT_MS,
  })
}

/** URL скачивания вложения (anchor с target=_blank, как в helpdesk/feedback). */
export function approvalAttachmentUrl(uuid: string, index: number): string {
  return `/api/v1/approvals/${encodeURIComponent(uuid)}/attachments/${index}`
}

// ── Settings (admin) ───────────────────────────────────────────────────────

export function fetchApprovalsSettings(): Promise<ApprovalsSettingsOut> {
  return api<ApprovalsSettingsOut>('/approvals/settings')
}

export function putApprovalsSettings(dto: ApprovalsSettingsIn): Promise<ApprovalsSettingsOut> {
  return api<ApprovalsSettingsOut>('/approvals/settings', { method: 'PUT', body: dto })
}

export function testApprovalsConnection(): Promise<ApprovalsTestResult> {
  return api<ApprovalsTestResult>('/approvals/test', { method: 'POST' })
}
