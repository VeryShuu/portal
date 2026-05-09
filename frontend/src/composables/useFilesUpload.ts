import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { uploadFiles } from '../api/files'
import { extractDroppedFiles } from '../utils/extractDroppedFiles'
import { useFilesStore } from '../stores/files'

export function useFilesUpload(
  folderId: Ref<string | null>,
  onUploaded: () => Promise<void> | void,
): {
  uploading: Ref<boolean>
  uploadProgress: Ref<{ done: number; total: number; failed: number }>
  fileInputRef: Ref<HTMLInputElement | null>
  triggerUpload(): void
  handleFileInput(e: Event): Promise<void>
  runUpload(files: File[]): Promise<void>
  dragDepth: Ref<number>
  dndActive: ComputedRef<boolean>
  onMainDragEnter(e: DragEvent): void
  onMainDragOver(e: DragEvent): void
  onMainDragLeave(e: DragEvent): void
  onMainDrop(e: DragEvent): Promise<void>
} {
  const { t } = useI18n()
  const message = useMessage()
  const store = useFilesStore()

  const uploading = ref(false)
  const uploadProgress = ref<{ done: number; total: number; failed: number }>({ done: 0, total: 0, failed: 0 })
  const fileInputRef = ref<HTMLInputElement | null>(null)
  const dragDepth = ref(0)
  const dndActive = computed(() => dragDepth.value > 0)

  function triggerUpload() {
    fileInputRef.value?.click()
  }

  async function handleFileInput(e: Event) {
    const input = e.target as HTMLInputElement
    if (!input.files?.length || !folderId.value) return
    const files = Array.from(input.files)
    input.value = ''
    await runUpload(files)
  }

  async function runUpload(files: File[]) {
    if (!files.length || !folderId.value) return
    uploading.value = true
    uploadProgress.value = { done: 0, total: files.length, failed: 0 }
    try {
      const result = await uploadFiles(folderId.value, files)
      uploadProgress.value = {
        done: result.uploaded.length,
        total: files.length,
        failed: result.failed.length,
      }
      if (result.uploaded.length) {
        message.success(t('files.uploaded', { n: result.uploaded.length }))
      }
      if (result.failed.length) {
        message.warning(t('files.uploadFailed', { n: result.failed.length }))
      }
      await onUploaded()
    } catch {
      message.error(t('files.error.upload'))
    } finally {
      uploading.value = false
    }
  }

  function onMainDragEnter(e: DragEvent) {
    if (!store.canUpload || !folderId.value) return
    if (!e.dataTransfer?.types?.includes('Files')) return
    dragDepth.value += 1
  }

  function onMainDragOver(e: DragEvent) {
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  }

  function onMainDragLeave(_e: DragEvent) {
    if (dragDepth.value > 0) dragDepth.value -= 1
  }

  async function onMainDrop(e: DragEvent) {
    dragDepth.value = 0
    if (!store.canUpload || !folderId.value || !e.dataTransfer) return
    const { files, hadFolders } = await extractDroppedFiles(e.dataTransfer)
    if (hadFolders) {
      message.info(t('files.dropzone.foldersSkipped'))
    }
    if (!files.length) return
    await runUpload(files)
  }

  return {
    uploading,
    uploadProgress,
    fileInputRef,
    triggerUpload,
    handleFileInput,
    runUpload,
    dragDepth,
    dndActive,
    onMainDragEnter,
    onMainDragOver,
    onMainDragLeave,
    onMainDrop,
  }
}
