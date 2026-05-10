import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchMyShares, fetchRecentPhotos,
  revokePhotoShare, revokeFolderShare,
} from '../api/photos'
import { queryKeys } from './keys'

export function useMySharesQuery() {
  return useQuery({
    queryKey: queryKeys.photos.myShares(),
    queryFn: fetchMyShares,
    staleTime: 60_000,
  })
}

export function useRecentPhotosQuery(limit: MaybeRefOrGetter<number> = 8) {
  return useQuery({
    queryKey: computed(() => queryKeys.photos.recent(toValue(limit))),
    queryFn: () => fetchRecentPhotos(toValue(limit)),
    staleTime: 120_000,
  })
}

export function useRevokePhotoShareMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tokenId: string) => revokePhotoShare(tokenId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.photos.myShares() })
    },
  })
}

export function useRevokeFolderShareMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tokenId: string) => revokeFolderShare(tokenId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.photos.myShares() })
    },
  })
}
