import { ref, onUnmounted } from 'vue'
import type { UploadFileInfo } from 'naive-ui'

export function useLinkIconUpload() {
  const iconFile = ref<File | null>(null)
  const iconPreview = ref<string | null>(null)
  const iconRemoved = ref(false)

  onUnmounted(() => {
    if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
  })

  function onIconFileChange({ file }: { file: UploadFileInfo }) {
    if (file.file) {
      if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
      iconFile.value = file.file
      iconPreview.value = URL.createObjectURL(file.file)
      iconRemoved.value = false
    }
  }

  function removeIcon() {
    if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
    iconFile.value = null
    iconPreview.value = null
    iconRemoved.value = true
  }

  function resetIconState() {
    if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
    iconFile.value = null
    iconPreview.value = null
    iconRemoved.value = false
  }

  return { iconFile, iconPreview, iconRemoved, onIconFileChange, removeIcon, resetIconState }
}
