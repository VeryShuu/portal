import { ref } from 'vue'
import type { Ref } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { apiUpload } from '@/api'

export function useEditorImageUpload(editor: Ref<Editor | undefined>, uploadEndpoint: Ref<string | undefined>) {
  const { t } = useI18n()
  const message = useMessage()

  const fileInputRef = ref<HTMLInputElement | null>(null)

  async function uploadImage(file: File): Promise<string | null> {
    if (!uploadEndpoint.value) {
      message.warning(t('editor.imageUploadDisabled'))
      return null
    }
    const formData = new FormData()
    formData.append('file', file)
    try {
      const data = await apiUpload<{ url: string }>(uploadEndpoint.value, formData)
      return data.url
    } catch (err) {
      const errorObj = err as { response?: { status?: number }, status?: number, statusCode?: number }
      const status = errorObj?.response?.status ?? errorObj?.status ?? errorObj?.statusCode
      if (status === 413) {
        message.error(t('editor.imageTooLarge'))
      } else {
        message.error(t('editor.imageUploadError'))
      }
      return null
    }
  }

  function insertImage(url: string) {
    editor.value?.chain().focus().setImage({ src: url }).run()
  }

  function triggerImageUpload() {
    fileInputRef.value?.click()
  }

  async function handleFileInputChange(event: Event) {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    if (!file) return
    input.value = ''
    const url = await uploadImage(file)
    if (url) insertImage(url)
  }

  async function handleDrop(event: DragEvent) {
    const files = event.dataTransfer?.files
    if (!files?.length) return
    for (const file of Array.from(files)) {
      if (file.type.startsWith('image/')) {
        const url = await uploadImage(file)
        if (url) insertImage(url)
      }
    }
  }

  async function handlePaste(event: ClipboardEvent) {
    const items = event.clipboardData?.items
    if (!items) return
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        event.preventDefault()
        const file = item.getAsFile()
        if (!file) continue
        const url = await uploadImage(file)
        if (url) insertImage(url)
      }
    }
  }

  return {
    fileInputRef,
    triggerImageUpload,
    handleFileInputChange,
    handleDrop,
    handlePaste,
  }
}
