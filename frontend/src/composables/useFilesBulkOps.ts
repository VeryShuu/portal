import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, type TreeOption } from 'naive-ui'
import { useConfirmDialog } from './useConfirmDialog'
import { useFilesData } from './useFilesData'
import { useAuthStore } from '../stores/auth'
import {
  BULK_DOWNLOAD_LIMIT,
  bulkDeleteFiles,
  bulkMoveFiles,
  downloadFile,
  type FileFolderTreeNode,
} from '../api/files'

export function useFilesBulkOps(args: {
  folderId: Ref<string | null>
  selectedFilenames: ComputedRef<string[]>
  clearSelection: () => void
  onAfterMutation: () => Promise<void> | void
}): {
  bulkBusy: Ref<boolean>
  showMoveModal: Ref<boolean>
  moveTargetKey: Ref<string | null>
  moveTreeData: ComputedRef<TreeOption[]>
  bulkDownload(): Promise<void>
  confirmBulkDelete(): Promise<void>
  openMoveModal(): void
  onMoveTargetSelect(keys: Array<string | number>): void
  submitBulkMove(): Promise<void>
  canMoveTo(node: FileFolderTreeNode): boolean
} {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()
  const store = useFilesData()
  const auth = useAuthStore()

  const { folderId, selectedFilenames, clearSelection, onAfterMutation } = args

  const bulkBusy = ref(false)
  const showMoveModal = ref(false)
  const moveTargetKey = ref<string | null>(null)

  function canMoveTo(node: FileFolderTreeNode): boolean {
    return node.permission === 'editor' || node.permission === 'manager' || auth.isAdmin
  }

  const moveTreeData = computed<TreeOption[]>(() => {
    function map(nodes: FileFolderTreeNode[]): TreeOption[] {
      return nodes
        .map((n) => {
          const opt: TreeOption = {
            key: n.id,
            label: n.name,
            disabled: n.id === folderId.value || !canMoveTo(n),
            children: map(n.children),
          }
          return opt
        })
        .filter((opt) => !opt.disabled || (Array.isArray(opt.children) && opt.children.length > 0))
    }
    return map(store.tree)
  })

  async function bulkDownload() {
    if (!folderId.value) return
    const names = selectedFilenames.value
    if (!names.length) return
    if (names.length > BULK_DOWNLOAD_LIMIT) {
      message.warning(t('files.bulk.downloadLimit'))
      return
    }
    message.info(t('files.bulk.downloadStarted', { n: names.length }))
    for (const name of names) {
      const a = document.createElement('a')
      a.href = downloadFile(folderId.value, name)
      a.download = name
      a.style.display = 'none'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      await new Promise((resolve) => setTimeout(resolve, 150))
    }
  }

  async function confirmBulkDelete() {
    const names = selectedFilenames.value
    if (!names.length) return
    const ok = await confirm({
      title: t('files.bulk.deleteTitle'),
      content: t('files.bulk.deleteConfirm', { n: names.length }),
      positiveText: t('common.delete'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    bulkBusy.value = true
    try {
      const result = await bulkDeleteFiles(folderId.value!, names)
      if (result.failed.length === 0) {
        message.success(t('files.bulk.deleteSuccess', { n: result.deleted.length }))
      } else {
        message.warning(t('files.bulk.deletePartial', { deleted: result.deleted.length, failed: result.failed.length }))
      }
      clearSelection()
      await onAfterMutation()
    } catch (err) {
      const status = (err as { status?: number })?.status
      if (status === 409) {
        message.warning(t('files.error.bulkInProgress'))
      } else {
        message.error(t('files.error.bulkDelete'))
      }
    } finally {
      bulkBusy.value = false
    }
  }

  function openMoveModal() {
    if (!selectedFilenames.value.length) return
    moveTargetKey.value = null
    showMoveModal.value = true
  }

  function onMoveTargetSelect(keys: Array<string | number>) {
    if (!keys.length) {
      moveTargetKey.value = null
      return
    }
    const id = String(keys[0])
    const node = store.findNodeById(id)
    if (!node || !canMoveTo(node) || id === folderId.value) return
    moveTargetKey.value = id
  }

  async function submitBulkMove() {
    if (!folderId.value || !moveTargetKey.value) return
    const names = selectedFilenames.value
    if (!names.length) return
    bulkBusy.value = true
    try {
      const targetId = moveTargetKey.value
      const result = await bulkMoveFiles(folderId.value, names, targetId)
      if (result.failed.length === 0) {
        message.success(t('files.bulk.moveSuccess', { n: result.moved.length }))
      } else {
        message.warning(t('files.bulk.movePartial', { moved: result.moved.length, failed: result.failed.length }))
      }
      showMoveModal.value = false
      clearSelection()
      await onAfterMutation()
    } catch (err) {
      const status = (err as { status?: number })?.status
      if (status === 409) {
        message.warning(t('files.error.bulkInProgress'))
      } else {
        message.error(t('files.error.bulkMove'))
      }
    } finally {
      bulkBusy.value = false
    }
  }

  return {
    bulkBusy,
    showMoveModal,
    moveTargetKey,
    moveTreeData,
    bulkDownload,
    confirmBulkDelete,
    openMoveModal,
    onMoveTargetSelect,
    submitBulkMove,
    canMoveTo,
  }
}
