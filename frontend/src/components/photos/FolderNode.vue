<template>
  <li class="folder-node">
    <div class="folder-node__row" :class="{ selected: selectedId === node.id }">
      <button
        v-if="node.children.length"
        type="button"
        class="folder-node__toggle"
        @click="open = !open"
        :aria-label="open ? 'collapse' : 'expand'"
      >{{ open ? '▾' : '▸' }}</button>
      <span v-else class="folder-node__toggle folder-node__toggle--leaf">·</span>

      <img
        v-if="node.cover_photo_id"
        :src="thumbUrl(node.cover_photo_id, 200)"
        class="folder-node__cover"
        :alt="node.name"
      />
      <span v-else class="folder-node__icon">📁</span>

      <button
        type="button"
        class="folder-node__name"
        :title="node.path"
        @click="$emit('select', node)"
      >
        {{ node.name }}
      </button>

      <n-dropdown
        v-if="canManage"
        trigger="click"
        :options="menuOptions"
        @select="onMenu"
      >
        <button class="folder-node__menu" type="button" aria-label="menu">⋯</button>
      </n-dropdown>
    </div>

    <ul v-if="open && node.children.length" class="folder-node__children">
      <FolderNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :selected-id="selectedId"
        @select="(n: PhotoFolderTreeNode) => $emit('select', n)"
        @subfolder="(n: PhotoFolderTreeNode) => $emit('subfolder', n)"
        @permissions="(n: PhotoFolderTreeNode) => $emit('permissions', n)"
        @delete="(n: PhotoFolderTreeNode) => $emit('delete', n)"
      />
    </ul>
  </li>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NDropdown } from 'naive-ui'
import type { PhotoFolderTreeNode } from '@/api/photos'
import { thumbUrl } from '@/api/photos'

const props = defineProps<{
  node: PhotoFolderTreeNode
  selectedId: string | null
}>()

const emit = defineEmits<{
  (e: 'select', n: PhotoFolderTreeNode): void
  (e: 'subfolder', n: PhotoFolderTreeNode): void
  (e: 'permissions', n: PhotoFolderTreeNode): void
  (e: 'delete', n: PhotoFolderTreeNode): void
}>()

const { t } = useI18n()
const open = ref(true)

const canManage = computed(() => props.node.permission === 'manager')

const menuOptions = computed(() => {
  const out = [
    { label: t('photos.folders.newSub'), key: 'subfolder' },
    { label: t('photos.permissions.manage'), key: 'permissions' },
  ]
  if (canManage.value) {
    out.push({ label: t('common.delete'), key: 'delete' } as { label: string; key: string })
  }
  return out
})

function onMenu(key: string) {
  if (key === 'subfolder') emit('subfolder', props.node)
  else if (key === 'permissions') emit('permissions', props.node)
  else if (key === 'delete') emit('delete', props.node)
}
</script>

<style scoped>
.folder-node { list-style: none; }
.folder-node__row {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 6px; border-radius: var(--radius-sm);
}
.folder-node__row.selected { background: var(--color-bg-muted); }
.folder-node__row:hover { background: var(--color-bg-muted); }
.folder-node__toggle {
  background: transparent; border: 0; cursor: pointer;
  width: 18px; font-size: 11px; color: var(--color-text-muted);
}
.folder-node__toggle--leaf { cursor: default; }
.folder-node__name {
  flex: 1; text-align: left; background: transparent; border: 0;
  cursor: pointer; font-size: 13px; padding: 2px 0;
  color: var(--color-text); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.folder-node__menu {
  background: transparent; border: 0; cursor: pointer;
  font-size: 16px; color: var(--color-text-muted); padding: 0 4px;
  visibility: hidden;
}
.folder-node__row:hover .folder-node__menu { visibility: visible; }
.folder-node__children {
  list-style: none; padding-left: 16px; margin: 0;
}
.folder-node__cover {
  width: 24px; height: 24px; object-fit: cover; border-radius: 3px; flex-shrink: 0;
}
.folder-node__icon { font-size: 14px; flex-shrink: 0; }
</style>
