<template>
  <n-button-group size="small">
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.heading2')"
          :type="editor.isActive('heading', { level: 2 }) ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleHeading({ level: 2 }).run()"
        >
          H2
        </n-button>
      </template>
      {{ t('editor.heading2') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.heading3')"
          :type="editor.isActive('heading', { level: 3 }) ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleHeading({ level: 3 }).run()"
        >
          H3
        </n-button>
      </template>
      {{ t('editor.heading3') }}
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
