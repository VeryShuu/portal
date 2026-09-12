/**
 * TanStack Query composables модуля «Согласование документов»
 * (docs/approvals.md).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import {
  approveDocument,
  bulkApprove,
  fetchApprovalDetail,
  fetchApprovals,
  fetchApprovalsSettings,
  putApprovalsSettings,
  rejectDocument,
  type ApprovalsSettingsIn,
} from '../api/approvals'
import { queryKeys } from './keys'

export function useApprovalsQuery() {
  return useQuery({
    queryKey: queryKeys.approvals.list(),
    queryFn: () => fetchApprovals(),
    staleTime: 30_000,
  })
}

export function useApprovalDetailQuery(uuid: MaybeRefOrGetter<string | null>) {
  // uuid реактивен: queryKey/enabled обязаны быть computed — статическое
  // значение фиксируется на момент создания (drawer ещё закрыт, uuid=null)
  // и запрос никогда не выполнится (e2e-регрессия approvals.spec).
  return useQuery({
    queryKey: computed(() => queryKeys.approvals.document(toValue(uuid) ?? '')),
    queryFn: () => fetchApprovalDetail(toValue(uuid) as string),
    enabled: computed(() => !!toValue(uuid)),
    staleTime: 0,
  })
}

export function useApproveMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      uuid,
      dto,
    }: {
      uuid: string
      dto: { comment: string; manager_guid?: string | null }
    }) => approveDocument(uuid, dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.approvals.list() }),
  })
}

export function useRejectMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ uuid, dto }: { uuid: string; dto: { comment: string } }) =>
      rejectDocument(uuid, dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.approvals.list() }),
  })
}

export function useBulkApproveMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (uuids: string[]) => bulkApprove(uuids),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.approvals.list() }),
  })
}

export function useApprovalsSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.approvals.settings(),
    queryFn: () => fetchApprovalsSettings(),
    staleTime: 30_000,
  })
}

export function usePutApprovalsSettingsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: ApprovalsSettingsIn) => putApprovalsSettings(dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.approvals.settings() }),
  })
}
