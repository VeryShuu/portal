import type { Editor } from '@tiptap/core'

export function useEditorBubbleMenu(onEditFigure: () => void) {
  function shouldShowBubbleMenu({ editor, from, to }: { editor: Editor; from: number; to: number }) {
    if (!editor.isEditable) return false
    if (from === to) return false
    if (editor.isActive('image') || editor.isActive('table')) return false
    const text = editor.state.doc.textBetween(from, to, ' ').trim()
    return text.length > 0
  }

  function handleEditorDblClick(event: MouseEvent) {
    const target = event.target as HTMLElement | null
    if (!target) return
    const figure = target.closest('figure[data-type="figure-image"]')
    if (figure) {
      event.preventDefault()
      onEditFigure()
    }
  }

  return { shouldShowBubbleMenu, handleEditorDblClick }
}
