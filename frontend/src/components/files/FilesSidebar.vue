<template>
  <aside class="files-side">
    <div class="files-side__head">
      <h2 class="files-side__title">
        {{ t('files.folders.title') }}
      </h2>
      <n-dropdown
        v-if="isAdmin"
        trigger="click"
        :options="adminMenu"
        @select="onAdminSelect"
      >
        <n-button
          size="tiny"
          quaternary
          circle
          :title="t('common.more')"
        >
          <template #icon>
            <n-icon :component="SettingsOutline" />
          </template>
        </n-button>
      </n-dropdown>
    </div>

    <n-button
      v-if="isEditor"
      block
      size="small"
      type="primary"
      class="files-side__create"
      @click="$emit('create-root')"
    >
      <template #icon>
        <n-icon :component="AddOutline" />
      </template>
      {{ t('files.folders.newRoot') }}
    </n-button>

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
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDropdown, NIcon, type DropdownOption } from 'naive-ui'
import {
  AddOutline,
  SettingsOutline,
  SyncOutline,
  ImageOutline,
} from '@vicons/ionicons5'
import SkeletonCard from '../SkeletonCard.vue'
import FileFolderNode from '../FileFolderNode.vue'
import type { FileFolderTreeNode } from '../../api/files'

const props = defineProps<{
  tree: FileFolderTreeNode[]
  loading: boolean
  selectedId: string | null
  isAdmin: boolean
  isEditor: boolean
  syncing: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  'create-root': []
  'create-child': [folderId: string]
  manage: [folderId: string]
  delete: [folderId: string]
  sync: []
  'manage-icons': []
}>()

const { t } = useI18n()

const adminMenu = computed<DropdownOption[]>(() => [
  {
    key: 'sync',
    label: props.syncing ? t('files.sync.button') + '…' : t('files.sync.button'),
    disabled: props.syncing,
    icon: () => h(NIcon, null, { default: () => h(SyncOutline) }),
  },
  {
    key: 'manage-icons',
    label: t('admin.tabs.fileIcons'),
    icon: () => h(NIcon, null, { default: () => h(ImageOutline) }),
  },
])

function onAdminSelect(key: string) {
  if (key === 'sync') emit('sync')
  else if (key === 'manage-icons') emit('manage-icons')
}
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
  margin-bottom: 10px;
}

.files-side__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}

.files-side__create {
  margin-bottom: 12px;
}

.files-side__loading,
.files-side__empty {
  font-size: 13px;
  color: var(--n-text-color-3, #999);
  padding: 8px 0;
}

.folder-tree {
  list-style: none;
  margin: 0;
  padding: 0;
}
</style>
