/**
 * queries/approvals.ts: комбинирование queryKeys.approvals.* и api-функций
 * ( TanStack замокан — проверяем wiring: ключи, queryFn, invalidations ).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, toValue } from 'vue'

const capturedQueries: { queryKey: unknown; queryFn: () => Promise<unknown>; enabled?: unknown }[] = []
const capturedMutations: { mutationFn: (args: unknown) => Promise<unknown> }[] = []
const invalidated: unknown[] = []
const qc = { invalidateQueries: vi.fn((arg: { queryKey: unknown }) => invalidated.push(arg.queryKey)) }

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: Record<string, unknown>) => {
    capturedQueries.push(opts as never)
    return { data: ref(undefined), isLoading: ref(false), refetch: vi.fn() }
  }),
  useMutation: vi.fn(
    (opts: {
      mutationFn: (args: unknown) => Promise<unknown>
      onSuccess?: (data: unknown) => void
    }) => {
      capturedMutations.push(opts)
      return {
        // Воспроизводим семантику: mutateAsync вызывает onSuccess после успеха.
        mutateAsync: (args: unknown) =>
          opts.mutationFn(args).then((data: unknown) => {
            opts.onSuccess?.(data)
            return data
          }),
        isPending: ref(false),
      }
    },
  ),
  useQueryClient: vi.fn(() => qc),
}))

vi.mock('../../src/api/approvals', () => ({
  fetchApprovals: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchApprovalDetail: vi.fn().mockResolvedValue({ guid: 'g-1' }),
  approveDocument: vi.fn().mockResolvedValue({ ok: true }),
  rejectDocument: vi.fn().mockResolvedValue({ ok: true }),
  bulkApprove: vi.fn().mockResolvedValue({ results: [], approved: 0, failed: 0 }),
  fetchApprovalsSettings: vi.fn().mockResolvedValue({ base_url: '' }),
  putApprovalsSettings: vi.fn().mockResolvedValue({}),
}))

import {
  useApprovalDetailQuery,
  useApprovalsQuery,
  useApprovalsSettingsQuery,
  useApproveMutation,
  useBulkApproveMutation,
  usePutApprovalsSettingsMutation,
  useRejectMutation,
} from '../../src/queries/approvals'

describe('src/queries/approvals', () => {
  beforeEach(() => {
    capturedQueries.length = 0
    capturedMutations.length = 0
    invalidated.length = 0
    vi.clearAllMocks()
  })

  it('useApprovalsQuery: ключ list + queryFn дергает API', async () => {
    const q = useApprovalsQuery()
    const opts = capturedQueries[0]
    expect(toValue(opts.queryKey)).toEqual(['approvals', 'list'])
    await opts.queryFn()
    const { fetchApprovals } = await import('../../src/api/approvals')
    expect(fetchApprovals).toHaveBeenCalled()
    expect(q).toBeDefined()
  })

  it('useApprovalDetailQuery: enabled по uuid, ключ document', async () => {
    useApprovalDetailQuery(() => null)
    expect(toValue(capturedQueries[0].enabled)).toBe(false)
    useApprovalDetailQuery(() => 'g-9')
    expect(toValue(capturedQueries[1].enabled)).toBe(true)
    expect(toValue(capturedQueries[1].queryKey)).toEqual(['approvals', 'document', 'g-9'])
    await capturedQueries[1].queryFn()
    const { fetchApprovalDetail } = await import('../../src/api/approvals')
    expect(fetchApprovalDetail).toHaveBeenCalledWith('g-9')
  })

  it('useApprovalDetailQuery: РЕАКТИВНЫЙ переход null → uuid включает запрос', async () => {
    // Регрессия e2e: статичный enabled=false навсегда — drawer не грузил карточку.
    const { ref } = await import('vue')
    const uuid = ref<string | null>(null)
    useApprovalDetailQuery(() => uuid.value)
    expect(toValue(capturedQueries[0].enabled)).toBe(false)

    uuid.value = 'g-1'
    expect(toValue(capturedQueries[0].enabled)).toBe(true)
    expect(toValue(capturedQueries[0].queryKey)).toEqual(['approvals', 'document', 'g-1'])
    await capturedQueries[0].queryFn()
    const { fetchApprovalDetail } = await import('../../src/api/approvals')
    expect(fetchApprovalDetail).toHaveBeenCalledWith('g-1')
  })

  it('мутации: invalidate list после успеха', async () => {
    const approve = useApproveMutation()
    const reject = useRejectMutation()
    const bulk = useBulkApproveMutation()
    expect(capturedMutations.length).toBe(3)
    await approve.mutateAsync({ uuid: 'a', dto: { comment: '' } })
    await reject.mutateAsync({ uuid: 'a', dto: { comment: 'x' } })
    await bulk.mutateAsync(['a'])
    const { approveDocument, rejectDocument, bulkApprove } = await import('../../src/api/approvals')
    expect(approveDocument).toHaveBeenCalledWith('a', { comment: '' })
    expect(rejectDocument).toHaveBeenCalledWith('a', { comment: 'x' })
    expect(bulkApprove).toHaveBeenCalledWith(['a'])
    expect(invalidated).toEqual([
      ['approvals', 'list'],
      ['approvals', 'list'],
      ['approvals', 'list'],
    ])
  })

  it('settings: query + mutation invalidates settings', async () => {
    useApprovalsSettingsQuery()
    expect(toValue(capturedQueries[0].queryKey)).toEqual(['approvals', 'settings'])
    const put = usePutApprovalsSettingsMutation()
    await put.mutateAsync({ base_url: 'https://x', token_base_url: '', auth_username: 'Portal' })
    const { putApprovalsSettings } = await import('../../src/api/approvals')
    expect(putApprovalsSettings).toHaveBeenCalled()
    expect(invalidated).toEqual([['approvals', 'settings']])
  })
})
