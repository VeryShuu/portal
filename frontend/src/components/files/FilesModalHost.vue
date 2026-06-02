<template>
  <div class="files-modal-host">
    <FilesCreateFolderModal
      v-model:show="showCreate"
      :loading="creating"
      @submit="(payload) => $emit('submit-create', payload)"
    />
    <FilesMoveModal
      v-model:show="showMove"
      :tree-data="moveTreeData"
      :target-key="moveTargetKey"
      :loading="moveLoading"
      @update:target-key="(key) => (moveTargetKey = key)"
      @confirm="$emit('confirm-move')"
    />
    <FilesPermissionsModal
      v-model:show="showPerms"
      :folder-id="permsFolderId"
      :parent-id="permsParentId"
      :inherit-permissions="permsInherit"
      @tree-refresh="$emit('tree-refresh')"
    />
    <FilesShareModal
      v-model:show="showShare"
      :folder-id="shareFolderId"
      :filename="shareFilename"
    />
    <FilesImagePreview
      v-if="showImagePreview && previewFolderId"
      :images="previewImages"
      :initial-index="previewInitialIndex"
      :folder-id="previewFolderId"
      @close="showImagePreview = false"
    />
    <n-drawer
      :show="iconsDrawerOpen"
      :width="720"
      placement="right"
      :on-update:show="(v: boolean) => { if (!v) $emit('close-icons-drawer') }"
    >
      <n-drawer-content
        :title="t('admin.tabs.fileIcons')"
        closable
      >
        <Suspense>
          <FileIconsTab />
        </Suspense>
      </n-drawer-content>
    </n-drawer>
    <n-drawer
      :show="sharesDrawerOpen"
      :width="900"
      placement="right"
      :on-update:show="(v: boolean) => { if (!v) $emit('close-shares-drawer') }"
    >
      <n-drawer-content
        :title="t('files.share.admin.title')"
        closable
      >
        <Suspense>
          <FileSharesTab />
        </Suspense>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { NDrawer, NDrawerContent, type TreeOption } from 'naive-ui'
import FilesCreateFolderModal from './FilesCreateFolderModal.vue'
import FilesMoveModal from './FilesMoveModal.vue'
import FilesPermissionsModal from './FilesPermissionsModal.vue'
import FilesShareModal from './FilesShareModal.vue'
import FilesImagePreview from './FilesImagePreview.vue'
import type { NCItem } from '../../api/files'

defineProps<{
  creating: boolean
  moveTreeData: TreeOption[]
  moveLoading: boolean
  permsFolderId: string | null
  permsParentId: string | null
  permsInherit: boolean
  shareFolderId: string | null
  shareFilename: string | null
  previewImages: NCItem[]
  previewInitialIndex: number
  previewFolderId: string | null
  iconsDrawerOpen: boolean
  sharesDrawerOpen: boolean
}>()

defineEmits<{
  (e: 'submit-create', payload: { name: string; description: string | null }): void
  (e: 'confirm-move'): void
  (e: 'tree-refresh'): void
  (e: 'close-icons-drawer'): void
  (e: 'close-shares-drawer'): void
}>()

const showCreate = defineModel<boolean>('showCreate', { required: true })
const showMove = defineModel<boolean>('showMove', { required: true })
const moveTargetKey = defineModel<string | null>('moveTargetKey', { required: true })
const showPerms = defineModel<boolean>('showPerms', { required: true })
const showShare = defineModel<boolean>('showShare', { required: true })
const showImagePreview = defineModel<boolean>('showImagePreview', { required: true })

const { t } = useI18n()

const FileIconsTab = defineAsyncComponent(() => import('../../pages/admin/tabs/FileIconsTab.vue'))
const FileSharesTab = defineAsyncComponent(() => import('../../pages/admin/tabs/FileSharesTab.vue'))
</script>
