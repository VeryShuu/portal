import { reactive, ref } from 'vue'
import type { Ref } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { apiUpload } from '@/api'

export function useEditorImageUpload(editor: Ref<Editor | undefined>, uploadEndpoint: Ref<string | undefined>) {
  const { t } = useI18n()
  const message = useMessage()

  const fileInputRef = ref<HTMLInputElement | null>(null)

  const showImageDialog = ref(false)
  const imageForm = reactive({
    src: '',
    alt: '',
    caption: '',
  })

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

  function triggerImageUpload() {
    if (editor.value?.isActive('figureImage')) {
      openImageDialogForEdit()
      return
    }
    fileInputRef.value?.click()
  }

  function resetImageForm() {
    imageForm.src = ''
    imageForm.alt = ''
    imageForm.caption = ''
  }

  function openImageDialogForEdit() {
    const ed = editor.value
    if (!ed) return
    const attrs = ed.getAttributes('figureImage') as {
      src?: string
      alt?: string
      caption?: string
    }
    if (!attrs?.src) return
    imageForm.src = attrs.src
    imageForm.alt = attrs.alt ?? ''
    imageForm.caption = attrs.caption ?? ''
    showImageDialog.value = true
  }

  function submitImageDialog() {
    const ed = editor.value
    if (!ed || !imageForm.src) {
      showImageDialog.value = false
      return
    }
    const payload = {
      src: imageForm.src,
      alt: imageForm.alt,
      caption: imageForm.caption,
    }
    if (ed.isActive('figureImage')) {
      ed.chain().focus().updateFigureImage(payload).run()
    } else {
      ed.chain().focus().setFigureImage(payload).run()
    }
    showImageDialog.value = false
    resetImageForm()
  }

  function cancelImageDialog() {
    showImageDialog.value = false
    resetImageForm()
  }

  async function handleFileInputChange(event: Event) {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    if (!file) return
    input.value = ''
    const url = await uploadImage(file)
    if (!url) return
    resetImageForm()
    imageForm.src = url
    showImageDialog.value = true
  }

  async function handleDrop(event: DragEvent) {
    const files = event.dataTransfer?.files
    if (!files?.length) return
    const file = Array.from(files).find((f) => f.type.startsWith('image/'))
    if (!file) return
    const url = await uploadImage(file)
    if (!url) return
    resetImageForm()
    imageForm.src = url
    showImageDialog.value = true
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
        if (!url) return
        resetImageForm()
        imageForm.src = url
        showImageDialog.value = true
        return
      }
    }
  }

  return {
    fileInputRef,
    triggerImageUpload,
    handleFileInputChange,
    handleDrop,
    handlePaste,
    showImageDialog,
    imageForm,
    openImageDialogForEdit,
    submitImageDialog,
    cancelImageDialog,
  }
}
