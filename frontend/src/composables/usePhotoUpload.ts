import { computed, ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { uploadPhotos } from '@/api/photos'

export interface UploadQueueItem {
  file: File
  status: 'pending' | 'uploading' | 'done' | 'error'
  error?: string
}

export function usePhotoUpload(
  selectedFolderId: Ref<string | null>,
  onSuccess: () => Promise<void>,
) {
  const { t } = useI18n()
  const message = useMessage()

  const fileInputRef = ref<HTMLInputElement | null>(null)
  const uploadQueue = ref<UploadQueueItem[]>([])
  const uploadAborted = ref(false)
  const isDraggingOver = ref(false)

  const uploadingActive = computed(() =>
    uploadQueue.value.length > 0 &&
    uploadQueue.value.some(i => i.status === 'pending' || i.status === 'uploading'),
  )
  const uploadDoneCount = computed(
    () => uploadQueue.value.filter(i => i.status === 'done').length,
  )

  function triggerUpload() {
    fileInputRef.value?.click()
  }

  async function runUploadQueue(files: File[]) {
    if (!selectedFolderId.value) return
    uploadAborted.value = false
    uploadQueue.value = files.map(f => ({ file: f, status: 'pending' as const }))

    const batchSize = 5
    for (let i = 0; i < files.length; i += batchSize) {
      if (uploadAborted.value) break
      const end = Math.min(i + batchSize, files.length)
      for (let j = i; j < end; j++) uploadQueue.value[j].status = 'uploading'
      try {
        await uploadPhotos(selectedFolderId.value, files.slice(i, end))
        for (let j = i; j < end; j++) uploadQueue.value[j].status = 'done'
      } catch {
        for (let j = i; j < end; j++) {
          uploadQueue.value[j].status = 'error'
          uploadQueue.value[j].error = t('photos.upload.error')
        }
      }
    }

    if (uploadAborted.value) {
      for (let j = 0; j < uploadQueue.value.length; j++) {
        if (uploadQueue.value[j].status === 'pending') {
          uploadQueue.value[j].status = 'error'
          uploadQueue.value[j].error = t('photos.upload.aborted')
        }
      }
      message.warning(t('photos.upload.aborted'))
    } else {
      const doneCount = uploadQueue.value.filter(i => i.status === 'done').length
      if (doneCount > 0) message.success(t('photos.upload.done', { n: doneCount }))
    }
    await onSuccess()
  }

  async function onFilesPicked(e: Event) {
    const input = e.target as HTMLInputElement
    if (!input.files?.length || !selectedFolderId.value) return
    const files = Array.from(input.files)
    if (input) input.value = ''
    await runUploadQueue(files)
  }

  function onDrop(e: DragEvent) {
    isDraggingOver.value = false
    if (!selectedFolderId.value || !e.dataTransfer?.files.length) return
    if (!Array.from(e.dataTransfer.types).includes('Files')) return
    const files = Array.from(e.dataTransfer.files).filter(
      f => f.type.startsWith('image/') || /\.(heic|heif)$/i.test(f.name),
    )
    if (!files.length) return
    runUploadQueue(files)
  }

  return {
    fileInputRef,
    uploadQueue,
    uploadAborted,
    uploadingActive,
    uploadDoneCount,
    isDraggingOver,
    triggerUpload,
    runUploadQueue,
    onFilesPicked,
    onDrop,
  }
}
