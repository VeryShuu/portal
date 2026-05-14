import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import TextAlign from '@tiptap/extension-text-align'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableHeader from '@tiptap/extension-table-header'
import TableCell from '@tiptap/extension-table-cell'
import { Markdown } from 'tiptap-markdown'
import { IframeEmbed } from './extensions/IframeEmbed'
import { AlignedParagraph, AlignedHeading } from './extensions/AlignedNodes'
import { Callout } from './extensions/Callout'
import { Details } from './extensions/Details'

export function buildEditorExtensions(placeholder = '') {
  return [
    StarterKit.configure({
      paragraph: false,
      heading: false,
    }),
    AlignedParagraph,
    AlignedHeading,
    Placeholder.configure({ placeholder }),
    Link.configure({ openOnClick: false, HTMLAttributes: {} }),
    Image,
    TextAlign.configure({
      types: ['heading', 'paragraph'],
      alignments: ['left', 'center', 'right'],
    }),
    Table.configure({ resizable: true }),
    TableRow,
    TableHeader,
    TableCell,
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
