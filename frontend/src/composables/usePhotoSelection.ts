import { ref } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { bulkAction, type Photo } from '@/api/photos'
import { usePhotosStore, RECENT_LIMIT } from '@/stores/photos'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { parseApiError } from '@/utils/parseApiError'

export interface UsePhotoSelectionOptions {
  photos: Ref<Photo[]>
  totalPhotos: Ref<number>
  reloadPhotos: () => Promise<void>
}

export function usePhotoSelection(opts: UsePhotoSelectionOptions) {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()
  const photosStore = usePhotosStore()

  const selectMode = ref(false)
  const selectedPhotoIds = ref<Set<string>>(new Set())

  const moveModalOpen = ref(false)
  const moveTargetFolderId = ref<string | null>(null)

  function toggleSelectMode() {
    selectMode.value = !selectMode.value
    if (!selectMode.value) selectedPhotoIds.value = new Set()
  }

  function togglePhotoSelect(id: string) {
    const s = new Set(selectedPhotoIds.value)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    selectedPhotoIds.value = s
  }

  async function bulkDelete() {
    if (selectedPhotoIds.value.size === 0) return
    const ids = [...selectedPhotoIds.value]
    const ok = await confirm({
      title: t('photos.select.delete'),
      content: t('photos.select.deleteConfirm', { n: ids.length }),
      positiveText: t('common.delete'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    try {
      const res = await bulkAction({ action: 'delete', photo_ids: ids })
      opts.photos.value = opts.photos.value.filter(p => !ids.includes(p.id))
      opts.totalPhotos.value = Math.max(0, opts.totalPhotos.value - res.processed)
      message.success(t('photos.select.deleteDone', { n: res.processed }))
      toggleSelectMode()
      photosStore.loadRecent(RECENT_LIMIT)
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }

  function openMoveModal() {
    if (selectedPhotoIds.value.size === 0) return
    moveTargetFolderId.value = null
    moveModalOpen.value = true
  }

  async function confirmMove(): Promise<boolean | void> {
    if (!moveTargetFolderId.value) return false
    const ids = [...selectedPhotoIds.value]
    try {
      const res = await bulkAction({
        action: 'move',
        photo_ids: ids,
        target_folder_id: moveTargetFolderId.value,
      })
      message.success(t('photos.select.moveDone', { n: res.processed }))
      moveModalOpen.value = false
      toggleSelectMode()
      await opts.reloadPhotos()
    } catch (e) {
      message.error(parseApiError(e, t))
      return false
    }
  }

  return {
    selectMode,
    selectedPhotoIds,
    moveModalOpen,
    moveTargetFolderId,
    toggleSelectMode,
    togglePhotoSelect,
    bulkDelete,
    openMoveModal,
    confirmMove,
  }
}
