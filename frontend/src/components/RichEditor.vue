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

      <n-button size="small" quaternary :aria-label="t('editor.undo')" @click="editor.chain().focus().undo().run()">↩</n-button>
      <n-button size="small" quaternary :aria-label="t('editor.redo')" @click="editor.chain().focus().redo().run()">↪</n-button>
    </div>

    <editor-content
      :editor="editor"
      class="editor-content"
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
import { Markdown } from 'tiptap-markdown'
import { NButton, NButtonGroup, NCheckbox, NModal, NInput } from 'naive-ui'
import { apiUpload } from '@/api'
import { IframeEmbed } from './editor/extensions/IframeEmbed'
import { AlignedParagraph, AlignedHeading } from './editor/extensions/AlignedNodes'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  articleId?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { t } = useI18n()

const fileInputRef = ref<HTMLInputElement | null>(null)
const showVideoDialog = ref(false)
const videoUrl = ref('')

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
  if (!props.articleId) return null
  const formData = new FormData()
  formData.append('file', file)
  try {
    const data = await apiUpload<{ url: string }>(`/kb/articles/${props.articleId}/media`, formData)
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
</style>
