import MarkdownIt from 'markdown-it'

export const mdSafe = new MarkdownIt({ html: false, linkify: true, typographer: true })

export const mdUnsafe = new MarkdownIt({ html: true, linkify: true, typographer: true })
