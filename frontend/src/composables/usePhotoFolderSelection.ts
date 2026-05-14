import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  fetchFolder,
  fetchFolderTree,
  updateFolder,
  type PhotoFolder,
  type PhotoFolderTreeNode,
} from '@/api/photos'

export interface UsePhotoFolderSelectionOptions {
  onAfterSelect?: () => Promise<void> | void
  beforeSelect?: () => void
}

export function usePhotoFolderSelection(opts: UsePhotoFolderSelectionOptions = {}) {
  const { t } = useI18n()
  const message = useMessage()

  const tree = ref<PhotoFolderTreeNode[]>([])
  const loadingTree = ref(false)
  const selectedFolderId = ref<string | null>(null)
  const selectedFolder = ref<PhotoFolder | null>(null)

  const editingDescription = ref(false)
  const editDescValue = ref('')

  async function loadTree() {
    loadingTree.value = true
    try {
      const data = await fetchFolderTree()
      tree.value = data.items
    } catch {
      message.error(t('errors.generic'))
    } finally {
      loadingTree.value = false
    }
  }

  async function selectFolder(node: PhotoFolderTreeNode) {
    opts.beforeSelect?.()
    selectedFolderId.value = node.id
    try {
      selectedFolder.value = await fetchFolder(node.id)
      await opts.onAfterSelect?.()
    } catch {
      message.error(t('errors.generic'))
    }
  }

  function startEditDescription() {
    editDescValue.value = selectedFolder.value?.description ?? ''
    editingDescription.value = true
  }

  async function saveDescription() {
    if (!selectedFolder.value) return
    try {
      const updated = await updateFolder(selectedFolder.value.id, {
        description: editDescValue.value.trim() || null,
      })
      selectedFolder.value = updated
      editingDescription.value = false
      message.success(t('photos.folders.descriptionSaved'))
    } catch {
      message.error(t('errors.generic'))
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
  }
}
