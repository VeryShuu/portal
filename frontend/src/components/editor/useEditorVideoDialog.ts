import { ref } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import type { Ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { parseVideoEmbed, DEFAULT_VIDEO_IFRAME_ORIGINS } from '../../utils/videoEmbed'

function extractEmbedSrc(input: string): string {
  const match = input.match(/src=["']([^"']+)["']/)
  return match ? match[1] : input
}

/**
 * Диалог «Вставить видео» rich-редактора. Конвертация ссылки в embed-адрес —
 * через общий парсер портала (utils/videoEmbed): что вставил автор (обычная
 * watch-ссылка или готовый embed-код) — в HTML статьи попадает канонический
 * embed-src, который разрешён CSP и не блокируется X-Frame-Options.
 * allowedOrigins — живой список из настройки video_iframe_origins
 * (bootstrap → branding.allowed_iframe_origins); гейт совпадает с CSP.
 */
export function useEditorVideoDialog(
  editor: Ref<Editor | undefined>,
  allowedOrigins: () => string[] = () => DEFAULT_VIDEO_IFRAME_ORIGINS,
) {
  const showVideoDialog = ref(false)
  const videoUrl = ref('')
  const message = useMessage()
  const { t } = useI18n()

  function insertVideo() {
    const raw = videoUrl.value.trim()
    if (!raw) return
    const src = extractEmbedSrc(raw)
    const info = parseVideoEmbed(src, allowedOrigins())
    if (!info) {
      message.error(t('editor.invalidVideoUrl'))
      return
    }
    const success = editor.value?.commands.setIframe({ src: info.embedUrl, title: '' })
    if (success === false) {
      message.error(t('editor.invalidVideoUrl'))
      return
    }
    videoUrl.value = ''
    showVideoDialog.value = false
  }

  return { showVideoDialog, videoUrl, insertVideo }
}
