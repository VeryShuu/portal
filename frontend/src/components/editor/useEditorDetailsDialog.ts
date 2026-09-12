import { ref } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import type { Ref } from 'vue'

export function useEditorDetailsDialog(editor: Ref<Editor | undefined>) {
  const showDetailsDialog = ref(false)
  const detailsSummary = ref('')

  function openDetailsDialog() {
    detailsSummary.value = ''
    showDetailsDialog.value = true
  }

  function insertDetails() {
    const summary = detailsSummary.value.trim()
    editor.value?.chain().focus().insertDetails(summary).run()
    showDetailsDialog.value = false
    detailsSummary.value = ''
  }

  function preventDetailsToggle(event: MouseEvent) {
    const target = event.target as Element | null
    const summary = target?.closest?.('summary') as HTMLElement | null
    if (!summary) return
    const detailsEl = summary.closest('details[data-tiptap-details]') as HTMLElement | null
    if (!detailsEl) return

    event.preventDefault()

    const ed = editor.value
    if (!ed) return

    const view = ed.view
    let pos: number | null = null
    try {
      pos = view.posAtDOM(detailsEl, 0)
    } catch {
      pos = null
    }
    if (pos == null) return

    const $pos = ed.state.doc.resolve(pos)
    for (let depth = $pos.depth; depth >= 0; depth--) {
      const node = $pos.node(depth)
      if (node.type.name === 'details') {
        const nodePos = $pos.before(depth)
        const isOpen = !!node.attrs['open']
        ed.chain()
          .command(({ tr }) => {
            tr.setNodeMarkup(nodePos, undefined, { ...node.attrs, open: !isOpen })
            return true
          })
          .run()
        break
      }
    }
  }

  return { showDetailsDialog, detailsSummary, openDetailsDialog, insertDetails, preventDetailsToggle }
}
