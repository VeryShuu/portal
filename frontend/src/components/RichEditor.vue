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
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import TextAlign from '@tiptap/extension-text-align'
import { Markdown } from 'tiptap-markdown'
import { NButton, NButtonGroup, NModal, NInput } from 'naive-ui'
import { apiUpload } from '@/api'
import { IframeEmbed } from './editor/extensions/IframeEmbed'

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

const editor = useEditor({
  content: props.modelValue,
  extensions: [
    StarterKit,
    Placeholder.configure({ placeholder: props.placeholder ?? '' }),
    Link.configure({ openOnClick: false }),
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
.editor-content :deep(.ProseMirror p.is-editor-empty:first-child::before) {
  color: #aaa;
  content: attr(data-placeholder);
  float: left;
  height: 0;
  pointer-events: none;
}
</style>
