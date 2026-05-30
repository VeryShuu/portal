import { computed } from 'vue'
import type { Editor } from '@tiptap/vue-3'

export function useToolbarState(getEditor: () => Editor) {
  return {
    isBold: computed(() => getEditor().isActive('bold')),
    isItalic: computed(() => getEditor().isActive('italic')),
    isStrike: computed(() => getEditor().isActive('strike')),
    isUnderline: computed(() => getEditor().isActive('underline')),
    isCode: computed(() => getEditor().isActive('code')),
    isHighlight: computed(() => getEditor().isActive('highlight')),
    isSubscript: computed(() => getEditor().isActive('subscript')),
    isSuperscript: computed(() => getEditor().isActive('superscript')),
    isHeading2: computed(() => getEditor().isActive('heading', { level: 2 })),
    isHeading3: computed(() => getEditor().isActive('heading', { level: 3 })),
    isBulletList: computed(() => getEditor().isActive('bulletList')),
    isOrderedList: computed(() => getEditor().isActive('orderedList')),
    isTaskList: computed(() => getEditor().isActive('taskList')),
    isBlockquote: computed(() => getEditor().isActive('blockquote')),
    isCodeBlock: computed(() => getEditor().isActive('codeBlock')),
    isAlignLeft: computed(() => getEditor().isActive({ textAlign: 'left' })),
    isAlignCenter: computed(() => getEditor().isActive({ textAlign: 'center' })),
    isAlignRight: computed(() => getEditor().isActive({ textAlign: 'right' })),
    isLink: computed(() => getEditor().isActive('link')),
    isCallout: computed(() => getEditor().isActive('callout')),
    isDetails: computed(() => getEditor().isActive('details')),
  }
}
