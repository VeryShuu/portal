import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchFolderTree, fetchFolderDetail,
  createFolder, deleteFolder, syncFromNextcloud,
  createFileShare, fetchFileShares, revokeFileShare,
  fetchMyShares, fetchSharedWithMe, fetchAdminShares,
  type FileFolderPublic,
} from '../api/files'
import { queryKeys } from './keys'

export function useFolderTreeQuery() {
  return useQuery({
    queryKey: queryKeys.files.tree(),
    queryFn: () => fetchFolderTree(),
    staleTime: 60_000,
  })
}

export function useFolderDetailQuery(
  folderId: MaybeRefOrGetter<string | null>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.files.folder(toValue(folderId) ?? '')),
    queryFn: () => fetchFolderDetail(toValue(folderId)!),
    staleTime: 30_000,
    enabled: computed(() => !!toValue(folderId)),
  })
}

export function useCreateFolderMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { name: string; parent_id: string | null; description: string | null }) =>
      createFolder(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.files.tree() })
    },
  })
}

export function useDeleteFolderMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteFolder(id),
    onSuccess: (_: void, id: string) => {
      qc.invalidateQueries({ queryKey: queryKeys.files.tree() })
      qc.removeQueries({ queryKey: queryKeys.files.folder(id) })
    },
  })
}

export function useSyncFromNcMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => syncFromNextcloud(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.files.all })
    },
  })
}

export function useFileSharesQuery(
  folderId: MaybeRefOrGetter<string | null>,
  filename: MaybeRefOrGetter<string | null>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.files.fileShares(toValue(folderId) ?? '', toValue(filename) ?? '')
    ),
    queryFn: () => fetchFileShares(toValue(folderId)!, toValue(filename)!),
    enabled: computed(() => !!toValue(folderId) && !!toValue(filename)),
    staleTime: 10_000,
  })
}

export function useCreateFileShareMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: {
      folderId: string
      filename: string
      body: {
        subject_type: 'user' | 'group'
        subject_id: string
        subject_name: string
        permission: 'viewer' | 'editor'
        expires_in_days?: number | null
      }
    }) => createFileShare(input.folderId, input.filename, input.body),
    onSuccess: (_, input) => {
      qc.invalidateQueries({ queryKey: queryKeys.files.fileShares(input.folderId, input.filename) })
      qc.invalidateQueries({ queryKey: queryKeys.files.myShares() })
    },
  })
}

export function useRevokeFileShareMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { folderId: string; filename: string; shareId: string }) =>
      revokeFileShare(input.folderId, input.filename, input.shareId),
    onSuccess: (_, input) => {
      qc.invalidateQueries({ queryKey: queryKeys.files.fileShares(input.folderId, input.filename) })
      qc.invalidateQueries({ queryKey: queryKeys.files.myShares() })
    },
  })
}

export function useMyFileSharesQuery() {
  return useQuery({
    queryKey: queryKeys.files.myShares(),
    queryFn: () => fetchMyShares(),
    staleTime: 30_000,
  })
}

export function useSharedWithMeQuery() {
  return useQuery({
    queryKey: queryKeys.files.sharedWithMe(),
    queryFn: () => fetchSharedWithMe(),
    staleTime: 30_000,
  })
}

export function useAdminSharesQuery(
  params: MaybeRefOrGetter<{
    subject_id?: string
    folder_id?: string
    active_only?: boolean
    limit?: number
    offset?: number
  }>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.files.adminShares(toValue(params))),
    queryFn: () => fetchAdminShares(toValue(params)),
    staleTime: 15_000,
  })
}

export function useUpdateFolderDetailCache() {
  const qc = useQueryClient()
  return (folderId: string, updater: (prev: FileFolderPublic | undefined) => FileFolderPublic) => {
    const key = queryKeys.files.folder(folderId)
    const prev = qc.getQueryData<Awaited<ReturnType<typeof fetchFolderDetail>>>(key)
    if (prev) {
      qc.setQueryData(key, { ...prev, folder: updater(prev.folder) })
    }
  }
}
