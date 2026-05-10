import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchFolderTree, fetchFolderDetail,
  createFolder, deleteFolder, syncFromNextcloud,
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
