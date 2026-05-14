<template>
  <div class="editor-wrap">
    <RichEditorToolbar
      v-if="editor"
      :editor="editor"
      @open-link="openLinkDialog"
      @insert-image="triggerImageUpload"
      @open-video="showVideoDialog = true"
      @open-details="openDetailsDialog"
    />

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
import { ref, toRef, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import { NButton, NCheckbox, NModal, NInput } from 'naive-ui'
import RichEditorToolbar from './editor/RichEditorToolbar.vue'
import { buildEditorExtensions } from './editor/useEditorExtensions'
import { useEditorLinkDialog } from './editor/useEditorLinkDialog'
import { useEditorImageUpload } from './editor/useEditorImageUpload'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  uploadEndpoint?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { t } = useI18n()

const showVideoDialog = ref(false)
const videoUrl = ref('')

const showDetailsDialog = ref(false)
const detailsSummary = ref('')

const editor = useEditor({
  content: props.modelValue,
  extensions: buildEditorExtensions(props.placeholder ?? ''),
  onUpdate({ editor }) {
    emit('update:modelValue', editor.storage.markdown.getMarkdown())
  },
})

const {
  showLinkDialog,
  linkEditingExisting,
  linkForm,
  linkUrlError,
  linkDialogTitle,
  linkShowTextField,
  linkUrlStatus,
  canSubmitLink,
  onLinkUrlChange,
  openLinkDialog,
  submitLink,
  removeLink,
} = useEditorLinkDialog(editor)

const {
  fileInputRef,
  triggerImageUpload,
  handleFileInputChange,
  handleDrop,
  handlePaste,
} = useEditorImageUpload(editor, toRef(props, 'uploadEndpoint'))

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

watch(() => props.modelValue, (val) => {
  if (!editor.value) return
  const current = editor.value.storage.markdown.getMarkdown()
  if (current !== val) {
    editor.value.commands.setContent(val, false)
  }
})

onBeforeUnmount(() => editor.value?.destroy())

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
