import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import {
  fetchFolder,
  updateFolder,
  type PhotoFolder,
  type PhotoFolderTreeNode,
} from '@/api/photos'
import { usePhotoFolderTreeQuery, usePhotoFolderQuery } from '@/queries/photos'
import { queryKeys } from '@/queries/keys'
import { parseApiError } from '@/utils/parseApiError'

export interface UsePhotoFolderSelectionOptions {
  onAfterSelect?: () => Promise<void> | void
  beforeSelect?: () => void
}

export function usePhotoFolderSelection(opts: UsePhotoFolderSelectionOptions = {}) {
  const { t } = useI18n()
  const message = useMessage()
  const queryClient = useQueryClient()

  const selectedFolderId = ref<string | null>(null)

  const folderTreeQuery = usePhotoFolderTreeQuery()
  const tree = computed<PhotoFolderTreeNode[]>(() => folderTreeQuery.data.value?.items ?? [])
  const loadingTree = computed(() => folderTreeQuery.isLoading.value)

  const folderQuery = usePhotoFolderQuery(selectedFolderId)
  const selectedFolder = computed<PhotoFolder | null>(() => folderQuery.data.value ?? null)

  const editingDescription = ref(false)
  const editDescValue = ref('')

  async function loadTree() {
    try {
      await queryClient.invalidateQueries({ queryKey: queryKeys.photos.folderTree() })
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }

  async function selectFolder(node: PhotoFolderTreeNode) {
    opts.beforeSelect?.()
    selectedFolderId.value = node.id
    try {
      await queryClient.ensureQueryData({
        queryKey: queryKeys.photos.folder(node.id),
        queryFn: () => fetchFolder(node.id),
      })
      await opts.onAfterSelect?.()
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }

  function startEditDescription() {
    editDescValue.value = selectedFolder.value?.description ?? ''
    editingDescription.value = true
  }

  async function saveDescription() {
    if (!selectedFolderId.value) return
    try {
      const updated = await updateFolder(selectedFolderId.value, {
        description: editDescValue.value.trim() || null,
      })
      queryClient.setQueryData(queryKeys.photos.folder(selectedFolderId.value), updated)
      queryClient.invalidateQueries({ queryKey: queryKeys.photos.folderTree() })
      editingDescription.value = false
      message.success(t('photos.folders.descriptionSaved'))
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }

  function flatten(nodes: PhotoFolderTreeNode[]): PhotoFolderTreeNode[] {
    const out: PhotoFolderTreeNode[] = []
    const walk = (ns: PhotoFolderTreeNode[]) => {
      for (const n of ns) {
        out.push(n)
        if (n.children?.length) walk(n.children)
      }
    }
    walk(nodes)
    return out
  }

  async function refreshSelectedFolder() {
    if (!selectedFolderId.value) return
    try {
      await queryClient.invalidateQueries({ queryKey: queryKeys.photos.folder(selectedFolderId.value) })
    } catch {
      // ignore
    }
  }

  return {
    tree,
    loadingTree,
    selectedFolderId,
    selectedFolder,
    editingDescription,
    editDescValue,
    loadTree,
    selectFolder,
    startEditDescription,
    saveDescription,
    flatten,
    refreshSelectedFolder,
  }
}
