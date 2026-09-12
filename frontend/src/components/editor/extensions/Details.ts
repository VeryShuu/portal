import { Node, mergeAttributes, getHTMLFromFragment } from '@tiptap/core'
import { Fragment } from '@tiptap/pm/model'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    details: {
      insertDetails: (summary?: string) => ReturnType
    }
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
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
      open: {
        default: true,
        parseHTML: (el) => (el as HTMLElement).hasAttribute('open'),
        renderHTML: (attrs) => (attrs['open'] ? { open: '' } : {}),
      },
    }
  },

  parseHTML() {
    return [
      {
        tag: 'details',
        getAttrs: (el) => ({
          summary: (el as HTMLElement).querySelector('summary')?.textContent ?? '',
          open: (el as HTMLElement).hasAttribute('open'),
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
      mergeAttributes(HTMLAttributes, { 'data-tiptap-details': '' }),
      ['summary', {}, node.attrs['summary'] || ''],
      ['div', { class: 'details-content' }, 0],
    ]
  },

  addCommands() {
    return {
      insertDetails:
        (summary = '') =>
        ({ state, chain }) => {
          const { from, to } = state.selection
          const hasSelection = from !== to

          let innerContent: Record<string, unknown>[] = [{ type: 'paragraph' }]

          if (hasSelection) {
            const slice = state.selection.content()
            const fragmentJson = slice.content.toJSON() as Record<string, unknown>[] | null
            if (fragmentJson && fragmentJson.length) {
              const blockNodes = fragmentJson.filter(
                (n) => n && typeof n === 'object' && 'type' in n,
              )
              const allBlocks = blockNodes.every((n) => {
                const type = (n as { type?: string }).type
                return type !== 'text'
              })
              if (allBlocks && blockNodes.length) {
                innerContent = blockNodes
              } else {
                const text = state.doc.textBetween(from, to, '\n', '\n')
                innerContent = text
                  .split('\n')
                  .map((line) => ({
                    type: 'paragraph',
                    content: line ? [{ type: 'text', text: line }] : undefined,
                  }))
              }
            }
          }

          const result = chain()
            .focus()
            .insertContent({
              type: this.name,
              attrs: { summary, open: true },
              content: innerContent,
            })
            .run()

          if (result) {
            const { tr } = this.editor.state
            const insertedAt = tr.selection.from
            const $pos = tr.doc.resolve(Math.max(0, insertedAt - 2))
            for (let depth = $pos.depth; depth >= 0; depth--) {
              if ($pos.node(depth).type.name === this.name) {
                const detailsStart = $pos.before(depth)
                const detailsNode = $pos.node(depth)
                let innerPos = detailsStart + 1
                detailsNode.descendants((node, pos) => {
                  if (node.isTextblock && innerPos === detailsStart + 1) {
                    innerPos = detailsStart + 1 + pos + node.nodeSize - 1
                    return false
                  }
                  return true
                })
                this.editor.commands.setTextSelection(innerPos)
                break
              }
            }
          }

          return result
        },
    }
  },

  addStorage() {
    return {
      markdown: {
        serialize(
          state: Record<string, CallableFunction>,
          node: { attrs: { summary: string }; type: { schema: unknown }; content: unknown },
        ) {
          const summary = (node.attrs.summary || '').trim()
          const schema = (node.type as { schema: Parameters<typeof getHTMLFromFragment>[1] }).schema
          const innerHtml = getHTMLFromFragment(
            Fragment.from(node.content as Parameters<typeof Fragment.from>[0]),
            schema,
          )
          state['write']('<details>')
          state['ensureNewLine']()
          state['write'](`<summary>${escapeHtml(summary)}</summary>`)
          state['ensureNewLine']()
          state['write']('')
          state['ensureNewLine']()
          state['write'](innerHtml)
          state['ensureNewLine']()
          state['write']('</details>')
          state['closeBlock'](node)
        },
        parse: {},
      },
    }
  },
})
