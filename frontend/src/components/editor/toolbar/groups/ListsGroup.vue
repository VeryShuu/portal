<template>
  <n-button-group size="small">
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.bulletList')"
          :type="editor.isActive('bulletList') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleBulletList().run()"
        >
          ≡
        </n-button>
      </template>
      {{ t('editor.bulletList') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.orderedList')"
          :type="editor.isActive('orderedList') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleOrderedList().run()"
        >
          1.
        </n-button>
      </template>
      {{ t('editor.orderedList') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.taskList')"
          :type="editor.isActive('taskList') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleTaskList().run()"
        >
          ☑
        </n-button>
      </template>
      {{ t('editor.taskList') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.blockquote')"
          :type="editor.isActive('blockquote') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleBlockquote().run()"
        >
          "
        </n-button>
      </template>
      {{ t('editor.blockquote') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.codeBlock')"
          :type="editor.isActive('codeBlock') ? 'primary' : 'default'"
          @click="editor.chain().focus().toggleCodeBlock().run()"
        >
          &lt;/&gt;
        </n-button>
      </template>
      {{ t('editor.codeBlock') }}
    </n-tooltip>
  </n-button-group>

  <n-button-group size="small">
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.alignLeft')"
          :type="editor.isActive({ textAlign: 'left' }) ? 'primary' : 'default'"
          @click="editor.chain().focus().setTextAlign('left').run()"
        >
          ⯇
        </n-button>
      </template>
      {{ t('editor.alignLeft') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.alignCenter')"
          :type="editor.isActive({ textAlign: 'center' }) ? 'primary' : 'default'"
          @click="editor.chain().focus().setTextAlign('center').run()"
        >
          ☰
        </n-button>
      </template>
      {{ t('editor.alignCenter') }}
    </n-tooltip>
    <n-tooltip>
      <template #trigger>
        <n-button
          quaternary
          :aria-label="t('editor.alignRight')"
          :type="editor.isActive({ textAlign: 'right' }) ? 'primary' : 'default'"
          @click="editor.chain().focus().setTextAlign('right').run()"
        >
          ⯈
        </n-button>
      </template>
      {{ t('editor.alignRight') }}
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
