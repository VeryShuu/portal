<template>
  <li
    class="ff-node"
    :class="{ 'ff-node--selected': node.id === selectedId }"
  >
    <div
      class="ff-node__row"
      role="button"
      tabindex="0"
      @click="$emit('select', node.id)"
      @keydown.enter="$emit('select', node.id)"
    >
      <span
        class="ff-node__toggle"
        role="button"
        tabindex="0"
        @click.stop="expanded = !expanded"
        @keydown.enter.stop="expanded = !expanded"
      >
        <span v-if="node.children.length">{{ expanded ? '▾' : '▸' }}</span>
        <span
          v-else
          class="ff-node__toggle--leaf"
        />
      </span>
      <span class="ff-node__icon">📁</span>
      <span
        class="ff-node__name"
        :title="node.name"
      >{{ node.name }}</span>
      <span
        class="ff-node__actions"
        @click.stop
      >
        <n-dropdown
          trigger="click"
          :options="menuOptions"
          @select="onMenuSelect"
        >
          <n-button
            size="tiny"
            text
          >⋮</n-button>
        </n-dropdown>
      </span>
    </div>
    <ul
      v-if="expanded && node.children.length"
      class="ff-node__children"
    >
      <FileFolderNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :selected-id="selectedId"
        @select="$emit('select', $event)"
        @create-child="$emit('create-child', $event)"
        @manage="$emit('manage', $event)"
        @delete="$emit('delete', $event)"
      />
    </ul>
  </li>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDropdown } from 'naive-ui'
import type { FileFolderTreeNode } from '../api/files'

const props = defineProps<{
  node: FileFolderTreeNode
  selectedId: string | null
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'create-child', id: string): void
  (e: 'manage', id: string): void
  (e: 'delete', id: string): void
}>()

const { t } = useI18n()
const expanded = ref(true)

const menuOptions = computed(() => {
  const opts = []
  if (props.node.permission === 'editor' || props.node.permission === 'manager') {
    opts.push({ label: t('files.folders.addSubfolder'), key: 'create-child' })
  }
  if (props.node.permission === 'manager') {
    opts.push({ label: t('files.manage'), key: 'manage' })
    opts.push({ label: t('common.delete'), key: 'delete' })
  }
  return opts
})

function onMenuSelect(key: string) {
  if (key === 'create-child') emit('create-child', props.node.id)
  else if (key === 'manage') emit('manage', props.node.id)
  else if (key === 'delete') emit('delete', props.node.id)
}
</script>

<style scoped>
.ff-node {
  list-style: none;
}

.ff-node__row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.12s;
}

.ff-node__row:hover {
  background: var(--n-hover-color, #f0f0f0);
}

.ff-node--selected > .ff-node__row {
  background: var(--n-primary-color-hover, #edfff6);
  font-weight: 600;
}

.ff-node__toggle {
  width: 14px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--n-text-color-3, #999);
  cursor: pointer;
}

.ff-node__toggle--leaf {
  display: inline-block;
  width: 14px;
}

.ff-node__icon {
  font-size: 14px;
  flex-shrink: 0;
}

.ff-node__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ff-node__actions {
  opacity: 0;
  transition: opacity 0.1s;
}

.ff-node__row:hover .ff-node__actions {
  opacity: 1;
}

.ff-node__children {
  padding-left: 18px;
  margin: 0;
  list-style: none;
}
</style>
