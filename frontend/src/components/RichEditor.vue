<template>
  <div class="editor-wrap">
    <div v-if="editor" class="toolbar">
      <n-button-group size="small">
        <n-button quaternary :type="editor.isActive('bold') ? 'primary' : 'default'" @click="editor.chain().focus().toggleBold().run()">
          <b>B</b>
        </n-button>
        <n-button quaternary :type="editor.isActive('italic') ? 'primary' : 'default'" @click="editor.chain().focus().toggleItalic().run()">
          <i>I</i>
        </n-button>
        <n-button quaternary :type="editor.isActive('strike') ? 'primary' : 'default'" @click="editor.chain().focus().toggleStrike().run()">
          <s>S</s>
        </n-button>
      </n-button-group>

      <n-button-group size="small">
        <n-button quaternary :type="editor.isActive('heading', { level: 2 }) ? 'primary' : 'default'" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">
          H2
        </n-button>
        <n-button quaternary :type="editor.isActive('heading', { level: 3 }) ? 'primary' : 'default'" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">
          H3
        </n-button>
      </n-button-group>

      <n-button-group size="small">
        <n-button quaternary :type="editor.isActive('bulletList') ? 'primary' : 'default'" @click="editor.chain().focus().toggleBulletList().run()">
          ≡
        </n-button>
        <n-button quaternary :type="editor.isActive('orderedList') ? 'primary' : 'default'" @click="editor.chain().focus().toggleOrderedList().run()">
          1.
        </n-button>
        <n-button quaternary :type="editor.isActive('blockquote') ? 'primary' : 'default'" @click="editor.chain().focus().toggleBlockquote().run()">
          "
        </n-button>
        <n-button quaternary :type="editor.isActive('codeBlock') ? 'primary' : 'default'" @click="editor.chain().focus().toggleCodeBlock().run()">
          &lt;/&gt;
        </n-button>
      </n-button-group>

      <n-button size="small" quaternary title="Вставить изображение" @click="triggerImageUpload">
        🖼
      </n-button>

      <n-button
        v-if="allowedIframeOrigins && allowedIframeOrigins.length"
        size="small"
        quaternary
        title="Вставить видео"
        @click="showVideoDialog = true"
      >
        ▶
      </n-button>

      <n-button size="small" quaternary @click="editor.chain().focus().undo().run()">↩</n-button>
      <n-button size="small" quaternary @click="editor.chain().focus().redo().run()">↪</n-button>
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

    <n-modal v-model:show="showVideoDialog" preset="dialog" title="Вставить видео">
      <n-input
        v-model:value="videoUrl"
        placeholder="https://video.company.local/videos/watch/..."
        clearable
      />
      <template #action>
        <n-button size="small" @click="showVideoDialog = false">Отмена</n-button>
        <n-button size="small" type="primary" @click="insertVideo">Вставить</n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import { Markdown } from 'tiptap-markdown'
import { NButton, NButtonGroup, NModal, NInput } from 'naive-ui'
import { apiUpload } from '@/api'
import { IframeEmbed } from './editor/extensions/IframeEmbed'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  articleId?: string
  allowedIframeOrigins?: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

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
    Markdown.configure({
      html: false,
      transformPastedText: true,
      transformCopiedText: true,
    }),
    IframeEmbed.configure({
      allowedOrigins: props.allowedIframeOrigins ?? [],
    }),
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

function insertVideo() {
  const src = videoUrl.value.trim()
  if (!src) return
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
