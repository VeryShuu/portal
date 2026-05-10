import { Node, mergeAttributes } from '@tiptap/core'

export type CalloutType = 'info' | 'warning' | 'tip' | 'danger'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    callout: {
      setCallout: (type: CalloutType) => ReturnType
      toggleCallout: (type: CalloutType) => ReturnType
    }
  }
}

export const Callout = Node.create({
  name: 'callout',
  group: 'block',
  content: 'block+',

  addAttributes() {
    return {
      type: {
        default: 'info' as CalloutType,
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-type') || 'info',
        renderHTML: (attrs) => ({ 'data-type': attrs.type }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-callout]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes({ 'data-callout': '' }, HTMLAttributes), 0]
  },

  addCommands() {
    return {
      setCallout:
        (type) =>
        ({ commands }) =>
          commands.wrapIn(this.name, { type }),
      toggleCallout:
        (type) =>
        ({ commands }) =>
          commands.toggleWrap(this.name, { type }),
    }
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: Record<string, CallableFunction>, node: { attrs: { type: string } }) {
          const calloutType = node.attrs.type
          state['write'](`<div data-callout data-type="${calloutType}">`)
          state['ensureNewLine']()
          state['renderContent'](node)
          state['ensureNewLine']()
          state['write']('</div>')
          state['closeBlock'](node)
        },
        parse: {},
      },
    }
  },
})
