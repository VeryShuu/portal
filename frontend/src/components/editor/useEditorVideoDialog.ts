import { ref } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import type { Ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'

function extractEmbedSrc(input: string): string {
  const match = input.match(/src=["']([^"']+)["']/)
  return match ? match[1] : input
}

export function useEditorVideoDialog(editor: Ref<Editor | undefined>) {
  const showVideoDialog = ref(false)
  const videoUrl = ref('')
  const message = useMessage()
  const { t } = useI18n()

  function insertVideo() {
    const raw = videoUrl.value.trim()
    if (!raw) return
    const src = extractEmbedSrc(raw)
    const success = editor.value?.commands.setIframe({ src, title: '' })
    if (success === false) {
      message.error(t('editor.invalidVideoUrl'))
      return
    }
    videoUrl.value = ''
    showVideoDialog.value = false
  }

  return { showVideoDialog, videoUrl, insertVideo }
}
