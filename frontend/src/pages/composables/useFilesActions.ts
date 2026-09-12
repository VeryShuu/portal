import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useConfirmDialog } from '../../composables/useConfirmDialog'
import { useFilesData } from '../../composables/useFilesData'
import { deleteFile, isPreviewableImage, previewFile, type NCItem } from '../../api/files'

type FilesStore = ReturnType<typeof useFilesData>

export function useFilesActions(store: FilesStore) {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()

  const showShareModal = ref(false)
  const shareFilename = ref<string | null>(null)
  const showImagePreview = ref(false)
  const previewInitialIndex = ref(0)
  const previewImages = computed(() => store.ncItems.filter(isPreviewableImage))

  function onShareFile(item: NCItem) {
    shareFilename.value = item.name
    showShareModal.value = true
  }

  function onPreviewImage(item: NCItem) {
    const idx = previewImages.value.findIndex((x: NCItem) => x.name === item.name)
    if (idx >= 0) {
      previewInitialIndex.value = idx
      showImagePreview.value = true
    }
  }

  function onPreviewPdf(item: NCItem) {
    if (store.selectedFolderId) {
      window.open(previewFile(store.selectedFolderId, item.name), '_blank', 'noopener,noreferrer')
    }
  }

  async function onDeleteFolder(folderId: string) {
    const ok = await confirm({
      title: t('files.folders.deleteTitle'),
      content: t('files.folders.deleteConfirm'),
      positiveText: t('common.delete'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    try {
      await store.deleteFolder(folderId)
      message.success(t('files.folders.deleted'))
    } catch {
      message.error(t('files.error.deleteFolder'))
    }
  }

  async function onSync() {
    try {
      const r = await store.syncFromNextcloud()
      message.success(t('files.sync.success', { created: r.created, skipped: r.skipped }))
    } catch {
      message.error(t('files.sync.error'))
    }
  }

  async function onDeleteFile(item: NCItem) {
    const ok = await confirm({
      title: t('files.deleteFileTitle'),
      content: `${t('files.deleteFileConfirm')} "${item.name}"?`,
      positiveText: t('common.delete'),
      negativeText: t('common.cancel'),
    })
    if (!ok || !store.selectedFolderId) return
    try {
      await deleteFile(store.selectedFolderId, item.name)
      message.success(t('files.fileDeleted'))
      await store.refreshCurrent()
    } catch {
      message.error(t('files.error.deleteFile'))
    }
  }

  return {
    showShareModal,
    shareFilename,
    showImagePreview,
    previewInitialIndex,
    previewImages,
    onShareFile,
    onPreviewImage,
    onPreviewPdf,
    onDeleteFolder,
    onSync,
    onDeleteFile,
  }
}
