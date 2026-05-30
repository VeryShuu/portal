<template>
  <n-tooltip>
    <template #trigger>
      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.undo')"
        @click="editor.chain().focus().undo().run()"
      >
        ↩
      </n-button>
    </template>
    {{ t('editor.undo') }}
  </n-tooltip>
  <n-tooltip>
    <template #trigger>
      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.redo')"
        @click="editor.chain().focus().redo().run()"
      >
        ↪
      </n-button>
    </template>
    {{ t('editor.redo') }}
  </n-tooltip>

  <n-tooltip>
    <template #trigger>
      <n-button
        size="small"
        quaternary
        :aria-label="focusMode ? t('editor.focusModeExit') : t('editor.focusMode')"
        :type="focusMode ? 'primary' : 'default'"
        @click="emit('toggle-focus')"
      >
        ◎
      </n-button>
    </template>
    {{ focusMode ? t('editor.focusModeExit') : t('editor.focusMode') }}
  </n-tooltip>

  <n-tooltip>
    <template #trigger>
      <n-button
        size="small"
        quaternary
        :aria-label="fullscreen ? t('editor.fullscreenExit') : t('editor.fullscreen')"
        :type="fullscreen ? 'primary' : 'default'"
        @click="emit('toggle-fullscreen')"
      >
        {{ fullscreen ? '▭' : '⛶' }}
      </n-button>
    </template>
    {{ fullscreen ? t('editor.fullscreenExit') : t('editor.fullscreen') }}
  </n-tooltip>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NTooltip } from 'naive-ui'
import type { Editor } from '@tiptap/vue-3'

defineProps<{
  editor: Editor
  fullscreen?: boolean
  focusMode?: boolean
}>()

const emit = defineEmits<{
  'toggle-fullscreen': []
  'toggle-focus': []
}>()

const { t } = useI18n()
</script>
