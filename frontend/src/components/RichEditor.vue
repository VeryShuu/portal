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

    <bubble-menu
      v-if="editor"
      :editor="editor"
      :tippy-options="{ duration: 100, placement: 'top' }"
      :should-show="shouldShowBubbleMenu"
      class="bubble-menu"
    >
      <n-button-group size="small">
        <n-button
          quaternary
          :aria-label="t('editor.bold')"
          :type="editor.isActive('bold') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleBold().run()"
        >
          <b>B</b>
        </n-button>
        <n-button
          quaternary
          :aria-label="t('editor.italic')"
          :type="editor.isActive('italic') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleItalic().run()"
        >
          <i>I</i>
        </n-button>
        <n-button
          quaternary
          :aria-label="t('editor.underline')"
          :type="editor.isActive('underline') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleUnderline().run()"
        >
          <u>U</u>
        </n-button>
        <n-button
          quaternary
          :aria-label="t('editor.strike')"
          :type="editor.isActive('strike') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleStrike().run()"
        >
          <s>S</s>
        </n-button>
        <n-button
          quaternary
          :aria-label="t('editor.code')"
          :type="editor.isActive('code') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleCode().run()"
        >
          <span style="font-family: monospace;">&lt;&gt;</span>
        </n-button>
        <n-button
          quaternary
          :aria-label="t('editor.link.insert')"
          :type="editor.isActive('link') ? 'primary' : 'default'"
          @click="openLinkDialog"
        >
          🔗
        </n-button>
        <n-button
          quaternary
          :aria-label="t('editor.highlight')"
          :type="editor.isActive('highlight') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleHighlight().run()"
        >
          <mark style="background: #ffe066; padding: 0 2px;">H</mark>
        </n-button>
      </n-button-group>
    </bubble-menu>

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

    <n-modal
      v-model:show="showImageDialog"
      preset="dialog"
      :title="t('editor.image.dialogTitle')"
      style="max-width: 480px"
    >
      <div class="link-form">
        <div
          v-if="imageForm.src"
          class="image-preview"
        >
          <img
            :src="imageForm.src"
            :alt="imageForm.alt || ''"
          >
        </div>
        <div class="link-field">
          <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
          <label
            class="link-label"
            for="image-alt-input"
          >{{ t('editor.image.alt') }}</label>
          <n-input
            v-model:value="imageForm.alt"
            :placeholder="t('editor.image.altPlaceholder')"
            :input-props="{ id: 'image-alt-input' }"
            clearable
          />
        </div>
        <div class="link-field">
          <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
          <label
            class="link-label"
            for="image-caption-input"
          >{{ t('editor.image.caption') }}</label>
          <n-input
            v-model:value="imageForm.caption"
            type="textarea"
            :rows="2"
            :placeholder="t('editor.image.captionPlaceholder')"
            :input-props="{ id: 'image-caption-input' }"
            clearable
          />
        </div>
      </div>
      <template #action>
        <n-button
          size="small"
          @click="cancelImageDialog"
        >
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          size="small"
          type="primary"
          :disabled="!imageForm.src"
          @click="submitImageDialog"
        >
          {{ t('editor.insert') }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showVideoDialog"
      preset="dialog"
      :title="t('editor.insert_video')"
    >
      <n-input
        v-model:value="videoUrl"
        type="textarea"
        :rows="3"
        :placeholder="t('editor.videoUrlPlaceholder')"
        clearable
      />
      <template #action>
        <n-button
          size="small"
          @click="showVideoDialog = false"
        >
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          size="small"
          type="primary"
          @click="insertVideo"
        >
          {{ t('editor.insert') }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showLinkDialog"
      preset="dialog"
      :title="linkDialogTitle"
      style="max-width: 480px"
    >
      <n-tabs
        v-model:value="linkTab"
        type="line"
        size="small"
        animated
      >
        <n-tab-pane
          name="url"
          :tab="t('editor.link.tabUrl')"
        >
          <div class="link-form">
            <div class="link-field">
              <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
              <label
                class="link-label"
                for="link-url-input"
              >{{ t('editor.link.url') }}</label>
              <n-input
                v-model:value="linkForm.url"
                :placeholder="t('editor.link.urlPlaceholder')"
                :status="linkUrlStatus"
                :input-props="{ id: 'link-url-input' }"
                clearable
                @update:value="onLinkUrlChange"
              />
              <div
                v-if="linkUrlError"
                class="link-error"
              >
                {{ linkUrlError }}
              </div>
              <div
                v-else-if="linkForm.url && isInternalKbLink(linkForm.url)"
                class="link-hint"
              >
                {{ t('editor.link.kbInternalHint') }}
              </div>
            </div>

            <div
              v-if="linkShowTextField"
              class="link-field"
            >
              <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
              <label
                class="link-label"
                for="link-text-input"
              >{{ t('editor.link.text') }}</label>
              <n-input
                v-model:value="linkForm.text"
                :placeholder="t('editor.link.textPlaceholder')"
                :input-props="{ id: 'link-text-input' }"
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
        </n-tab-pane>
        <n-tab-pane
          name="kb"
          :tab="t('editor.link.tabKb')"
        >
          <div class="link-form">
            <div class="link-field">
              <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
              <label
                class="link-label"
                for="link-kb-search"
              >{{ t('editor.link.kbSearchLabel') }}</label>
              <n-input
                :value="kbSearchQuery"
                :placeholder="t('editor.link.kbSearchPlaceholder')"
                :input-props="{ id: 'link-kb-search', autocomplete: 'off' }"
                clearable
                autofocus
                @update:value="onKbSearchInput"
                @keydown="onKbKeydown"
              />
            </div>
            <div
              v-if="kbSearchLoading"
              class="kb-search-hint"
            >
              {{ t('common.loading') }}
            </div>
            <div
              v-else-if="kbSearchQuery.trim().length >= kbMinLength && !kbSearchResults.length"
              class="kb-search-hint"
            >
              {{ t('editor.link.kbNoResults') }}
            </div>
            <ul
              v-else-if="kbSearchResults.length"
              class="kb-search-results"
              role="listbox"
            >
              <li
                v-for="(item, idx) in kbSearchResults"
                :key="item.id"
                role="option"
                :aria-selected="idx === kbActiveIndex"
              >
                <button
                  type="button"
                  class="kb-search-item"
                  :class="{ 'is-active': idx === kbActiveIndex }"
                  @click="selectKbArticle(item)"
                  @mouseenter="kbActiveIndex = idx"
                >
                  <span class="kb-search-item-title">
                    <template
                      v-for="(chunk, ci) in highlightKbMatch(item.title)"
                      :key="ci"
                    >
                      <mark
                        v-if="chunk.match"
                        class="kb-search-item-hl"
                      >{{ chunk.text }}</mark>
                      <span v-else>{{ chunk.text }}</span>
                    </template>
                  </span>
                  <span
                    v-if="item.status && item.status !== 'published'"
                    class="kb-search-item-status"
                  >{{ item.status }}</span>
                </button>
              </li>
            </ul>
            <div
              v-else
              class="kb-search-hint"
            >
              {{ t('editor.link.kbHint', { n: kbMinLength }) }}
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>
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
        <n-button
          size="small"
          @click="showLinkDialog = false"
        >
          {{ t('common.cancel') }}
        </n-button>
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
        <n-button
          size="small"
          @click="showDetailsDialog = false"
        >
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          size="small"
          type="primary"
          @click="insertDetails"
        >
          {{ t('editor.insert') }}
        </n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEditor, EditorContent, BubbleMenu } from '@tiptap/vue-3'
import { NButton, NButtonGroup, NCheckbox, NModal, NInput, NTabs, NTabPane } from 'naive-ui'
import RichEditorToolbar from './editor/RichEditorToolbar.vue'
import { buildEditorExtensions } from './editor/useEditorExtensions'
import { useEditorLinkDialog } from './editor/useEditorLinkDialog'
import { useEditorImageUpload } from './editor/useEditorImageUpload'
import { useEditorVideoDialog } from './editor/useEditorVideoDialog'
import { useEditorDetailsDialog } from './editor/useEditorDetailsDialog'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  uploadEndpoint?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { t } = useI18n()

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

const isFullscreen = ref(false)
const isFocusMode = ref(false)

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

function toggleFocusMode() {
  isFocusMode.value = !isFocusMode.value
}

function handleEscape(e: KeyboardEvent) {
  if (e.key === 'Escape' && isFullscreen.value) {
    isFullscreen.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleEscape)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleEscape)
})

function handleEditorDblClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  if (!target) return
  const figure = target.closest('figure[data-type="figure-image"]')
  if (figure) {
    event.preventDefault()
    openImageDialogForEdit()
  }
}

function shouldShowBubbleMenu({ editor: ed, from, to }: { editor: import('@tiptap/core').Editor; from: number; to: number }) {
  if (!ed.isEditable) return false
  if (from === to) return false
  if (ed.isActive('image') || ed.isActive('table')) return false
  const text = ed.state.doc.textBetween(from, to, ' ').trim()
  return text.length > 0
}

onBeforeUnmount(() => editor.value?.destroy())

</script>

<style scoped>
.editor-wrap {
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 8px;
  overflow: hidden;
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
  min-height: 240px;
  padding: 16px;
}
.bubble-menu {
  display: flex;
  background: var(--n-color, #fff);
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  padding: 2px;
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
.link-hint {
  font-size: 12px;
  color: var(--n-text-color-3, #888);
}
.kb-search-hint {
  font-size: 13px;
  color: var(--n-text-color-3, #888);
  padding: 6px 2px;
}
.kb-search-results {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 4px;
}
.kb-search-results li {
  border-bottom: 1px solid var(--n-border-color, #f0f0f3);
}
.kb-search-results li:last-child {
  border-bottom: none;
}
.kb-search-item {
  width: 100%;
  text-align: left;
  background: transparent;
  border: none;
  padding: 8px 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font: inherit;
  color: inherit;
}
.kb-search-item:hover,
.kb-search-item:focus-visible,
.kb-search-item.is-active {
  background: var(--n-table-header-color, #f5f5f7);
  outline: none;
}
.kb-search-item-hl {
  background: #fff3a0;
  color: inherit;
  padding: 0 1px;
  border-radius: 2px;
}
.kb-search-item-title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-search-item-status {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--n-text-color-3, #999);
  text-transform: uppercase;
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
.image-preview {
  display: flex;
  justify-content: center;
  margin-bottom: 4px;
}
.image-preview img {
  max-width: 100%;
  max-height: 200px;
  border-radius: 4px;
  border: 1px solid var(--n-border-color, #e0e0e6);
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
