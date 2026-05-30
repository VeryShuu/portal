<template>
  <n-tooltip>
    <template #trigger>
      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.insert_link')"
        :type="editor.isActive('link') ? 'primary' : 'default'"
        @click="emit('open-link')"
      >
        🔗
      </n-button>
    </template>
    {{ t('editor.insert_link') }}
  </n-tooltip>

  <n-tooltip>
    <template #trigger>
      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.insert_image')"
        @click="emit('insert-image')"
      >
        🖼
      </n-button>
    </template>
    {{ t('editor.insert_image') }}
  </n-tooltip>

  <n-tooltip>
    <template #trigger>
      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.insert_video')"
        @click="emit('open-video')"
      >
        ▶
      </n-button>
    </template>
    {{ t('editor.insert_video') }}
  </n-tooltip>

  <n-tooltip>
    <template #trigger>
      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.horizontal_rule')"
        @click="editor.chain().focus().setHorizontalRule().run()"
      >
        —
      </n-button>
    </template>
    {{ t('editor.horizontal_rule') }}
  </n-tooltip>

  <n-dropdown
    trigger="click"
    :options="tableMenuOptions"
    @select="handleTableMenuSelect"
  >
    <n-tooltip>
      <template #trigger>
        <n-button
          size="small"
          quaternary
          :aria-label="t('editor.table.label')"
        >
          ⊞
        </n-button>
      </template>
      {{ t('editor.table.label') }}
    </n-tooltip>
  </n-dropdown>

  <n-dropdown
    trigger="click"
    :options="calloutMenuOptions"
    @select="handleCalloutMenuSelect"
  >
    <n-tooltip>
      <template #trigger>
        <n-button
          size="small"
          quaternary
          :aria-label="t('editor.callout.label')"
          :type="editor.isActive('callout') ? 'primary' : 'default'"
        >
          ℹ
        </n-button>
      </template>
      {{ t('editor.callout.label') }}
    </n-tooltip>
  </n-dropdown>

  <n-tooltip>
    <template #trigger>
      <n-button
        size="small"
        quaternary
        :aria-label="t('editor.details.label')"
        :type="editor.isActive('details') ? 'primary' : 'default'"
        @click="emit('open-details')"
      >
        ▸
      </n-button>
    </template>
    {{ t('editor.details.label') }}
  </n-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDropdown, NTooltip } from 'naive-ui'
import type { DropdownOption } from 'naive-ui'
import type { Editor } from '@tiptap/vue-3'
import type { CalloutType } from '../../extensions/Callout'

const props = defineProps<{
  editor: Editor
}>()

const emit = defineEmits<{
  'open-link': []
  'insert-image': []
  'open-video': []
  'open-details': []
}>()

const { t } = useI18n()

const tableMenuOptions = computed<DropdownOption[]>(() => [
  { label: t('editor.table.insert'), key: 'insert' },
  { type: 'divider', key: 'd1' },
  { label: t('editor.table.addColBefore'), key: 'addColBefore' },
  { label: t('editor.table.addColAfter'), key: 'addColAfter' },
  { label: t('editor.table.deleteCol'), key: 'deleteCol' },
  { type: 'divider', key: 'd2' },
  { label: t('editor.table.addRowBefore'), key: 'addRowBefore' },
  { label: t('editor.table.addRowAfter'), key: 'addRowAfter' },
  { label: t('editor.table.deleteRow'), key: 'deleteRow' },
  { type: 'divider', key: 'd3' },
  { label: t('editor.table.delete'), key: 'deleteTable' },
])

const calloutMenuOptions = computed<DropdownOption[]>(() => [
  { label: `ℹ ${t('editor.callout.info')}`, key: 'info' },
  { label: `⚠ ${t('editor.callout.warning')}`, key: 'warning' },
  { label: `💡 ${t('editor.callout.tip')}`, key: 'tip' },
  { label: `🚨 ${t('editor.callout.danger')}`, key: 'danger' },
])

function handleTableMenuSelect(key: string) {
  const ed = props.editor
  const chain = ed.chain().focus()
  switch (key) {
    case 'insert':
      chain.insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
      break
    case 'addColBefore':
      chain.addColumnBefore().run()
      break
    case 'addColAfter':
      chain.addColumnAfter().run()
      break
    case 'deleteCol':
      chain.deleteColumn().run()
      break
    case 'addRowBefore':
      chain.addRowBefore().run()
      break
    case 'addRowAfter':
      chain.addRowAfter().run()
      break
    case 'deleteRow':
      chain.deleteRow().run()
      break
    case 'deleteTable':
      chain.deleteTable().run()
      break
  }
}

function handleCalloutMenuSelect(key: string) {
  props.editor.chain().focus().toggleCallout(key as CalloutType).run()
}
</script>
