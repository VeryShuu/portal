<template>
  <aside class="photos-side">
    <div class="photos-side__head">
      <h2 class="photos-side__title">
        {{ t('photos.folders.title') }}
      </h2>
      <div class="photos-side__head-actions">
        <n-button
          v-if="auth.isAdmin"
          size="tiny"
          quaternary
          circle
          :title="t('admin.modules.openPhotosSettings')"
          @click="$emit('open-module-settings')"
        >
          <template #icon>
            <n-icon :component="SettingsOutline" />
          </template>
        </n-button>
        <n-button
          v-if="auth.isEditor"
          size="tiny"
          @click="$emit('create-root')"
        >
          + {{ t('photos.folders.newRoot') }}
        </n-button>
      </div>
    </div>

    <div
      v-if="loadingTree"
      class="photos-side__loading"
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
      <FolderNode
        v-for="n in tree"
        :key="n.id"
        :node="n"
        :selected-id="selectedFolderId"
        @select="(node) => $emit('select', node)"
        @subfolder="(node) => $emit('create-child', node)"
        @permissions="(node) => $emit('permissions', node)"
        @delete="(node) => $emit('delete', node)"
        @drag-start="(node) => $emit('drag-start', node)"
        @drop="(payload) => $emit('drop', payload)"
        @move-to-root="(node) => $emit('move-to-root', node)"
      />
    </ul>
    <p
      v-else
      class="photos-side__empty"
    >
      {{ t('photos.folders.empty') }}
    </p>

    <div
      v-if="tags.length"
      class="photos-side__tags"
    >
      <div class="photos-side__tags-head">
        <span class="photos-side__tags-title">{{ t('photos.tags.title') }}</span>
        <button
          v-if="activeTagFilter"
          class="photos-side__tags-clear"
          @click="$emit('clear-tag-filter')"
        >
          × {{ t('photos.tags.clearFilter') }}
        </button>
      </div>
      <div class="tag-cloud">
        <button
          v-for="tag in tags"
          :key="tag.id"
          class="tag-chip"
          :class="{ 'tag-chip--active': activeTagFilter === tag.id }"
          @click="$emit('set-tag-filter', tag)"
        >
          {{ tag.name }}
        </button>
      </div>
    </div>

    <div
      v-if="auth.isAdmin"
      class="photos-side__import"
    >
      <n-button
        size="small"
        block
        @click="$emit('import-scan')"
      >
        {{ t('photos.import.button') }}
      </n-button>
    </div>

    <div class="photos-side__myshares">
      <button
        class="photos-side__myshares-btn"
        @click="router.push('/photos/my-shares')"
      >
        {{ t('photos.myShares.title') }}
      </button>
      <button
        v-if="auth.isEditor"
        class="photos-side__myshares-btn"
        @click="$emit('open-trash')"
      >
        {{ t('photos.trash.button') }}
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon } from 'naive-ui'
import { SettingsOutline } from '@vicons/ionicons5'
import SkeletonCard from '../SkeletonCard.vue'
import FolderNode from './FolderNode.vue'
import { useAuthStore } from '@/stores/auth'
import type { PhotoFolderTreeNode, PhotoTag } from '@/api/photos'

defineProps<{
  tree: PhotoFolderTreeNode[]
  loadingTree: boolean
  selectedFolderId: string | null
  tags: PhotoTag[]
  activeTagFilter: string | null
}>()

defineEmits<{
  'create-root': []
  'select': [node: PhotoFolderTreeNode]
  'create-child': [node: PhotoFolderTreeNode]
  'permissions': [node: PhotoFolderTreeNode]
  'delete': [node: PhotoFolderTreeNode]
  'drag-start': [node: PhotoFolderTreeNode]
  'drop': [target: PhotoFolderTreeNode]
  'move-to-root': [node: PhotoFolderTreeNode]
  'set-tag-filter': [tag: PhotoTag]
  'clear-tag-filter': []
  'import-scan': []
  'open-trash': []
  'open-module-settings': []
}>()

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
</script>

<style scoped>
.photos-side {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px;
  height: fit-content;
  position: sticky;
  top: 16px;
}
.photos-side__head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px;
}
.photos-side__head-actions { display: flex; align-items: center; gap: 4px; }
.photos-side__title { margin: 0; font-size: 14px; font-weight: 700; }
.photos-side__loading, .photos-side__empty {
  font-size: 13px; color: var(--color-text-muted); margin: 12px 0;
}
.folder-tree { list-style: none; margin: 0; padding: 0; }

.photos-side__import {
  margin-top: 12px;
  border-top: 1px solid var(--color-border);
  padding-top: 10px;
}

.photos-side__tags {
  margin-top: 12px;
  border-top: 1px solid var(--color-border);
  padding-top: 10px;
}
.photos-side__tags-head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;
}
.photos-side__tags-title {
  font-size: 12px; font-weight: 600; color: var(--color-text-muted); text-transform: uppercase;
}
.photos-side__tags-clear {
  background: transparent; border: 0; cursor: pointer; font-size: 11px; color: var(--color-text-muted);
}
.photos-side__tags-clear:hover { color: var(--color-text); }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 4px; }
.tag-chip {
  background: var(--color-bg-muted); border: 1px solid var(--color-border);
  border-radius: 999px; padding: 2px 8px; font-size: 11px; cursor: pointer;
  color: var(--color-text); white-space: nowrap;
}
.tag-chip:hover { background: var(--color-border); }
.tag-chip--active { background: var(--color-primary, #3b82f6); color: #fff; border-color: var(--color-primary, #3b82f6); }

.photos-side__myshares {
  margin-top: 8px;
  border-top: 1px solid var(--color-border);
  padding-top: 10px;
}
.photos-side__myshares-btn {
  background: transparent; border: 0; cursor: pointer; padding: 0;
  font-size: 13px; color: var(--color-text-muted); text-align: left; width: 100%;
}
.photos-side__myshares-btn:hover { color: var(--color-text); text-decoration: underline; }

@media (max-width: 900px) {
  .photos-side { position: static; }
}
</style>
