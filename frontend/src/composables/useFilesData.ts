import { computed, reactive } from 'vue'
import { storeToRefs } from 'pinia'
import { useQueryClient } from '@tanstack/vue-query'
import {
  type FileFolderPublic,
  type FileFolderTreeNode,
  type NCItem,
  type NcSyncReport,
} from '../api/files'
import { useAuthStore } from '../stores/auth'
import { useFilesStore } from '../stores/files'
import { queryKeys } from '../queries/keys'
import {
  useFolderTreeQuery,
  useFolderDetailQuery,
  useCreateFolderMutation,
  useDeleteFolderMutation,
  useSyncFromNcMutation,
} from '../queries/files'

export interface UseFilesData {
  readonly tree: FileFolderTreeNode[]
  readonly loadingTree: boolean
  selectedFolderId: string | null
  readonly currentFolder: FileFolderPublic | null
  readonly ncItems: NCItem[]
  readonly breadcrumbs: FileFolderPublic[]
  readonly loadingDetail: boolean
  readonly syncing: boolean
  readonly canUpload: boolean
  readonly canManage: boolean
  readonly canEdit: boolean
  findNodeById(id: string, nodes?: FileFolderTreeNode[]): FileFolderTreeNode | null
  findNodeByNcPath(path: string, nodes?: FileFolderTreeNode[]): FileFolderTreeNode | null
  selectFolder(id: string | null): void
  loadTree(): Promise<void>
  loadDetail(folderId: string): Promise<void>
  createFolder(input: { name: string; parent_id: string | null; description: string | null }): Promise<void>
  deleteFolder(id: string): Promise<void>
  syncFromNextcloud(): Promise<NcSyncReport>
  refreshCurrent(): Promise<void>
}

export function useFilesData(): UseFilesData {
  const auth = useAuthStore()
  const store = useFilesStore()
  const qc = useQueryClient()

  const { selectedFolderId } = storeToRefs(store)

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
    store.selectFolder(id)
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
    if (store.selectedFolderId === id) store.selectFolder(null)
  }

  async function syncFromNextcloud(): Promise<NcSyncReport> {
    return syncMutation.mutateAsync()
  }

  async function refreshCurrent(): Promise<void> {
    if (store.selectedFolderId) {
      await qc.invalidateQueries({ queryKey: queryKeys.files.folder(store.selectedFolderId) })
    }
  }

  return reactive({
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
    selectFolder,
    loadTree,
    loadDetail,
    createFolder,
    deleteFolder,
    syncFromNextcloud,
    refreshCurrent,
  }) as unknown as UseFilesData
}
