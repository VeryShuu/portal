/**
 * TanStack Query composables для ERP-синхронизации (docs/erp-sync.md).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import type { MaybeRefOrGetter } from 'vue'
import { computed, toValue } from 'vue'
import { queryKeys } from './keys'
import {
  fetchErpSyncRuns,
  fetchErpSyncSettings,
  putErpSyncSettings,
  type ErpSyncRunList,
  type ErpSyncSettingsIn,
} from '../api/erpSync'

export function useErpSyncSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.erpSync.settings(),
    queryFn: () => fetchErpSyncSettings(),
    staleTime: 30_000,
  })
}

export function usePutErpSyncSettingsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: ErpSyncSettingsIn) => putErpSyncSettings(dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.erpSync.settings() }),
  })
}

export interface ErpSyncRunsParams {
  limit?: number
  offset?: number
}

export function useErpSyncRunsQuery(params: MaybeRefOrGetter<ErpSyncRunsParams>) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.erpSync.runs(toValue(params) as Record<string, unknown>),
    ),
    queryFn: () => fetchErpSyncRuns(toValue(params) ?? {}),
    staleTime: 0,
    placeholderData: (prev: ErpSyncRunList | undefined) => prev,
  })
}
