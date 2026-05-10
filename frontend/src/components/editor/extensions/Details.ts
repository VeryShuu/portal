import { Node, mergeAttributes } from '@tiptap/core'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    details: {
      insertDetails: (summary?: string) => ReturnType
    }
  }
}

export const Details = Node.create({
  name: 'details',
  group: 'block',
  content: 'block+',

  addAttributes() {
    return {
      summary: {
        default: '',
        parseHTML: (el) => (el as HTMLElement).querySelector('summary')?.textContent ?? '',
        renderHTML: () => ({}),
      },
    }
  },

  parseHTML() {
    return [
      {
        tag: 'details',
        getAttrs: (el) => ({
          summary: (el as HTMLElement).querySelector('summary')?.textContent ?? '',
        }),
        contentElement: (el: HTMLElement | string) => {
          const element = el as HTMLElement
          const contentDiv = element.querySelector('.details-content')
          if (contentDiv) return contentDiv as HTMLElement
          const div = document.createElement('div')
          for (const child of Array.from(element.childNodes)) {
            if ((child as Element).tagName?.toLowerCase() !== 'summary') {
              div.appendChild(child.cloneNode(true))
            }
          }
          return div
        },
      },
    ]
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'details',
      mergeAttributes(HTMLAttributes),
      ['summary', {}, node.attrs.summary || ''],
      ['div', { class: 'details-content' }, 0],
    ]
  },

  addCommands() {
    return {
      insertDetails:
        (summary = '') =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: { summary },
            content: [{ type: 'paragraph' }],
          }),
    }
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: Record<string, CallableFunction>, node: { attrs: { summary: string } }) {
          const summary = node.attrs.summary || ''
          state['write'](`<details><summary>${summary}</summary>`)
          state['ensureNewLine']()
          state['renderContent'](node)
          state['ensureNewLine']()
          state['write']('</details>')
          state['closeBlock'](node)
        },
        parse: {},
      },
    }
  },
})
