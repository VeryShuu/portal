<template>
  <aside class="files-side">
    <div class="files-side__head">
      <h2 class="files-side__title">
        {{ t('files.folders.title') }}
      </h2>
      <n-button
        v-if="isEditor"
        size="tiny"
        type="primary"
        ghost
        @click="$emit('create-root')"
      >
        + {{ t('files.folders.newRoot') }}
      </n-button>
    </div>
    <div
      v-if="isAdmin"
      class="files-side__sync"
    >
      <n-button
        size="tiny"
        :loading="syncing"
        :disabled="syncing"
        @click="$emit('sync')"
      >
        {{ t('files.sync.button') }}
      </n-button>
    </div>
    <div
      v-if="loading"
      class="files-side__loading"
    >
      <SkeletonCard
        v-for="i in 6"
        :key="i"
        variant="folder-item"
      />
    </div>
    <ul
      v-else-if="tree.length"
      class="folder-tree"
    >
      <FileFolderNode
        v-for="node in tree"
        :key="node.id"
        :node="node"
        :selected-id="selectedId"
        @select="$emit('select', $event)"
        @create-child="$emit('create-child', $event)"
        @manage="$emit('manage', $event)"
        @delete="$emit('delete', $event)"
      />
    </ul>
    <p
      v-else
      class="files-side__empty"
    >
      {{ t('files.folders.empty') }}
    </p>
  </aside>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import SkeletonCard from '../SkeletonCard.vue'
import FileFolderNode from '../FileFolderNode.vue'
import type { FileFolderTreeNode } from '../../api/files'

defineProps<{
  tree: FileFolderTreeNode[]
  loading: boolean
  selectedId: string | null
  isAdmin: boolean
  isEditor: boolean
  syncing: boolean
}>()

defineEmits<{
  select: [id: string]
  'create-root': []
  'create-child': [folderId: string]
  manage: [folderId: string]
  delete: [folderId: string]
  sync: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.files-side {
  width: 260px;
  min-width: 200px;
  border-right: 1px solid var(--n-border-color, #e0e0e0);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  overflow-y: auto;
  flex-shrink: 0;
}

.files-side__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.files-side__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}

.files-side__loading,
.files-side__empty {
  font-size: 13px;
  color: var(--n-text-color-3, #999);
  padding: 8px 0;
}

.files-side__sync {
  margin-bottom: 10px;
}

.folder-tree {
  list-style: none;
  margin: 0;
  padding: 0;
}
</style>
