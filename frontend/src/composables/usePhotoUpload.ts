import { computed, ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { uploadPhotoXhr } from '@/api/photos'

export interface UploadQueueItem {
  file: File
  status: 'pending' | 'uploading' | 'done' | 'error'
  progress: number
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
  let _abortController: AbortController | null = null

  const uploadingActive = computed(() =>
    uploadQueue.value.length > 0 &&
    uploadQueue.value.some(i => i.status === 'pending' || i.status === 'uploading'),
  )
  const uploadDoneCount = computed(
    () => uploadQueue.value.filter(i => i.status === 'done').length,
  )
  const totalProgress = computed(() => {
    if (!uploadQueue.value.length) return 0
    const sum = uploadQueue.value.reduce((acc, item) => acc + item.progress, 0)
    return Math.round(sum / uploadQueue.value.length)
  })

  function triggerUpload() {
    fileInputRef.value?.click()
  }

  function abortUpload() {
    uploadAborted.value = true
    _abortController?.abort()
    _abortController = null
  }

  async function runUploadQueue(files: File[]) {
    if (!selectedFolderId.value) return
    if (uploadingActive.value) return
    uploadAborted.value = false
    _abortController = new AbortController()
    uploadQueue.value = files.map(f => ({ file: f, status: 'pending' as const, progress: 0 }))

    const { signal } = _abortController
    for (let i = 0; i < files.length; i++) {
      if (uploadAborted.value || signal.aborted) break
      const item = uploadQueue.value[i]
      item.status = 'uploading'
      item.progress = 0
      try {
        await uploadPhotoXhr(
          selectedFolderId.value,
          files[i],
          (pct) => { uploadQueue.value[i].progress = pct },
          signal,
        )
        item.status = 'done'
        item.progress = 100
      } catch (err: unknown) {
        const isAbort = (err as { name?: string })?.name === 'AbortError' || signal.aborted
        item.status = 'error'
        item.error = isAbort ? t('photos.upload.aborted') : t('photos.upload.error')
        if (isAbort) break
      }
    }

    _abortController = null
    if (uploadAborted.value) {
      for (const item of uploadQueue.value) {
        if (item.status === 'pending') {
          item.status = 'error'
          item.error = t('photos.upload.aborted')
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
    runUploadQueue(files).catch((err: unknown) => {
      console.error('[usePhotoUpload] onDrop upload failed', err)
    })
  }

  return {
    fileInputRef,
    uploadQueue,
    uploadAborted,
    uploadingActive,
    uploadDoneCount,
    totalProgress,
    isDraggingOver,
    triggerUpload,
    abortUpload,
    runUploadQueue,
    onFilesPicked,
    onDrop,
  }
}
