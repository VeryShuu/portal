import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchFolderTree, fetchFolderDetail,
  createFolder as apiCreateFolder,
  deleteFolder as apiDeleteFolder,
  syncFromNextcloud as apiSyncFromNextcloud,
  type FileFolderPublic,
  type FileFolderTreeNode,
  type NCItem,
  type NcSyncReport,
} from '../api/files'
import { useAuthStore } from './auth'
import { queryKeys } from '../queries/keys'

export const useFilesStore = defineStore('files', () => {
  const auth = useAuthStore()
  const qc = useQueryClient()

  const selectedFolderId = ref<string | null>(null)

  const { data: treeData, isLoading: loadingTree } = useQuery({
    queryKey: queryKeys.files.tree(),
    queryFn: () => fetchFolderTree(),
    staleTime: 60_000,
  })

  const tree = computed<FileFolderTreeNode[]>(() => treeData.value?.items ?? [])

  const { data: detailData, isLoading: loadingDetail } = useQuery({
    queryKey: computed(() => queryKeys.files.folder(selectedFolderId.value ?? '')),
    queryFn: () => fetchFolderDetail(selectedFolderId.value!),
    staleTime: 30_000,
    enabled: computed(() => !!selectedFolderId.value),
  })

  const currentFolder = computed<FileFolderPublic | null>(() => detailData.value?.folder ?? null)
  const ncItems = computed<NCItem[]>(() => detailData.value?.items ?? [])
  const breadcrumbs = computed<FileFolderPublic[]>(() => detailData.value?.breadcrumbs ?? [])

  const canUpload = computed(() => {
    const p = currentFolder.value?.permission
    return p === 'editor' || p === 'manager' || auth.isAdmin
  })

  const canManage = computed(() => {
    const p = currentFolder.value?.permission
    return p === 'manager' || auth.isAdmin
  })

  const createFolderMutation = useMutation({
    mutationFn: (input: { name: string; parent_id: string | null; description: string | null }) =>
      apiCreateFolder(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.files.tree() })
    },
  })

  const deleteFolderMutation = useMutation({
    mutationFn: (id: string) => apiDeleteFolder(id),
    onSuccess: (_: void, id: string) => {
      qc.invalidateQueries({ queryKey: queryKeys.files.tree() })
      qc.removeQueries({ queryKey: queryKeys.files.folder(id) })
    },
  })

  const syncMutation = useMutation({
    mutationFn: () => apiSyncFromNextcloud(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.files.all })
    },
  })

  const syncing = computed(() => syncMutation.isPending.value)

  function findNodeById(id: string, nodes: FileFolderTreeNode[] = tree.value): FileFolderTreeNode | null {
    for (const n of nodes) {
      if (n.id === id) return n
      const child = findNodeById(id, n.children)
      if (child) return child
    }
    return null
  }

  function findNodeByNcPath(path: string, nodes: FileFolderTreeNode[] = tree.value): FileFolderTreeNode | null {
    for (const n of nodes) {
      if (n.nc_path === path) return n
      const child = findNodeByNcPath(path, n.children)
      if (child) return child
    }
    return null
  }

  function selectFolder(id: string | null): void {
    selectedFolderId.value = id
  }

  async function loadTree(): Promise<void> {
    await qc.invalidateQueries({ queryKey: queryKeys.files.tree() })
  }

  async function loadDetail(folderId: string): Promise<void> {
    await qc.invalidateQueries({ queryKey: queryKeys.files.folder(folderId) })
  }

  async function createFolder(input: { name: string; parent_id: string | null; description: string | null }): Promise<void> {
    await createFolderMutation.mutateAsync(input)
  }

  async function deleteFolder(id: string): Promise<void> {
    await deleteFolderMutation.mutateAsync(id)
    if (selectedFolderId.value === id) selectedFolderId.value = null
  }

  async function syncFromNextcloud(): Promise<NcSyncReport> {
    return syncMutation.mutateAsync()
  }

  async function refreshCurrent(): Promise<void> {
    if (selectedFolderId.value) {
      await qc.invalidateQueries({ queryKey: queryKeys.files.folder(selectedFolderId.value) })
    }
  }

  return {
    tree,
    loadingTree,
    selectedFolderId,
    currentFolder,
    ncItems,
    breadcrumbs,
    loadingDetail,
    syncing,
    canUpload,
    canManage,
    findNodeById,
    findNodeByNcPath,
    loadTree,
    loadDetail,
    selectFolder,
    createFolder,
    deleteFolder,
    syncFromNextcloud,
    refreshCurrent,
  }
})
