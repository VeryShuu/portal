/**
 * TanStack Query composables для интеграции Directum (docs/directum.md).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import type { MaybeRefOrGetter } from 'vue'
import { computed, toValue } from 'vue'
import { queryKeys } from './keys'
import {
  fetchDirectumRuns,
  fetchDirectumSettings,
  putDirectumSettings,
  type DirectumRunList,
  type DirectumSettingsIn,
} from '../api/directum'

export function useDirectumSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.directum.settings(),
    queryFn: () => fetchDirectumSettings(),
    staleTime: 30_000,
  })
}

export function usePutDirectumSettingsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: DirectumSettingsIn) => putDirectumSettings(dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.directum.settings() }),
  })
}

export interface DirectumRunsParams {
  limit?: number
  offset?: number
}

export function useDirectumRunsQuery(params: MaybeRefOrGetter<DirectumRunsParams>) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.directum.runs(toValue(params) as Record<string, unknown>),
    ),
    queryFn: () => fetchDirectumRuns(toValue(params) ?? {}),
    staleTime: 0,
    placeholderData: (prev: DirectumRunList | undefined) => prev,
  })
}
