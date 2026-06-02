<template>
  <bubble-menu
    :editor="editor"
    :tippy-options="{ duration: 100, placement: 'top' }"
    :should-show="shouldShow"
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
        @click="$emit('open-link')"
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
</template>

<script setup lang="ts">
import { BubbleMenu } from '@tiptap/vue-3'
import { NButton, NButtonGroup } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import type { Editor } from '@tiptap/vue-3'

defineProps<{
  editor: Editor
  shouldShow: (props: { editor: import('@tiptap/core').Editor; from: number; to: number }) => boolean
}>()

defineEmits<{
  'open-link': []
}>()

const { t } = useI18n()
</script>

<style scoped>
.bubble-menu {
  display: flex;
  background: var(--n-color, #fff);
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  padding: 2px;
}
</style>
