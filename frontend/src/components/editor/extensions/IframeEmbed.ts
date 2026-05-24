import { Node, mergeAttributes } from '@tiptap/core'

export interface IframeEmbedOptions {
  HTMLAttributes: Record<string, unknown>
  allowedDomains: string[]
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    iframeEmbed: {
      setIframe: (options: { src: string; title?: string }) => ReturnType
    }
  }
}

function isAllowedSrc(src: string | null | undefined, allowedDomains: string[]): boolean {
  if (!src) return false
  try {
    const url = new URL(src)
    return allowedDomains.some((domain) => url.hostname === domain || url.hostname.endsWith(`.${domain}`))
  } catch {
    return false
  }
}

export const IframeEmbed = Node.create<IframeEmbedOptions>({
  name: 'iframeEmbed',

  addOptions() {
    return {
      HTMLAttributes: {},
      allowedDomains: [
        'youtube.com',
        'youtu.be',
        'youtube-nocookie.com',
        'rutube.ru',
        'vimeo.com',
        'vk.com',
        'vk.video',
      ],
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
    return [
      {
        tag: 'iframe',
        getAttrs: (node) => {
          const el = node as HTMLIFrameElement
          const src = el.getAttribute('src')
          if (!isAllowedSrc(src, this.options.allowedDomains)) {
            return false
          }
          return null
        },
      },
    ]
  },

  renderHTML({ HTMLAttributes }) {
    if (!isAllowedSrc(HTMLAttributes.src as string, this.options.allowedDomains)) {
      return ['div', { class: 'iframe-wrapper iframe-wrapper--blocked' }]
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
          if (!isAllowedSrc(options.src, this.options.allowedDomains)) {
            return false
          }
          return commands.insertContent({
            type: this.name,
            attrs: options,
          })
        },
    }
  },
})
