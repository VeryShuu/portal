<template>
  <div class="editor-wrap">
    <div v-if="editor" class="toolbar">
      <n-button-group size="small">
        <n-button quaternary :aria-label="t('editor.bold')" :type="editor.isActive('bold') ? 'primary' : 'default'" @click="editor.chain().focus().toggleBold().run()">
          <b>B</b>
        </n-button>
        <n-button quaternary :aria-label="t('editor.italic')" :type="editor.isActive('italic') ? 'primary' : 'default'" @click="editor.chain().focus().toggleItalic().run()">
          <i>I</i>
        </n-button>
        <n-button quaternary :aria-label="t('editor.strike')" :type="editor.isActive('strike') ? 'primary' : 'default'" @click="editor.chain().focus().toggleStrike().run()">
          <s>S</s>
        </n-button>
      </n-button-group>

      <n-button-group size="small">
        <n-button quaternary :aria-label="t('editor.heading2')" :type="editor.isActive('heading', { level: 2 }) ? 'primary' : 'default'" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">
          H2
        </n-button>
        <n-button quaternary :aria-label="t('editor.heading3')" :type="editor.isActive('heading', { level: 3 }) ? 'primary' : 'default'" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">
          H3
        </n-button>
      </n-button-group>

      <n-button-group size="small">
        <n-button quaternary :aria-label="t('editor.bulletList')" :type="editor.isActive('bulletList') ? 'primary' : 'default'" @click="editor.chain().focus().toggleBulletList().run()">
          ≡
        </n-button>
        <n-button quaternary :aria-label="t('editor.orderedList')" :type="editor.isActive('orderedList') ? 'primary' : 'default'" @click="editor.chain().focus().toggleOrderedList().run()">
          1.
        </n-button>
        <n-button quaternary :aria-label="t('editor.blockquote')" :type="editor.isActive('blockquote') ? 'primary' : 'default'" @click="editor.chain().focus().toggleBlockquote().run()">
          "
        </n-button>
        <n-button quaternary :aria-label="t('editor.codeBlock')" :type="editor.isActive('codeBlock') ? 'primary' : 'default'" @click="editor.chain().focus().toggleCodeBlock().run()">
          &lt;/&gt;
        </n-button>
      </n-button-group>

      <n-button-group size="small">
        <n-button quaternary :aria-label="t('editor.alignLeft')" :type="editor.isActive({ textAlign: 'left' }) ? 'primary' : 'default'" @click="editor.chain().focus().setTextAlign('left').run()">
          ⯇
        </n-button>
        <n-button quaternary :aria-label="t('editor.alignCenter')" :type="editor.isActive({ textAlign: 'center' }) ? 'primary' : 'default'" @click="editor.chain().focus().setTextAlign('center').run()">
          ☰
        </n-button>
        <n-button quaternary :aria-label="t('editor.alignRight')" :type="editor.isActive({ textAlign: 'right' }) ? 'primary' : 'default'" @click="editor.chain().focus().setTextAlign('right').run()">
          ⯈
        </n-button>
      </n-button-group>

      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.insert_link')"
        :type="editor.isActive('link') ? 'primary' : 'default'"
        @click="openLinkDialog"
      >
        🔗
      </n-button>

      <n-button size="small" quaternary :aria-label="t('editor.insert_image')" @click="triggerImageUpload">
        🖼
      </n-button>

      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.insert_video')"
        @click="showVideoDialog = true"
      >
        ▶
      </n-button>

      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.horizontal_rule')"
        @click="editor.chain().focus().setHorizontalRule().run()"
      >
        —
      </n-button>

      <n-dropdown
        trigger="click"
        :options="tableMenuOptions"
        @select="handleTableMenuSelect"
      >
        <n-button size="small" quaternary :aria-label="t('editor.table.label')">
          ⊞
        </n-button>
      </n-dropdown>

      <n-dropdown
        trigger="click"
        :options="calloutMenuOptions"
        @select="handleCalloutMenuSelect"
      >
        <n-button size="small" quaternary :aria-label="t('editor.callout.label')" :type="editor.isActive('callout') ? 'primary' : 'default'">
          ℹ
        </n-button>
      </n-dropdown>

      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.details.label')"
        :type="editor.isActive('details') ? 'primary' : 'default'"
        @click="openDetailsDialog"
      >
        ▸
      </n-button>

      <n-button size="small" quaternary :aria-label="t('editor.undo')" @click="editor.chain().focus().undo().run()">↩</n-button>
      <n-button size="small" quaternary :aria-label="t('editor.redo')" @click="editor.chain().focus().redo().run()">↪</n-button>
    </div>

    <editor-content
      :editor="editor"
      class="editor-content"
      @click.capture="preventDetailsToggle"
      @drop.prevent="handleDrop"
      @paste="handlePaste"
    />

    <input
      ref="fileInputRef"
      type="file"
      accept="image/*"
      style="display:none"
      @change="handleFileInputChange"
    />

    <n-modal v-model:show="showVideoDialog" preset="dialog" :title="t('editor.insert_video')">
      <n-input
        v-model:value="videoUrl"
        type="textarea"
        :rows="3"
        :placeholder="t('editor.videoUrlPlaceholder')"
        clearable
      />
      <template #action>
        <n-button size="small" @click="showVideoDialog = false">{{ t('common.cancel') }}</n-button>
        <n-button size="small" type="primary" @click="insertVideo">{{ t('editor.insert') }}</n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showLinkDialog"
      preset="dialog"
      :title="linkDialogTitle"
      style="max-width: 480px"
    >
      <div class="link-form">
        <div class="link-field">
          <label class="link-label">{{ t('editor.link.url') }}</label>
          <n-input
            v-model:value="linkForm.url"
            :placeholder="t('editor.link.urlPlaceholder')"
            :status="linkUrlStatus"
            clearable
            @update:value="onLinkUrlChange"
          />
          <div v-if="linkUrlError" class="link-error">{{ linkUrlError }}</div>
        </div>

        <div v-if="linkShowTextField" class="link-field">
          <label class="link-label">{{ t('editor.link.text') }}</label>
          <n-input
            v-model:value="linkForm.text"
            :placeholder="t('editor.link.textPlaceholder')"
            clearable
          />
        </div>

        <n-checkbox v-model:checked="linkForm.newTab">
          {{ t('editor.link.newTab') }}
        </n-checkbox>
        <n-checkbox v-model:checked="linkForm.nofollow">
          {{ t('editor.link.nofollow') }}
        </n-checkbox>
      </div>
      <template #action>
        <n-button
          v-if="linkEditingExisting"
          size="small"
          type="error"
          ghost
          @click="removeLink"
        >
          {{ t('editor.link.remove') }}
        </n-button>
        <n-button size="small" @click="showLinkDialog = false">{{ t('common.cancel') }}</n-button>
        <n-button
          size="small"
          type="primary"
          :disabled="!canSubmitLink"
          @click="submitLink"
        >
          {{ linkEditingExisting ? t('editor.link.update') : t('editor.insert') }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showDetailsDialog"
      preset="dialog"
      :title="t('editor.details.insert')"
      style="max-width: 480px"
    >
      <n-input
        v-model:value="detailsSummary"
        :placeholder="t('editor.details.summaryPlaceholder')"
        clearable
      />
      <template #action>
        <n-button size="small" @click="showDetailsDialog = false">{{ t('common.cancel') }}</n-button>
        <n-button size="small" type="primary" @click="insertDetails">{{ t('editor.insert') }}</n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEditor, EditorContent } from '@tiptap/vue-3'
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
import { NButton, NButtonGroup, NCheckbox, NDropdown, NModal, NInput, useMessage } from 'naive-ui'
import type { DropdownOption } from 'naive-ui'
import { apiUpload } from '@/api'
import { IframeEmbed } from './editor/extensions/IframeEmbed'
import { AlignedParagraph, AlignedHeading } from './editor/extensions/AlignedNodes'
import { Callout } from './editor/extensions/Callout'
import type { CalloutType } from './editor/extensions/Callout'
import { Details } from './editor/extensions/Details'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  uploadEndpoint?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { t } = useI18n()
const message = useMessage()

const fileInputRef = ref<HTMLInputElement | null>(null)
const showVideoDialog = ref(false)
const videoUrl = ref('')

const showDetailsDialog = ref(false)
const detailsSummary = ref('')

const ALLOWED_LINK_SCHEMES = ['http:', 'https:', 'mailto:', 'tel:'] as const

const showLinkDialog = ref(false)
const linkEditingExisting = ref(false)
const linkHasSelection = ref(false)
const linkUrlError = ref('')
const linkForm = reactive({
  url: '',
  text: '',
  newTab: false,
  nofollow: false,
})

const linkDialogTitle = computed(() =>
  linkEditingExisting.value ? t('editor.link.edit') : t('editor.link.insert'),
)
const linkShowTextField = computed(() => !linkHasSelection.value)
const linkUrlStatus = computed<'error' | undefined>(() => (linkUrlError.value ? 'error' : undefined))
const canSubmitLink = computed(() => {
  const url = linkForm.url.trim()
  return Boolean(url) && !linkUrlError.value
})

const tableMenuOptions = computed<DropdownOption[]>(() => [
  { label: t('editor.table.insert'), key: 'insert' },
  { type: 'divider', key: 'd1' },
  { label: t('editor.table.addColBefore'), key: 'addColBefore' },
  { label: t('editor.table.addColAfter'), key: 'addColAfter' },
  { label: t('editor.table.deleteCol'), key: 'deleteCol' },
  { type: 'divider', key: 'd2' },
  { label: t('editor.table.addRowBefore'), key: 'addRowBefore' },
  { label: t('editor.table.addRowAfter'), key: 'addRowAfter' },
  { label: t('editor.table.deleteRow'), key: 'deleteRow' },
  { type: 'divider', key: 'd3' },
  { label: t('editor.table.delete'), key: 'deleteTable' },
])

const calloutMenuOptions = computed<DropdownOption[]>(() => [
  { label: `ℹ ${t('editor.callout.info')}`, key: 'info' },
  { label: `⚠ ${t('editor.callout.warning')}`, key: 'warning' },
  { label: `💡 ${t('editor.callout.tip')}`, key: 'tip' },
  { label: `🚨 ${t('editor.callout.danger')}`, key: 'danger' },
])

function handleTableMenuSelect(key: string) {
  const ed = editor.value
  if (!ed) return
  const chain = ed.chain().focus()
  switch (key) {
    case 'insert':
      chain.insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
      break
    case 'addColBefore':
      chain.addColumnBefore().run()
      break
    case 'addColAfter':
      chain.addColumnAfter().run()
      break
    case 'deleteCol':
      chain.deleteColumn().run()
      break
    case 'addRowBefore':
      chain.addRowBefore().run()
      break
    case 'addRowAfter':
      chain.addRowAfter().run()
      break
    case 'deleteRow':
      chain.deleteRow().run()
      break
    case 'deleteTable':
      chain.deleteTable().run()
      break
  }
}

function handleCalloutMenuSelect(key: string) {
  editor.value?.chain().focus().toggleCallout(key as CalloutType).run()
}

function preventDetailsToggle(event: MouseEvent) {
  const target = event.target as Element | null
  const summary = target?.closest?.('summary') as HTMLElement | null
  if (!summary) return
  const detailsEl = summary.closest('details[data-tiptap-details]') as HTMLElement | null
  if (!detailsEl) return

  event.preventDefault()

  const ed = editor.value
  if (!ed) return

  const view = ed.view
  let pos: number | null = null
  try {
    pos = view.posAtDOM(detailsEl, 0)
  } catch {
    pos = null
  }
  if (pos == null) return

  const $pos = ed.state.doc.resolve(pos)
  for (let depth = $pos.depth; depth >= 0; depth--) {
    const node = $pos.node(depth)
    if (node.type.name === 'details') {
      const nodePos = $pos.before(depth)
      const isOpen = !!node.attrs['open']
      ed.chain()
        .command(({ tr }) => {
          tr.setNodeMarkup(nodePos, undefined, { ...node.attrs, open: !isOpen })
          return true
        })
        .run()
      break
    }
  }
}

function openDetailsDialog() {
  detailsSummary.value = ''
  showDetailsDialog.value = true
}

function insertDetails() {
  const summary = detailsSummary.value.trim()
  editor.value?.chain().focus().insertDetails(summary).run()
  showDetailsDialog.value = false
  detailsSummary.value = ''
}

function isExternalUrl(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin)
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return parsed.origin !== window.location.origin
    }
    return parsed.protocol === 'mailto:' || parsed.protocol === 'tel:'
  } catch {
    return false
  }
}

function normalizeUrl(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return ''
  if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed) || trimmed.startsWith('/') || trimmed.startsWith('#')) {
    return trimmed
  }
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
    return `mailto:${trimmed}`
  }
  return `https://${trimmed}`
}

function validateUrl(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return ''
  const candidate = normalizeUrl(trimmed)
  try {
    const parsed = new URL(candidate, window.location.origin)
    if (!ALLOWED_LINK_SCHEMES.includes(parsed.protocol as typeof ALLOWED_LINK_SCHEMES[number])) {
      return t('editor.link.errorScheme')
    }
    return ''
  } catch {
    return t('editor.link.errorInvalid')
  }
}

let linkUrlAutoToggled = false

function onLinkUrlChange(value: string) {
  linkUrlError.value = validateUrl(value)
  if (!linkEditingExisting.value && !linkUrlAutoToggled && !linkUrlError.value && value.trim()) {
    const external = isExternalUrl(normalizeUrl(value))
    if (external) {
      linkForm.newTab = true
      linkForm.nofollow = true
      linkUrlAutoToggled = true
    }
  }
}

function getSelectedText(): string {
  const ed = editor.value
  if (!ed) return ''
  const { from, to } = ed.state.selection
  if (from === to) return ''
  return ed.state.doc.textBetween(from, to, ' ')
}

function openLinkDialog() {
  const ed = editor.value
  if (!ed) return

  linkUrlError.value = ''
  linkUrlAutoToggled = false

  if (ed.isActive('link')) {
    ed.chain().focus().extendMarkRange('link').run()
    const attrs = ed.getAttributes('link') as { href?: string; target?: string | null; rel?: string | null }
    const href = attrs.href ?? ''
    const rel = attrs.rel ?? ''
    linkEditingExisting.value = true
    linkHasSelection.value = true
    linkForm.url = href
    linkForm.text = getSelectedText()
    linkForm.newTab = attrs.target === '_blank'
    linkForm.nofollow = /\bnofollow\b/.test(rel)
  } else {
    const selected = getSelectedText()
    linkEditingExisting.value = false
    linkHasSelection.value = selected.length > 0
    linkForm.url = ''
    linkForm.text = selected
    linkForm.newTab = false
    linkForm.nofollow = false
  }

  showLinkDialog.value = true
}

function buildRel(nofollow: boolean, newTab: boolean): string | null {
  const parts: string[] = []
  if (newTab) parts.push('noopener', 'noreferrer')
  if (nofollow) parts.push('nofollow')
  return parts.length ? Array.from(new Set(parts)).join(' ') : null
}

function submitLink() {
  const ed = editor.value
  if (!ed) return
  const error = validateUrl(linkForm.url)
  if (error) {
    linkUrlError.value = error
    return
  }
  const href = normalizeUrl(linkForm.url)
  const rel = buildRel(linkForm.nofollow, linkForm.newTab)
  const target = linkForm.newTab ? '_blank' : null

  const attrs = { href, target, rel }

  if (linkEditingExisting.value) {
    ed.chain().focus().extendMarkRange('link').setLink(attrs).run()
  } else if (linkHasSelection.value) {
    ed.chain().focus().setLink(attrs).run()
  } else {
    const text = linkForm.text.trim() || href
    ed.chain()
      .focus()
      .insertContent({
        type: 'text',
        text,
        marks: [{ type: 'link', attrs }],
      })
      .run()
  }

  showLinkDialog.value = false
}

function removeLink() {
  const ed = editor.value
  if (!ed) return
  ed.chain().focus().extendMarkRange('link').unsetLink().run()
  showLinkDialog.value = false
}

watch(showLinkDialog, (open) => {
  if (open) return
  linkEditingExisting.value = false
  linkHasSelection.value = false
  linkUrlError.value = ''
  linkForm.url = ''
  linkForm.text = ''
  linkForm.newTab = false
  linkForm.nofollow = false
})

const editor = useEditor({
  content: props.modelValue,
  extensions: [
    StarterKit.configure({
      paragraph: false,
      heading: false,
    }),
    AlignedParagraph,
    AlignedHeading,
    Placeholder.configure({ placeholder: props.placeholder ?? '' }),
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
  ],
  onUpdate({ editor }) {
    emit('update:modelValue', editor.storage.markdown.getMarkdown())
  },
})

watch(() => props.modelValue, (val) => {
  if (!editor.value) return
  const current = editor.value.storage.markdown.getMarkdown()
  if (current !== val) {
    editor.value.commands.setContent(val, false)
  }
})

onBeforeUnmount(() => editor.value?.destroy())

async function uploadImage(file: File): Promise<string | null> {
  if (!props.uploadEndpoint) {
    message.warning(t('editor.imageUploadDisabled'))
    return null
  }
  const formData = new FormData()
  formData.append('file', file)
  try {
    const data = await apiUpload<{ url: string }>(props.uploadEndpoint, formData)
    return data.url
  } catch {
    return null
  }
}

function insertImage(url: string) {
  editor.value?.chain().focus().setImage({ src: url }).run()
}

function triggerImageUpload() {
  fileInputRef.value?.click()
}

async function handleFileInputChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  const url = await uploadImage(file)
  if (url) insertImage(url)
}

async function handleDrop(event: DragEvent) {
  const files = event.dataTransfer?.files
  if (!files?.length) return
  for (const file of Array.from(files)) {
    if (file.type.startsWith('image/')) {
      const url = await uploadImage(file)
      if (url) insertImage(url)
    }
  }
}

async function handlePaste(event: ClipboardEvent) {
  const items = event.clipboardData?.items
  if (!items) return
  for (const item of Array.from(items)) {
    if (item.type.startsWith('image/')) {
      event.preventDefault()
      const file = item.getAsFile()
      if (!file) continue
      const url = await uploadImage(file)
      if (url) insertImage(url)
    }
  }
}

function extractEmbedSrc(input: string): string {
  const match = input.match(/src=["']([^"']+)["']/)
  return match ? match[1] : input
}

function insertVideo() {
  const raw = videoUrl.value.trim()
  if (!raw) return
  const src = extractEmbedSrc(raw)
  editor.value?.commands.setIframe({ src, title: '' })
  videoUrl.value = ''
  showVideoDialog.value = false
}
</script>

<style scoped>
.editor-wrap {
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 8px;
  overflow: hidden;
}
.toolbar {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border-bottom: 1px solid var(--n-border-color, #e0e0e6);
  background: var(--n-color, #fff);
}
.editor-content {
  min-height: 240px;
  padding: 16px;
}
.editor-content :deep(.ProseMirror) {
  outline: none;
  min-height: 200px;
  font-size: 15px;
  line-height: 1.7;
}
.link-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}
.link-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.link-label {
  font-size: 13px;
  color: var(--n-text-color-2, #666);
}
.link-error {
  font-size: 12px;
  color: var(--n-error-color, #d03050);
}
.editor-content :deep(.ProseMirror p.is-editor-empty:first-child::before) {
  color: #aaa;
  content: attr(data-placeholder);
  float: left;
  height: 0;
  pointer-events: none;
}

.editor-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
  table-layout: fixed;
}
.editor-content :deep(table td),
.editor-content :deep(table th) {
  border: 1px solid var(--n-border-color, #e0e0e6);
  padding: 6px 10px;
  vertical-align: top;
  min-width: 60px;
  position: relative;
}
.editor-content :deep(table th) {
  background: var(--n-table-header-color, #f5f5f7);
  font-weight: 600;
}
.editor-content :deep(.selectedCell) {
  background: var(--n-primary-color-suppl, #e8f4ff);
}
.editor-content :deep(.column-resize-handle) {
  position: absolute;
  right: -2px;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--n-primary-color, #18a058);
  cursor: col-resize;
  pointer-events: all;
}
.editor-content :deep(.tableWrapper) {
  overflow-x: auto;
}

.editor-content :deep(div[data-callout]) {
  border-radius: 6px;
  padding: 12px 16px;
  margin: 1em 0;
  border-left: 4px solid;
}
.editor-content :deep(div[data-callout][data-type="info"]) {
  background: #e8f4ff;
  border-color: #2080f0;
  color: #1a3a5c;
}
.editor-content :deep(div[data-callout][data-type="warning"]) {
  background: #fff8e6;
  border-color: #f0a020;
  color: #5c3a00;
}
.editor-content :deep(div[data-callout][data-type="tip"]) {
  background: #edfaef;
  border-color: #18a058;
  color: #0d3d1f;
}
.editor-content :deep(div[data-callout][data-type="danger"]) {
  background: #fff0f0;
  border-color: #d03050;
  color: #5c0d1a;
}

.editor-content :deep(details) {
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 6px;
  padding: 0;
  margin: 1em 0;
  overflow: hidden;
}
.editor-content :deep(details > summary) {
  padding: 10px 14px;
  font-weight: 600;
  cursor: pointer;
  background: var(--n-table-header-color, #f5f5f7);
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.editor-content :deep(details > summary::-webkit-details-marker) {
  display: none;
}
.editor-content :deep(details > summary::before) {
  content: '▶';
  font-size: 10px;
  transition: transform 0.2s;
  display: inline-block;
}
.editor-content :deep(details[open] > summary::before) {
  transform: rotate(90deg);
}
.editor-content :deep(details > *:not(summary)) {
  padding: 12px 14px;
}
</style>
