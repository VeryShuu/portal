import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchMyShares, fetchRecentPhotos,
  revokePhotoShare, revokeFolderShare,
  fetchFolderTree, fetchFolder,
  fetchFolderPhotos, fetchFolderPhotosFiltered,
  fetchTags, fetchPhotoTags,
  type FolderPhotosParams,
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

export function usePhotoFolderTreeQuery() {
  return useQuery({
    queryKey: queryKeys.photos.folderTree(),
    queryFn: fetchFolderTree,
    staleTime: 30_000,
  })
}

export function usePhotoFolderQuery(folderId: MaybeRefOrGetter<string | null>) {
  return useQuery({
    queryKey: computed(() => queryKeys.photos.folder(toValue(folderId) ?? '')),
    queryFn: () => {
      const fId = toValue(folderId)
      if (!fId) throw new Error('No folder ID provided')
      return fetchFolder(fId)
    },
    enabled: computed(() => !!toValue(folderId)),
    staleTime: 30_000,
  })
}

export function usePhotoFolderPhotosQuery(
  folderId: MaybeRefOrGetter<string | null>,
  params: MaybeRefOrGetter<FolderPhotosParams>
) {
  return useQuery({
    queryKey: computed(() => queryKeys.photos.folderPhotos(toValue(folderId) ?? '', toValue(params))),
    queryFn: async () => {
      const fId = toValue(folderId)
      if (!fId) throw new Error('No folder ID provided')
      const p = toValue(params)
      if (p.tag_id) {
        return fetchFolderPhotosFiltered(fId, p)
      }
      return fetchFolderPhotos(fId, p)
    },
    enabled: computed(() => !!toValue(folderId)),
    staleTime: 30_000,
  })
}

export function usePhotoAllTagsQuery() {
  return useQuery({
    queryKey: queryKeys.photos.tags(),
    queryFn: () => fetchTags().then(res => res.items),
    staleTime: 60_000,
  })
}

export function usePhotoTagsQuery(photoId: MaybeRefOrGetter<string | null>) {
  return useQuery({
    queryKey: computed(() => queryKeys.photos.photoTags(toValue(photoId) ?? '')),
    queryFn: () => {
      const pId = toValue(photoId)
      if (!pId) throw new Error('No photo ID provided')
      return fetchPhotoTags(pId)
    },
    enabled: computed(() => !!toValue(photoId)),
    staleTime: 30_000,
  })
}
