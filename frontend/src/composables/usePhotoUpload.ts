import { computed, ref, type Ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { uploadPhotosBatchXhr, UploadResult } from '@/api/photos'

const PREVIEW_MAX_BYTES = 25 * 1024 * 1024
const PREVIEW_TTL_MS = 10 * 60 * 1000

const UPLOAD_BATCH_SIZE = 5
const RATE_LIMIT_RETRIES = 3
const RATE_LIMIT_BACKOFF_MS = 2000

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

  // Локальные blob-превью только что загруженных фото. Ключ — server photo_id.
  // Показываются в гриде, пока worker не сгенерирует серверный thumbnail
  // и фронт не получит SSE-событие `photos.processed`.
  const previewUrls = ref<Record<string, string>>({})
  const _previewTimers = new Map<string, ReturnType<typeof setTimeout>>()

  function _revokePreview(photoId: string) {
    const url = previewUrls.value[photoId]
    if (url) {
      URL.revokeObjectURL(url)
      const next = { ...previewUrls.value }
      delete next[photoId]
      previewUrls.value = next
    }
    const timer = _previewTimers.get(photoId)
    if (timer) {
      clearTimeout(timer)
      _previewTimers.delete(photoId)
    }
  }

  function _setPreview(photoId: string, file: File) {
    if (file.size > PREVIEW_MAX_BYTES) return
    if (!file.type.startsWith('image/')) return
    _revokePreview(photoId)
    try {
      const url = URL.createObjectURL(file)
      previewUrls.value = { ...previewUrls.value, [photoId]: url }
      const timer = setTimeout(() => _revokePreview(photoId), PREVIEW_TTL_MS)
      _previewTimers.set(photoId, timer)
    } catch {
      /* createObjectURL может бросить в SSR — игнорируем */
    }
  }

  function releasePreview(photoId: string) {
    _revokePreview(photoId)
  }

  function releaseAllPreviews() {
    for (const id of Object.keys(previewUrls.value)) _revokePreview(id)
  }

  function _onPhotoProcessed(ev: Event) {
    const detail = (ev as CustomEvent<{ photo_id: string }>).detail
    if (detail?.photo_id) _revokePreview(detail.photo_id)
  }
  onMounted(() => {
    if (typeof window !== 'undefined') {
      window.addEventListener('photos:processed', _onPhotoProcessed)
    }
  })

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

  onBeforeUnmount(() => {
    abortUpload()
    releaseAllPreviews()
    if (typeof window !== 'undefined') {
      window.removeEventListener('photos:processed', _onPhotoProcessed)
    }
  })

  async function runUploadQueue(files: File[]) {
    if (!selectedFolderId.value) return
    if (uploadingActive.value) return
    uploadAborted.value = false
    _abortController = new AbortController()
    uploadQueue.value = files.map(f => ({ file: f, status: 'pending' as const, progress: 0 }))

    const { signal } = _abortController
    for (let start = 0; start < files.length; start += UPLOAD_BATCH_SIZE) {
      if (uploadAborted.value || signal.aborted) break
      const end = Math.min(start + UPLOAD_BATCH_SIZE, files.length)
      const batch = files.slice(start, end)
      for (let i = start; i < end; i++) {
        uploadQueue.value[i].status = 'uploading'
        uploadQueue.value[i].progress = 0
      }

      let attempt = 0
      let succeeded = false
      let lastErr: unknown = null
      let uploadResult: UploadResult | null = null
      while (attempt <= RATE_LIMIT_RETRIES) {
        try {
          uploadResult = await uploadPhotosBatchXhr(
            selectedFolderId.value,
            batch,
            (pct) => {
              for (let i = start; i < end; i++) uploadQueue.value[i].progress = pct
            },
            signal,
          )
          succeeded = true
          break
        } catch (err: unknown) {
          lastErr = err
          const isAbort = (err as { name?: string })?.name === 'AbortError' || signal.aborted
          if (isAbort) break
          const status = (err as { status?: number })?.status
          if (status === 429 && attempt < RATE_LIMIT_RETRIES) {
            attempt += 1
            await new Promise<void>(resolve => setTimeout(resolve, RATE_LIMIT_BACKOFF_MS * attempt))
            continue
          }
          break
        }
      }

      if (succeeded) {
        if (uploadResult && uploadResult.items) {
          for (let i = start; i < end; i++) {
            const queueItem = uploadQueue.value[i]
            const resItem = uploadResult.items.find(
              item => item.original_name === queueItem.file.name,
            )
            if (resItem) {
              if (resItem.ok) {
                queueItem.status = 'done'
                queueItem.progress = 100
                if (resItem.photo_id) {
                  _setPreview(String(resItem.photo_id), queueItem.file)
                }
              } else {
                queueItem.status = 'error'
                queueItem.error = resItem.error || t('photos.upload.error')
                queueItem.progress = 100
              }
            } else {
              queueItem.status = 'done'
              queueItem.progress = 100
            }
          }
        } else {
          for (let i = start; i < end; i++) {
            uploadQueue.value[i].status = 'done'
            uploadQueue.value[i].progress = 100
          }
        }
      } else {
        const isAbort = (lastErr as { name?: string })?.name === 'AbortError' || signal.aborted
        for (let i = start; i < end; i++) {
          uploadQueue.value[i].status = 'error'
          uploadQueue.value[i].error = isAbort
            ? t('photos.upload.aborted')
            : t('photos.upload.error')
        }
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
      const errorCount = uploadQueue.value.filter(i => i.status === 'error').length
      if (doneCount > 0 && errorCount === 0) {
        message.success(t('photos.upload.done', { n: doneCount }))
      } else if (doneCount > 0 && errorCount > 0) {
        message.warning(t('photos.upload.partialSuccess', { done: doneCount, total: uploadQueue.value.length }))
      } else if (errorCount > 0) {
        message.error(t('photos.upload.failedAll'))
      }
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
    previewUrls,
    releasePreview,
    releaseAllPreviews,
  }
}
