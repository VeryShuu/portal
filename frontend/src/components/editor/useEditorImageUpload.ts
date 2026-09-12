import { reactive, ref } from 'vue'
import type { Ref } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { api, apiUpload } from '@/api'

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

  /**
   * Требует ли URL re-host: внешний http(s) (не наш локальный /api/v1/... и не
   * data:/blob:). Такие ссылки при paste/drop подменяются на локальную копию,
   * чтобы статья не зависела от стороннего URL (может протухнуть / быть
   * недоступным из VPN / тянуть трекеры).
   */
  function isRemoteUrl(src: string): boolean {
    return /^https?:\/\//i.test(src) && !src.toLowerCase().includes('/api/v1/')
  }

  /**
   * Нормализовать и провалидировать внешний image-URL через конструктор URL.
   * Возвращает канонический ``http(s)://host/...`` (отбрасывая мусор/невалидные
   * схемы/относительные пути) либо ``null``. Извлечённый из буфера URL **никогда
   * не вставляется в DOM напрямую**: он уходит на backend re-host, а в статью
   * попадает уже наш внутренний URL. Эта валидация — defense-in-depth и разрывает
   * CodeQL taint-flow (``js/xss``) на источнике.
   */
  function sanitizeRemoteUrl(raw: string): string | null {
    try {
      const u = new URL(raw.trim())
      // Только http(s) с непустым хостом; внутренние /api/v1/ URL отсеиваются
      // отдельно в isRemoteUrl (по pathname).
      if ((u.protocol !== 'http:' && u.protocol !== 'https:') || !u.hostname) {
        return null
      }
      return u.toString()
    } catch {
      return null
    }
  }

  /**
   * Извлечь первый внешний image-URL из буфера обмена/перетаскивания. Покрывает
   * «Копировать изображение» в браузере и Ctrl+C на <img> со страницы: в этих
   * случаях в буфере нет файла — только text/html с тегом <img src> (Firefox) или
   * голый URL (text/uri-list / text/plain). data:URI и blob: не обрабатываем.
   *
   * Извлечение ``src`` регуляркой (а не DOMParser.parseFromString) — намеренно:
   * избегаем DOM-парсинга user-контролируемого HTML (CodeQL js/xss source) и
   * берём ровно атрибут ``src`` первого ``<img>``. Сам URL валидируется в
   * :func:`sanitizeRemoteUrl` и **никогда не вставляется в DOM напрямую** — он
   * уходит на backend re-host, а в статью попадает уже наш внутренний URL.
   */
  const IMG_SRC_RE = /<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/i

  function extractRemoteImageUrl(html: string | null, uriList: string | null, plain: string | null): string | null {
    if (html) {
      const match = html.match(IMG_SRC_RE)
      if (match) {
        const safe = sanitizeRemoteUrl(match[1])
        if (safe && isRemoteUrl(safe)) return safe
      }
    }
    const candidate = uriList?.split('\n')[0]?.trim() ?? plain?.trim()
    if (candidate) {
      const safe = sanitizeRemoteUrl(candidate)
      if (safe && isRemoteUrl(safe)) return safe
    }
    return null
  }

  async function uploadRemoteImage(url: string): Promise<string | null> {
    if (!uploadEndpoint.value) {
      message.warning(t('editor.imageUploadDisabled'))
      return null
    }
    try {
      const data = await api<{ url: string }>(`${uploadEndpoint.value}/remote`, {
        method: 'POST',
        body: { url },
      })
      return data.url
    } catch (err) {
      const errorObj = err as { response?: { status?: number }, status?: number, statusCode?: number }
      const status = errorObj?.response?.status ?? errorObj?.status ?? errorObj?.statusCode
      if (status === 413) {
        message.error(t('editor.imageTooLarge'))
      } else {
        message.error(t('editor.imageFetchFailed'))
      }
      return null
    }
  }

  /**
   * Общий финальный шаг после получения локального URL (file-upload или
   * re-host): открыть диалог alt/caption для вставки FigureImage.
   */
  function openDialogWithUrl(url: string): void {
    resetImageForm()
    imageForm.src = url
    showImageDialog.value = true
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
    openDialogWithUrl(url)
  }

  async function handleDrop(event: DragEvent) {
    const dt = event.dataTransfer
    if (!dt) return
    // Сначала пробуем локальный файл (перетащили файл с диска).
    const file = Array.from(dt.files ?? []).find((f) => f.type.startsWith('image/'))
    if (file) {
      const url = await uploadImage(file)
      if (!url) return
      openDialogWithUrl(url)
      return
    }
    // Иначе — перетаскивание <img> с другой страницы: в DataTransfer лежит
    // text/html (Firefox) и/или text/uri-list. Re-host внешней картинки.
    const remoteUrl = extractRemoteImageUrl(
      dt.getData('text/html'),
      dt.getData('text/uri-list'),
      null,
    )
    if (!remoteUrl) return
    const url = await uploadRemoteImage(remoteUrl)
    if (!url) return
    openDialogWithUrl(url)
  }

  async function handlePaste(event: ClipboardEvent) {
    const cd = event.clipboardData
    if (!cd) return
    // Сначала ищем файл-картинку (скриншот, «Копировать изображение» в Chrome —
    // в буфере есть bitmap).
    for (const item of Array.from(cd.items)) {
      if (item.type.startsWith('image/')) {
        event.preventDefault()
        const file = item.getAsFile()
        if (!file) continue
        const url = await uploadImage(file)
        if (!url) return
        openDialogWithUrl(url)
        return
      }
    }
    // Файла нет — значит «Копировать изображение» в Firefox или Ctrl+C на <img>
    // со страницы кладёт в буфер text/html с <img src> (внешняя ссылка). Если её
    // не перехватить, TipTap вставит внешний URL как есть → ссылка протухнет.
    const html = cd.getData('text/html')
    const remoteUrl = extractRemoteImageUrl(
      html || null,
      cd.getData('text/uri-list') || null,
      cd.getData('text/plain') || null,
    )
    if (!remoteUrl) return
    event.preventDefault()
    const url = await uploadRemoteImage(remoteUrl)
    if (!url) return
    openDialogWithUrl(url)
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
