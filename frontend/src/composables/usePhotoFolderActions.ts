import { ref } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  createFolder,
  deleteFolder,
  moveFolder,
  type Photo,
  type PhotoFolder,
  type PhotoFolderTreeNode,
} from '@/api/photos'
import { usePhotosStore, RECENT_LIMIT } from '@/stores/photos'
import { useConfirmDialog } from '@/composables/useConfirmDialog'

export interface UsePhotoFolderActionsOptions {
  selectedFolderId: Ref<string | null>
  selectedFolder: Ref<PhotoFolder | null>
  photos: Ref<Photo[]>
  loadTree: () => Promise<void>
}

function isDescendant(parent: PhotoFolderTreeNode, targetId: string): boolean {
  if (!parent.children) return false
  for (const child of parent.children) {
    if (child.id === targetId) return true
    if (isDescendant(child, targetId)) return true
  }
  return false
}

export function usePhotoFolderActions(opts: UsePhotoFolderActionsOptions) {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()
  const photosStore = usePhotosStore()

  const folderModalOpen = ref(false)
  const newFolderParent = ref<string | null>(null)
  const newFolderName = ref('')
  const newFolderDesc = ref('')

  const permsModalOpen = ref(false)
  const permsTarget = ref<PhotoFolder | PhotoFolderTreeNode | null>(null)

  const draggingFolderNode = ref<PhotoFolderTreeNode | null>(null)

  function openCreateRoot() {
    newFolderParent.value = null
    newFolderName.value = ''
    newFolderDesc.value = ''
    folderModalOpen.value = true
  }

  function openCreateChild(node: PhotoFolderTreeNode) {
    newFolderParent.value = node.id
    newFolderName.value = ''
    newFolderDesc.value = ''
    folderModalOpen.value = true
  }

  async function submitCreateFolder(): Promise<boolean | void> {
    if (!newFolderName.value.trim()) {
      message.warning(t('photos.folders.nameRequired'))
      return false
    }
    try {
      await createFolder({
        parent_id: newFolderParent.value,
        name: newFolderName.value.trim(),
        description: newFolderDesc.value.trim() || null,
      })
      message.success(t('photos.folders.created'))
      folderModalOpen.value = false
      await opts.loadTree()
    } catch {
      message.error(t('errors.generic'))
      return false
    }
  }

  async function confirmDeleteFolder(node: PhotoFolderTreeNode) {
    const ok = await confirm({
      title: t('photos.folders.deleteTitle'),
      content: t('photos.folders.deleteConfirm', { name: node.name }),
      positiveText: t('common.delete'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    try {
      await deleteFolder(node.id)
      message.success(t('photos.folders.deleted'))
      if (opts.selectedFolderId.value === node.id) {
        opts.selectedFolderId.value = null
        opts.selectedFolder.value = null
        opts.photos.value = []
      }
      await opts.loadTree()
      photosStore.loadRecent(RECENT_LIMIT)
    } catch {
      message.error(t('errors.generic'))
    }
  }

  function openPermissions(node: PhotoFolder | PhotoFolderTreeNode) {
    permsTarget.value = node
    permsModalOpen.value = true
  }

  function onFolderDragStart(node: PhotoFolderTreeNode) {
    draggingFolderNode.value = node
  }

  async function onFolderDrop(targetNode: PhotoFolderTreeNode) {
    const dragged = draggingFolderNode.value
    draggingFolderNode.value = null
    if (!dragged) return
    if (dragged.id === targetNode.id) return

    if (targetNode.permission !== 'manager') {
      message.error(t('photos.folders.cannotMoveNoPermission'))
      return
    }

    if (isDescendant(dragged, targetNode.id)) {
      message.error(t('photos.folders.cannotMoveToDescendant'))
      return
    }

    const ok = await confirm({
      title: t('photos.folders.moveTo', { name: targetNode.name }),
      content: t('photos.folders.moveConfirm', { name: dragged.name, target: targetNode.name }),
      positiveText: t('common.confirm'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    try {
      await moveFolder(dragged.id, targetNode.id)
      message.success(t('photos.folders.moved'))
      await opts.loadTree()
    } catch {
      message.error(t('errors.generic'))
    }
  }

  async function onFolderMoveToRoot(node: PhotoFolderTreeNode) {
    const ok = await confirm({
      title: t('photos.folders.moveToRootTitle'),
      content: t('photos.folders.moveToRootConfirm', { name: node.name }),
      positiveText: t('common.confirm'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    try {
      await moveFolder(node.id, null)
      message.success(t('photos.folders.moved'))
      await opts.loadTree()
    } catch {
      message.error(t('errors.generic'))
    }
  }

  return {
    folderModalOpen,
    newFolderName,
    newFolderDesc,
    permsModalOpen,
    permsTarget,
    openCreateRoot,
    openCreateChild,
    submitCreateFolder,
    confirmDeleteFolder,
    openPermissions,
    onFolderDragStart,
    onFolderDrop,
    onFolderMoveToRoot,
  }
}
