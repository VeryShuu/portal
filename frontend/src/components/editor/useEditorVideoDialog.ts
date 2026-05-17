import { ref } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import type { Ref } from 'vue'

function extractEmbedSrc(input: string): string {
  const match = input.match(/src=["']([^"']+)["']/)
  return match ? match[1] : input
}

export function useEditorVideoDialog(editor: Ref<Editor | undefined>) {
  const showVideoDialog = ref(false)
  const videoUrl = ref('')

  function insertVideo() {
    const raw = videoUrl.value.trim()
    if (!raw) return
    const src = extractEmbedSrc(raw)
    editor.value?.commands.setIframe({ src, title: '' })
    videoUrl.value = ''
    showVideoDialog.value = false
  }

  return { showVideoDialog, videoUrl, insertVideo }
}
