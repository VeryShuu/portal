import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchMailingRecipients,
  createMailingRecipient,
  updateMailingRecipient,
  deleteMailingRecipient,
  type CreateMailingRecipientDto,
  type UpdateMailingRecipientDto,
} from '../api/mailingRecipients'
import { queryKeys } from './keys'

export function useMailingRecipientsQuery(
  params: MaybeRefOrGetter<Parameters<typeof fetchMailingRecipients>[0]> = {},
  options?: { enabled?: MaybeRefOrGetter<boolean> },
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.mailingRecipients.list(toValue(params) as Record<string, unknown>),
    ),
    queryFn: () => fetchMailingRecipients(toValue(params) ?? {}),
    staleTime: 60_000,
    enabled: computed(() => (options?.enabled !== undefined ? toValue(options.enabled) : true)),
  })
}

export function useCreateMailingRecipientMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: CreateMailingRecipientDto) => createMailingRecipient(dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mailingRecipients.all })
    },
  })
}

export function useUpdateMailingRecipientMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dto }: { id: string; dto: UpdateMailingRecipientDto }) =>
      updateMailingRecipient(id, dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mailingRecipients.all })
    },
  })
}

export function useDeleteMailingRecipientMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteMailingRecipient(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mailingRecipients.all })
    },
  })
}
