import { Node, mergeAttributes } from '@tiptap/core'

export interface IframeEmbedOptions {
  allowedOrigins: string[]
  HTMLAttributes: Record<string, unknown>
}

function isAllowedSrc(src: string, allowedOrigins: string[]): boolean {
  if (!src || !allowedOrigins.length) return false
  try {
    const origin = new URL(src).origin
    return allowedOrigins.some((o) => {
      try {
        return new URL(o).origin === origin
      } catch {
        return false
      }
    })
  } catch {
    return false
  }
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    iframeEmbed: {
      setIframe: (options: { src: string; title?: string }) => ReturnType
    }
  }
}

export const IframeEmbed = Node.create<IframeEmbedOptions>({
  name: 'iframeEmbed',

  addOptions() {
    return {
      allowedOrigins: [],
      HTMLAttributes: {},
    }
  },

  group: 'block',
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      src: { default: null },
      title: { default: '' },
      width: { default: '100%' },
      height: { default: '360' },
    }
  },

  parseHTML() {
    return [{ tag: 'iframe' }]
  },

  renderHTML({ HTMLAttributes }) {
    const src: string = HTMLAttributes.src ?? ''
    if (!isAllowedSrc(src, this.options.allowedOrigins)) {
      return ['div', mergeAttributes(this.options.HTMLAttributes, { class: 'iframe-blocked' }),
        `[Embedded video: ${src}]`]
    }
    return [
      'div',
      { class: 'iframe-wrapper' },
      ['iframe', mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        allowfullscreen: 'true',
        sandbox: 'allow-scripts allow-same-origin allow-presentation',
        loading: 'lazy',
      })],
    ]
  },

  addCommands() {
    return {
      setIframe:
        (options) =>
        ({ commands }) => {
          if (!isAllowedSrc(options.src, this.options.allowedOrigins)) return false
          return commands.insertContent({
            type: this.name,
            attrs: options,
          })
        },
    }
  },
})
