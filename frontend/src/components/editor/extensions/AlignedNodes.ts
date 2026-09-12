import Paragraph from '@tiptap/extension-paragraph'
import Heading from '@tiptap/extension-heading'
import { defaultMarkdownSerializer } from 'prosemirror-markdown'
import type { MarkdownSerializerState } from 'prosemirror-markdown'
import { DOMSerializer } from '@tiptap/pm/model'
import type { Node as PMNode } from '@tiptap/pm/model'

type AlignValue = 'left' | 'center' | 'right' | 'justify'

type SerializeFn = (state: MarkdownSerializerState, node: PMNode, parent: PMNode, index: number) => void

function serializeInlineToHtml(node: PMNode): string {
  if (typeof document === 'undefined') return node.textContent
  const serializer = DOMSerializer.fromSchema(node.type.schema)
  const fragment = serializer.serializeFragment(node.content)
  const tmp = document.createElement('div')
  tmp.appendChild(fragment)
  return tmp.innerHTML
}

function serializeWithAlign(
  defaultSerialize: SerializeFn,
  htmlTag: (node: PMNode, align: AlignValue, innerHtml: string) => string,
) {
  return function serialize(state: MarkdownSerializerState, node: PMNode, parent: PMNode, index: number) {
    const align = node.attrs.textAlign as AlignValue | null | undefined
    if (align && align !== 'left') {
      const innerHtml = serializeInlineToHtml(node)
      state.write(htmlTag(node, align, innerHtml))
      state.closeBlock(node)
      return
    }
    defaultSerialize(state, node, parent, index)
  }
}

export const AlignedParagraph = Paragraph.extend({
  addStorage() {
    return {
      markdown: {
        serialize: serializeWithAlign(
          defaultMarkdownSerializer.nodes.paragraph,
          (_node, align, innerHtml) => `<p style="text-align: ${align}">${innerHtml}</p>`,
        ),
        parse: {},
      },
    }
  },
})

export const AlignedHeading = Heading.extend({
  addStorage() {
    return {
      markdown: {
        serialize: serializeWithAlign(
          defaultMarkdownSerializer.nodes.heading,
          (node, align, innerHtml) => {
            const level = (node.attrs.level as number) ?? 1
            return `<h${level} style="text-align: ${align}">${innerHtml}</h${level}>`
          },
        ),
        parse: {},
      },
    }
  },
})
