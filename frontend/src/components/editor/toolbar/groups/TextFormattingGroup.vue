<template>
  <n-button-group size="small">
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.bold')"
          :type="editor.isActive('bold') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleBold().run()"
        >
          <b>B</b>
        </n-button>
      </template>
      {{ t('editor.bold') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.italic')"
          :type="editor.isActive('italic') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleItalic().run()"
        >
          <i>I</i>
        </n-button>
      </template>
      {{ t('editor.italic') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.strike')"
          :type="editor.isActive('strike') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleStrike().run()"
        >
          <s>S</s>
        </n-button>
      </template>
      {{ t('editor.strike') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.underline')"
          :type="editor.isActive('underline') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleUnderline().run()"
        >
          <u>U</u>
        </n-button>
      </template>
      {{ t('editor.underline') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.code')"
          :type="editor.isActive('code') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleCode().run()"
        >
          <span style="font-family: monospace;">&lt;&gt;</span>
        </n-button>
      </template>
      {{ t('editor.code') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.highlight')"
          :type="editor.isActive('highlight') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleHighlight().run()"
        >
          <mark style="background: #ffe066; padding: 0 2px;">H</mark>
        </n-button>
      </template>
      {{ t('editor.highlight') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.subscript')"
          :type="editor.isActive('subscript') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleSubscript().run()"
        >
          X<sub>2</sub>
        </n-button>
      </template>
      {{ t('editor.subscript') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.superscript')"
          :type="editor.isActive('superscript') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleSuperscript().run()"
        >
          X<sup>2</sup>
        </n-button>
      </template>
      {{ t('editor.superscript') }}
    </n-tooltip>
  </n-button-group>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NButtonGroup, NTooltip } from 'naive-ui'
import type { Editor } from '@tiptap/vue-3'

defineProps<{
  editor: Editor
}>()

const { t } = useI18n()
</script>
