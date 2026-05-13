import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useQueryClient } from '@tanstack/vue-query'
import {
  type FileFolderPublic,
  type FileFolderTreeNode,
  type NCItem,
  type NcSyncReport,
} from '../api/files'
import { useAuthStore } from './auth'
import { queryKeys } from '../queries/keys'
import {
  useFolderTreeQuery,
  useFolderDetailQuery,
  useCreateFolderMutation,
  useDeleteFolderMutation,
  useSyncFromNcMutation,
} from '../queries/files'

export const useFilesStore = defineStore('files', () => {
  const auth = useAuthStore()
  const qc = useQueryClient()

  const selectedFolderId = ref<string | null>(null)

  const treeQuery = useFolderTreeQuery()
  const treeData = treeQuery.data
  const loadingTree = treeQuery.isLoading

  const tree = computed<FileFolderTreeNode[]>(() => treeData.value?.items ?? [])

  const detailQuery = useFolderDetailQuery(selectedFolderId)
  const detailData = detailQuery.data
  const loadingDetail = detailQuery.isLoading

  const currentFolder = computed<FileFolderPublic | null>(() => detailData.value?.folder ?? null)
  const ncItems = computed<NCItem[]>(() => detailData.value?.items ?? [])
  const breadcrumbs = computed<FileFolderPublic[]>(() => detailData.value?.breadcrumbs ?? [])

  const canEdit = computed(() => {
    const p = currentFolder.value?.permission
    return p === 'editor' || p === 'manager' || auth.isAdmin
  })

  const canUpload = canEdit

  const canManage = computed(() => {
    const p = currentFolder.value?.permission
    return p === 'manager' || auth.isAdmin
  })

  const createFolderMutation = useCreateFolderMutation()
  const deleteFolderMutation = useDeleteFolderMutation()
  const syncMutation = useSyncFromNcMutation()

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
    canEdit,
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
