import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchSignatureConfig,
  fetchSignatureSettings,
  updateSignatureSettings,
  type SignatureSettings,
} from '../api/signature'
import { queryKeys } from './keys'

export function useSignatureConfigQuery(
  options: { enabled?: MaybeRefOrGetter<boolean> } = {},
) {
  return useQuery({
    queryKey: queryKeys.signature.config(),
    queryFn: () => fetchSignatureConfig(),
    staleTime: 60_000,
    enabled: computed(() => (options.enabled === undefined ? true : !!toValue(options.enabled))),
  })
}

export function useSignatureSettingsQuery(
  options: { enabled?: MaybeRefOrGetter<boolean> } = {},
) {
  return useQuery({
    queryKey: queryKeys.signature.settings(),
    queryFn: () => fetchSignatureSettings(),
    staleTime: 60_000,
    enabled: computed(() => (options.enabled === undefined ? true : !!toValue(options.enabled))),
  })
}

export function useUpdateSignatureSettingsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SignatureSettings) => updateSignatureSettings(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.signature.settings() })
      qc.invalidateQueries({ queryKey: queryKeys.signature.config() })
    },
  })
}
