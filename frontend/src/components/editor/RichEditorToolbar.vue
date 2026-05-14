<template>
  <div class="toolbar">
    <n-button-group size="small">
      <n-button quaternary :aria-label="t('editor.bold')" :type="editor.isActive('bold') ? 'primary' : 'default'" @click="editor.chain().focus().toggleBold().run()">
        <b>B</b>
      </n-button>
      <n-button quaternary :aria-label="t('editor.italic')" :type="editor.isActive('italic') ? 'primary' : 'default'" @click="editor.chain().focus().toggleItalic().run()">
        <i>I</i>
      </n-button>
      <n-button quaternary :aria-label="t('editor.strike')" :type="editor.isActive('strike') ? 'primary' : 'default'" @click="editor.chain().focus().toggleStrike().run()">
        <s>S</s>
      </n-button>
    </n-button-group>

    <n-button-group size="small">
      <n-button quaternary :aria-label="t('editor.heading2')" :type="editor.isActive('heading', { level: 2 }) ? 'primary' : 'default'" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">
        H2
      </n-button>
      <n-button quaternary :aria-label="t('editor.heading3')" :type="editor.isActive('heading', { level: 3 }) ? 'primary' : 'default'" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">
        H3
      </n-button>
    </n-button-group>

    <n-button-group size="small">
      <n-button quaternary :aria-label="t('editor.bulletList')" :type="editor.isActive('bulletList') ? 'primary' : 'default'" @click="editor.chain().focus().toggleBulletList().run()">
        ≡
      </n-button>
      <n-button quaternary :aria-label="t('editor.orderedList')" :type="editor.isActive('orderedList') ? 'primary' : 'default'" @click="editor.chain().focus().toggleOrderedList().run()">
        1.
      </n-button>
      <n-button quaternary :aria-label="t('editor.blockquote')" :type="editor.isActive('blockquote') ? 'primary' : 'default'" @click="editor.chain().focus().toggleBlockquote().run()">
        "
      </n-button>
      <n-button quaternary :aria-label="t('editor.codeBlock')" :type="editor.isActive('codeBlock') ? 'primary' : 'default'" @click="editor.chain().focus().toggleCodeBlock().run()">
        &lt;/&gt;
      </n-button>
    </n-button-group>

    <n-button-group size="small">
      <n-button quaternary :aria-label="t('editor.alignLeft')" :type="editor.isActive({ textAlign: 'left' }) ? 'primary' : 'default'" @click="editor.chain().focus().setTextAlign('left').run()">
        ⯇
      </n-button>
      <n-button quaternary :aria-label="t('editor.alignCenter')" :type="editor.isActive({ textAlign: 'center' }) ? 'primary' : 'default'" @click="editor.chain().focus().setTextAlign('center').run()">
        ☰
      </n-button>
      <n-button quaternary :aria-label="t('editor.alignRight')" :type="editor.isActive({ textAlign: 'right' }) ? 'primary' : 'default'" @click="editor.chain().focus().setTextAlign('right').run()">
        ⯈
      </n-button>
    </n-button-group>

    <n-button
      size="small"
      quaternary
      :aria-label="t('editor.insert_link')"
      :type="editor.isActive('link') ? 'primary' : 'default'"
      @click="$emit('open-link')"
    >
      🔗
    </n-button>

    <n-button size="small" quaternary :aria-label="t('editor.insert_image')" @click="$emit('insert-image')">
      🖼
    </n-button>

    <n-button
      size="small"
      quaternary
      :aria-label="t('editor.insert_video')"
      @click="$emit('open-video')"
    >
      ▶
    </n-button>

    <n-button
      size="small"
      quaternary
      :aria-label="t('editor.horizontal_rule')"
      @click="editor.chain().focus().setHorizontalRule().run()"
    >
      —
    </n-button>

    <n-dropdown
      trigger="click"
      :options="tableMenuOptions"
      @select="handleTableMenuSelect"
    >
      <n-button size="small" quaternary :aria-label="t('editor.table.label')">
        ⊞
      </n-button>
    </n-dropdown>

    <n-dropdown
      trigger="click"
      :options="calloutMenuOptions"
      @select="handleCalloutMenuSelect"
    >
      <n-button size="small" quaternary :aria-label="t('editor.callout.label')" :type="editor.isActive('callout') ? 'primary' : 'default'">
        ℹ
      </n-button>
    </n-dropdown>

    <n-button
      size="small"
      quaternary
      :aria-label="t('editor.details.label')"
      :type="editor.isActive('details') ? 'primary' : 'default'"
      @click="$emit('open-details')"
    >
      ▸
    </n-button>

    <n-button size="small" quaternary :aria-label="t('editor.undo')" @click="editor.chain().focus().undo().run()">↩</n-button>
    <n-button size="small" quaternary :aria-label="t('editor.redo')" @click="editor.chain().focus().redo().run()">↪</n-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NButtonGroup, NDropdown } from 'naive-ui'
import type { DropdownOption } from 'naive-ui'
import type { Editor } from '@tiptap/vue-3'
import type { CalloutType } from './extensions/Callout'

const props = defineProps<{
  editor: Editor
}>()

defineEmits<{
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

<style scoped>
.toolbar {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border-bottom: 1px solid var(--n-border-color, #e0e0e6);
  background: var(--n-color, #fff);
}
</style>
