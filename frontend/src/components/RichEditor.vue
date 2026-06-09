<template>
  <div
    class="editor-wrap"
    :class="{ 'is-fullscreen': isFullscreen, 'is-focus': isFocusMode }"
  >
    <RichEditorToolbar
      v-if="editor"
      :editor="editor"
      :fullscreen="isFullscreen"
      :focus-mode="isFocusMode"
      @open-link="openLinkDialog"
      @insert-image="triggerImageUpload"
      @open-video="showVideoDialog = true"
      @open-details="openDetailsDialog"
      @toggle-fullscreen="toggleFullscreen"
      @toggle-focus="toggleFocusMode"
    />

    <RichEditorBubbleMenu
      v-if="editor"
      :editor="editor"
      :should-show="shouldShowBubbleMenu"
      @open-link="openLinkDialog"
    />

    <editor-content
      :editor="editor"
      class="editor-content"
      @click.capture="preventDetailsToggle"
      @dblclick="handleEditorDblClick"
      @drop.prevent="handleDrop"
      @paste="handlePaste"
    />

    <input
      ref="fileInputRef"
      type="file"
      accept="image/*"
      style="display:none"
      aria-label="Upload image"
      @change="handleFileInputChange"
    >

    <RichEditorImageModal
      v-model:show="showImageDialog"
      v-model:alt="imageForm.alt"
      v-model:caption="imageForm.caption"
      :src="imageForm.src"
      @submit="submitImageDialog"
      @cancel="cancelImageDialog"
    />

    <RichEditorVideoModal
      v-model:show="showVideoDialog"
      v-model:url="videoUrl"
      @insert="insertVideo"
    />

    <RichEditorLinkModal
      v-model:show="showLinkDialog"
      v-model:tab="linkTab"
      v-model:kb-active-index="kbActiveIndex"
      v-model:url="linkForm.url"
      v-model:text="linkForm.text"
      v-model:new-tab="linkForm.newTab"
      v-model:nofollow="linkForm.nofollow"
      :title="linkDialogTitle"
      :url-status="linkUrlStatus"
      :url-error="linkUrlError"
      :show-text-field="linkShowTextField"
      :editing-existing="linkEditingExisting"
      :can-submit="canSubmitLink"
      :kb-query="kbSearchQuery"
      :kb-loading="kbSearchLoading"
      :kb-min-length="kbMinLength"
      :kb-results="kbSearchResults"
      :on-url-change="onLinkUrlChange"
      :is-internal-kb-link="isInternalKbLink"
      :on-kb-search-input="onKbSearchInput"
      :on-kb-keydown="onKbKeydown"
      :select-kb-article="selectKbArticle"
      :highlight-kb-match="highlightKbMatch"
      @remove="removeLink"
      @submit="submitLink"
    />

    <RichEditorDetailsModal
      v-model:show="showDetailsDialog"
      v-model:summary="detailsSummary"
      @insert="insertDetails"
    />
  </div>
</template>

<script setup lang="ts">
import { toRef, watch, onBeforeUnmount } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import RichEditorToolbar from './editor/toolbar/RichEditorToolbar.vue'
import RichEditorBubbleMenu from './editor/RichEditorBubbleMenu.vue'
import RichEditorImageModal from './editor/RichEditorImageModal.vue'
import RichEditorVideoModal from './editor/RichEditorVideoModal.vue'
import RichEditorDetailsModal from './editor/RichEditorDetailsModal.vue'
import RichEditorLinkModal from './editor/RichEditorLinkModal.vue'
import { buildEditorExtensions } from './editor/extensions'
import { useEditorLinkDialog } from './editor/useEditorLinkDialog'
import { useEditorImageUpload } from './editor/useEditorImageUpload'
import { useEditorVideoDialog } from './editor/useEditorVideoDialog'
import { useEditorDetailsDialog } from './editor/useEditorDetailsDialog'
import { useEditorFullscreen } from './editor/useEditorFullscreen'
import { useEditorBubbleMenu } from './editor/useEditorBubbleMenu'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  uploadEndpoint?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

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
  linkTab,
  kbSearchQuery,
  kbSearchResults,
  kbSearchLoading,
  kbActiveIndex,
  onKbSearchInput,
  onKbKeydown,
  selectKbArticle,
  highlightKbMatch,
  isInternalKbLink,
  kbMinLength,
} = useEditorLinkDialog(editor)

const {
  fileInputRef,
  triggerImageUpload,
  handleFileInputChange,
  handleDrop,
  handlePaste,
  showImageDialog,
  imageForm,
  openImageDialogForEdit,
  submitImageDialog,
  cancelImageDialog,
} = useEditorImageUpload(editor, toRef(props, 'uploadEndpoint'))

const { showVideoDialog, videoUrl, insertVideo } = useEditorVideoDialog(editor)

const {
  showDetailsDialog, detailsSummary,
  openDetailsDialog, insertDetails, preventDetailsToggle,
} = useEditorDetailsDialog(editor)

watch(() => props.modelValue, (val) => {
  if (!editor.value) return
  const current = editor.value.storage.markdown.getMarkdown()
  if (current !== val) {
    editor.value.commands.setContent(val, false)
  }
})

const { isFullscreen, isFocusMode, toggleFullscreen, toggleFocusMode } = useEditorFullscreen()

const { shouldShowBubbleMenu, handleEditorDblClick } = useEditorBubbleMenu(openImageDialogForEdit)

onBeforeUnmount(() => editor.value?.destroy())

</script>

<style scoped>
.editor-wrap {
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.editor-wrap.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9000;
  border-radius: 0;
  border: none;
  background: var(--n-color, #fff);
  display: flex;
  flex-direction: column;
}
.editor-wrap.is-fullscreen .editor-content {
  flex: 1;
  overflow-y: auto;
  max-height: none;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
}
.editor-wrap.is-focus .editor-content :deep(.ProseMirror) > * {
  opacity: 0.35;
  transition: opacity 0.2s ease;
}
.editor-wrap.is-focus .editor-content :deep(.ProseMirror) > .has-focus,
.editor-wrap.is-focus .editor-content :deep(.ProseMirror) > *:focus-within {
  opacity: 1;
}
.editor-content {
  flex: 1 1 auto;
  min-height: 240px;
  max-height: var(--editor-content-max-height, 60vh);
  overflow-y: auto;
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

.editor-content :deep(figure[data-type="figure-image"]) {
  margin: 1em 0;
  text-align: center;
}
.editor-content :deep(figure[data-type="figure-image"] img) {
  max-width: 100%;
  height: auto;
  display: inline-block;
}
.editor-content :deep(figure[data-type="figure-image"] figcaption) {
  margin-top: 6px;
  font-size: 13px;
  font-style: italic;
  color: var(--n-text-color-2, #888);
}
.editor-content :deep(mark) {
  background: #fff3a0;
  padding: 0 2px;
  border-radius: 2px;
}
.editor-content :deep(ul[data-type="taskList"]) {
  list-style: none;
  padding-left: 0;
}
.editor-content :deep(ul[data-type="taskList"] li) {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 2px 0;
}
.editor-content :deep(ul[data-type="taskList"] li > label) {
  margin-top: 2px;
  user-select: none;
  flex: 0 0 auto;
}
.editor-content :deep(ul[data-type="taskList"] li > div) {
  flex: 1 1 auto;
  min-width: 0;
}
.editor-content :deep(ul[data-type="taskList"] li[data-checked="true"] > div) {
  text-decoration: line-through;
  color: var(--n-text-color-3, #999);
}
.editor-content :deep(code:not(pre code)) {
  background: var(--n-code-color, #f5f5f7);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 0.9em;
}
</style>
