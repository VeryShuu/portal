import { Node, mergeAttributes } from '@tiptap/core'
import {
  DEFAULT_VIDEO_IFRAME_ORIGINS,
  hostsFromOrigins,
  parseVideoEmbed,
} from '../../../utils/videoEmbed'

export interface IframeEmbedOptions {
  HTMLAttributes: Record<string, unknown>
  // Origin'ы из настройки video_iframe_origins (bootstrap.allowed_iframe_origins);
  // хост-гейт и конвертация — через общий парсер utils/videoEmbed.
  allowedOrigins: string[]
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    iframeEmbed: {
      setIframe: (options: { src: string; title?: string }) => ReturnType
    }
  }
}

function isAllowedSrc(src: string | null | undefined, allowedOrigins: string[]): boolean {
  if (!src) return false
  const domains = hostsFromOrigins(allowedOrigins)
  try {
    const url = new URL(src)
    return domains.some((domain) => url.hostname === domain || url.hostname.endsWith(`.${domain}`))
  } catch {
    return false
  }
}

export const IframeEmbed = Node.create<IframeEmbedOptions>({
  name: 'iframeEmbed',

  addOptions() {
    return {
      HTMLAttributes: {},
      // Источник истины — настройка video_iframe_origins (Admin UI → System):
      // RichEditor передаёт origin'ы из bootstrap.allowed_iframe_origins при
      // создании редактора. Дефолт — зеркало дефолта настройки (как у парсера).
      // Старые захардкоженные youtube.com/vk.video сознательно убраны: такие
      // src уже блокируются CSP frame-src.
      allowedOrigins: [...DEFAULT_VIDEO_IFRAME_ORIGINS],
    }
  },

  group: 'block',
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    // this.options доступен здесь: TipTap вызывает addAttributes с биндингом
    // контекста расширения.
    const allowedOrigins = this.options.allowedOrigins
    return {
      src: {
        default: null,
        // Конвертация watch→embed — ЗДЕСЬ, а не в parseHTML-правиле узла:
        // TipTap (injectExtensionAttributesToParseRule) перекрывает результат
        // getAttrs сырыми атрибутами DOM, а атрибутный parseHTML применяется
        // последним и выигрывает.
        parseHTML: (element) => {
          const src = element.getAttribute('src')
          if (!src || !isAllowedSrc(src, allowedOrigins)) {
            return src
          }
          const info = parseVideoEmbed(src, allowedOrigins)
          return info?.embedUrl ?? src
        },
      },
      title: { default: '' },
      width: { default: '100%' },
      height: { default: '360' },
    }
  },

  parseHTML() {
    // this.options захватываем в замыкание: prosemirror вызывает getAttrs без
    // контекста, а сам parseHTML TipTap вызывает с биндингом на расширение.
    const allowedOrigins = this.options.allowedOrigins
    return [
      {
        tag: 'iframe',
        getAttrs: (node) => {
          const el = node as HTMLIFrameElement
          if (!isAllowedSrc(el.getAttribute('src'), allowedOrigins)) {
            return false
          }
          // src конвертируется в атрибутном parseHTML (см. addAttributes).
          return null
        },
      },
    ]
  },

  renderHTML({ HTMLAttributes }) {
    if (!isAllowedSrc(HTMLAttributes.src as string, this.options.allowedOrigins)) {
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

  addStorage() {
    return {
      markdown: {
        // tiptap-markdown: узел без сериализатора молча выпадает при сохранении
        // (тело новости/статьи — markdown). Пишем iframe сырым HTML: его
        // пропускают mdUnsafe (html:true) и sanitize-гейты (origin из того же
        // списка), а при повторном открытии в редакторе узел восстанавливается
        // через parseHTML.
        serialize(
          state: Record<string, CallableFunction>,
          node: { attrs: { src: string | null; title?: string | null; width?: string | null; height?: string | null } },
        ) {
          const esc = (v: string) =>
            v.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          // sandbox — ПОСЛЕДНИМ атрибутом: backend-санитайзер (sanitize.py,
          // _IFRAME_SANDBOX_RE) заменяет существующий sandbox только когда он
          // стоит непосредственно перед `>`, иначе дублирует атрибут.
          const attrs = [
            `src="${esc(node.attrs.src ?? '')}"`,
            `title="${esc(node.attrs.title ?? '')}"`,
            `width="${esc(node.attrs.width ?? '100%')}"`,
            `height="${esc(node.attrs.height ?? '360')}"`,
            'allowfullscreen',
            'loading="lazy"',
            'sandbox="allow-scripts allow-same-origin allow-presentation"',
          ].join(' ')
          state['write'](`<iframe ${attrs}></iframe>`)
          state['closeBlock'](node)
        },
        parse: {},
      },
    }
  },

  addCommands() {
    return {
      setIframe:
        (options) =>
        ({ commands }) => {
          if (!isAllowedSrc(options.src, this.options.allowedOrigins)) {
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
