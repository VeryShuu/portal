import { ref } from 'vue'

export interface UseFileDropzoneOptions {
  onFiles: (files: File[]) => void | Promise<void>
  enabled?: () => boolean
}

export function useFileDropzone(options: UseFileDropzoneOptions) {
  const { onFiles, enabled } = options
  const isDragOver = ref(false)

  function isEnabled(): boolean {
    return enabled ? enabled() : true
  }

  function onDragOver(e: DragEvent) {
    if (!isEnabled()) return
    const dt = e.dataTransfer
    if (!dt || !dt.types.includes('Files')) return
    dt.dropEffect = 'copy'
    isDragOver.value = true
  }

  function onDragLeave(e: DragEvent) {
    const current = e.currentTarget as HTMLElement | null
    const related = e.relatedTarget as Node | null
    if (current && related && current.contains(related)) return
    isDragOver.value = false
  }

  async function onDrop(e: DragEvent) {
    isDragOver.value = false
    if (!isEnabled()) return
    const files = Array.from(e.dataTransfer?.files ?? [])
    if (!files.length) return
    await onFiles(files)
  }

  return { isDragOver, onDragOver, onDragLeave, onDrop }
}
