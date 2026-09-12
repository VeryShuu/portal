/**
 * API-клиент approvals (src/api/approvals.ts): эндпоинты, методы, тела.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const apiMock = vi.fn().mockResolvedValue({})

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...(args as [string, unknown?])),
}))

import {
  fetchApprovals,
  fetchApprovalDetail,
  approveDocument,
  rejectDocument,
  bulkApprove,
  approvalAttachmentUrl,
  fetchApprovalsSettings,
  putApprovalsSettings,
  testApprovalsConnection,
  BULK_APPROVE_TIMEOUT_MS,
} from '../../src/api/approvals'

describe('src/api/approvals', () => {
  beforeEach(() => {
    apiMock.mockClear().mockResolvedValue({})
  })

  it('fetchApprovals — GET /approvals', async () => {
    await fetchApprovals()
    expect(apiMock).toHaveBeenCalledWith('/approvals')
  })

  it('fetchApprovalDetail — экранирует uuid', async () => {
    await fetchApprovalDetail('g/1')
    expect(apiMock).toHaveBeenCalledWith('/approvals/g%2F1')
  })

  it('approveDocument — POST c телом', async () => {
    const dto = { comment: 'ок', manager_guid: 'm-1' }
    await approveDocument('g-1', dto)
    expect(apiMock).toHaveBeenCalledWith('/approvals/g-1/approve', { method: 'POST', body: dto })
  })

  it('rejectDocument — POST c комментарием', async () => {
    await rejectDocument('g-1', { comment: 'брак' })
    expect(apiMock).toHaveBeenCalledWith('/approvals/g-1/reject', {
      method: 'POST',
      body: { comment: 'брак' },
    })
  })

  it('bulkApprove — POST с удлинённым таймаутом (партия > 30с общего)', async () => {
    await bulkApprove(['a', 'b'])
    expect(apiMock).toHaveBeenCalledWith('/approvals/bulk-approve', {
      method: 'POST',
      body: { uuids: ['a', 'b'] },
      timeout: BULK_APPROVE_TIMEOUT_MS,
    })
    expect(BULK_APPROVE_TIMEOUT_MS).toBe(120_000)
  })

  it('attachmentUrl — anchor-ссылка как в helpdesk', () => {
    expect(approvalAttachmentUrl('g 1', 2)).toBe('/api/v1/approvals/g%201/attachments/2')
  })

  it('settings: GET/PUT + test', async () => {
    await fetchApprovalsSettings()
    expect(apiMock).toHaveBeenLastCalledWith('/approvals/settings')
    await putApprovalsSettings({ base_url: 'https://erp.test/x', token_base_url: '', auth_username: 'Portal' })
    expect(apiMock).toHaveBeenLastCalledWith('/approvals/settings', {
      method: 'PUT',
      body: { base_url: 'https://erp.test/x', token_base_url: '', auth_username: 'Portal' },
    })
    await testApprovalsConnection()
    expect(apiMock).toHaveBeenLastCalledWith('/approvals/test', { method: 'POST' })
  })
})
