import Paragraph from '@tiptap/extension-paragraph'
import Heading from '@tiptap/extension-heading'
import { defaultMarkdownSerializer } from 'prosemirror-markdown'
import type { MarkdownSerializerState } from 'prosemirror-markdown'
import type { Node as PMNode } from '@tiptap/pm/model'

type AlignValue = 'left' | 'center' | 'right' | 'justify'

type SerializeFn = (state: MarkdownSerializerState, node: PMNode, parent: PMNode, index: number) => void

function serializeWithAlign(
  defaultSerialize: SerializeFn,
  htmlTag: (node: PMNode, align: AlignValue) => { open: string; close: string },
) {
  return function serialize(state: MarkdownSerializerState, node: PMNode, parent: PMNode, index: number) {
    const align = node.attrs.textAlign as AlignValue | null | undefined
    if (align && align !== 'left') {
      const { open, close } = htmlTag(node, align)
      state.write(open)
      state.renderInline(node)
      state.write(close)
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
          (_node, align) => ({
            open: `<p style="text-align: ${align}">`,
            close: '</p>',
          }),
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
          (node, align) => {
            const level = (node.attrs.level as number) ?? 1
            return {
              open: `<h${level} style="text-align: ${align}">`,
              close: `</h${level}>`,
            }
          },
        ),
        parse: {},
      },
    }
  },
})
