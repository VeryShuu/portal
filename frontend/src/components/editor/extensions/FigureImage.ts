import { Node, mergeAttributes } from '@tiptap/core'

export interface FigureImageAttrs {
  src: string
  alt?: string | null
  title?: string | null
  caption?: string | null
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    figureImage: {
      setFigureImage: (attrs: FigureImageAttrs) => ReturnType
      updateFigureImage: (attrs: Partial<FigureImageAttrs>) => ReturnType
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

function escapeAttr(text: string): string {
  return escapeHtml(text).replace(/'/g, '&#39;')
}

export const FigureImage = Node.create({
  name: 'figureImage',
  group: 'block',
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      src: {
        default: '',
        parseHTML: (el) => {
          const element = el as HTMLElement
          if (element.tagName.toLowerCase() === 'img') {
            return element.getAttribute('src') ?? ''
          }
          return element.querySelector('img')?.getAttribute('src') ?? ''
        },
        renderHTML: () => ({}),
      },
      alt: {
        default: '',
        parseHTML: (el) => {
          const element = el as HTMLElement
          if (element.tagName.toLowerCase() === 'img') {
            return element.getAttribute('alt') ?? ''
          }
          return element.querySelector('img')?.getAttribute('alt') ?? ''
        },
        renderHTML: () => ({}),
      },
      title: {
        default: '',
        parseHTML: (el) => {
          const element = el as HTMLElement
          if (element.tagName.toLowerCase() === 'img') {
            return element.getAttribute('title') ?? ''
          }
          return element.querySelector('img')?.getAttribute('title') ?? ''
        },
        renderHTML: () => ({}),
      },
      caption: {
        default: '',
        parseHTML: (el) => {
          const element = el as HTMLElement
          if (element.tagName.toLowerCase() === 'img') return ''
          return element.querySelector('figcaption')?.textContent?.trim() ?? ''
        },
        renderHTML: () => ({}),
      },
    }
  },

  parseHTML() {
    return [
      { tag: 'figure', priority: 60 },
      { tag: 'img[src]', priority: 50 },
    ]
  },

  renderHTML({ node, HTMLAttributes }) {
    const { src, alt, title, caption } = node.attrs as FigureImageAttrs
    const imgAttrs: Record<string, string> = { src: src || '' }
    if (alt) imgAttrs['alt'] = alt
    if (title) imgAttrs['title'] = title

    const children: unknown[] = [['img', mergeAttributes(HTMLAttributes, imgAttrs)]]
    if (caption && caption.trim()) {
      children.push(['figcaption', {}, caption])
    }
    return ['figure', { 'data-type': 'figure-image' }, ...children] as unknown as [
      string,
      Record<string, unknown>,
      ...unknown[],
    ]
  },

  addCommands() {
    return {
      setFigureImage:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: {
              src: attrs.src,
              alt: attrs.alt ?? '',
              title: attrs.title ?? '',
              caption: attrs.caption ?? '',
            },
          }),
      updateFigureImage:
        (attrs) =>
        ({ commands }) =>
          commands.updateAttributes(this.name, attrs),
    }
  },

  addStorage() {
    return {
      markdown: {
        serialize(
          state: Record<string, CallableFunction>,
          node: { attrs: FigureImageAttrs },
        ) {
          const { src, alt, title, caption } = node.attrs
          const safeSrc = src || ''
          const safeAlt = alt || ''
          const trimmedCaption = (caption || '').trim()

          if (!trimmedCaption) {
            const titlePart = title ? ` "${title.replace(/"/g, '\\"')}"` : ''
            state['write'](`![${safeAlt}](${safeSrc}${titlePart})`)
            state['closeBlock'](node)
            return
          }

          const imgAttrs = [`src="${escapeAttr(safeSrc)}"`]
          if (safeAlt) imgAttrs.push(`alt="${escapeAttr(safeAlt)}"`)
          if (title) imgAttrs.push(`title="${escapeAttr(title)}"`)
          state['write']('<figure data-type="figure-image">')
          state['ensureNewLine']()
          state['write'](`<img ${imgAttrs.join(' ')} />`)
          state['ensureNewLine']()
          state['write'](`<figcaption>${escapeHtml(trimmedCaption)}</figcaption>`)
          state['ensureNewLine']()
          state['write']('</figure>')
          state['closeBlock'](node)
        },
        parse: {},
      },
    }
  },
})
