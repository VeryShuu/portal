import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import TextAlign from '@tiptap/extension-text-align'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableHeader from '@tiptap/extension-table-header'
import TableCell from '@tiptap/extension-table-cell'
import Underline from '@tiptap/extension-underline'
import Subscript from '@tiptap/extension-subscript'
import Superscript from '@tiptap/extension-superscript'
import Highlight from '@tiptap/extension-highlight'
import Focus from '@tiptap/extension-focus'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import { Markdown } from 'tiptap-markdown'
import { IframeEmbed } from './IframeEmbed'
import { AlignedParagraph, AlignedHeading } from './AlignedNodes'
import { Callout } from './Callout'
import { Details } from './Details'
import { LinkExtension } from './link'
import { ImageUploadExtension } from './image-upload'

export function buildEditorExtensions(placeholder = '') {
  return [
    StarterKit.configure({
      paragraph: false,
      heading: false,
    }),
    AlignedParagraph,
    AlignedHeading,
    Placeholder.configure({ placeholder }),
    LinkExtension,
    ImageUploadExtension,
    TextAlign.configure({
      types: ['heading', 'paragraph'],
      alignments: ['left', 'center', 'right'],
    }),
    Table.configure({ resizable: true }),
    TableRow,
    TableHeader,
    TableCell,
    Underline,
    Subscript,
    Superscript,
    Highlight.configure({ multicolor: false }),
    Focus.configure({ className: 'has-focus', mode: 'shallowest' }),
    TaskList,
    TaskItem.configure({ nested: true }),
    Callout,
    Details,
    Markdown.configure({
      html: true,
      transformPastedText: true,
      transformCopiedText: true,
    }),
    IframeEmbed,
  ]
}
