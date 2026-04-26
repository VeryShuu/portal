<template>
  <div class="files-page">
    <!-- Sidebar: folder tree -->
    <aside class="files-side">
      <div class="files-side__head">
        <h2 class="files-side__title">{{ t('files.folders.title') }}</h2>
        <n-button
          v-if="auth.isEditor"
          size="tiny"
          type="primary"
          ghost
          @click="openCreateRoot"
        >+ {{ t('files.folders.newRoot') }}</n-button>
      </div>

      <div v-if="loadingTree" class="files-side__loading">{{ t('common.loading') }}</div>
      <ul v-else-if="tree.length" class="folder-tree">
        <FileFolderNode
          v-for="node in tree"
          :key="node.id"
          :node="node"
          :selected-id="selectedFolderId"
          @select="selectFolder"
          @create-child="openCreateChild"
          @manage="openManage"
          @delete="confirmDeleteFolder"
        />
      </ul>
      <p v-else class="files-side__empty">{{ t('files.folders.empty') }}</p>
    </aside>

    <!-- Main: folder content -->
    <main class="files-main">
      <div v-if="!selectedFolderId" class="files-empty-state">
        <n-empty :description="t('files.selectFolder')" />
      </div>

      <template v-else>
        <!-- Breadcrumbs -->
        <nav v-if="breadcrumbs.length" class="files-breadcrumbs">
          <span
            v-for="(crumb, i) in breadcrumbs"
            :key="crumb.id"
            class="files-breadcrumb"
          >
            <span
              class="files-breadcrumb__link"
              @click="selectFolder(crumb.id)"
            >{{ crumb.name }}</span>
            <span v-if="i < breadcrumbs.length - 1" class="files-breadcrumb__sep">/</span>
          </span>
          <span class="files-breadcrumb files-breadcrumb--current">{{ currentFolder?.name }}</span>
        </nav>

        <!-- Toolbar -->
        <div class="files-toolbar">
          <div class="files-toolbar__left">
            <h1 class="files-title">{{ currentFolder?.name }}</h1>
            <n-tag v-if="currentFolder?.permission" size="small" :type="permTagType(currentFolder.permission)">
              {{ t(`files.permission.${currentFolder.permission}`) }}
            </n-tag>
          </div>
          <div class="files-toolbar__right">
            <n-button
              v-if="canUpload"
              size="small"
              type="primary"
              @click="triggerUpload"
            >{{ t('files.upload') }}</n-button>
            <n-button
              v-if="canManage"
              size="small"
              @click="openManage(selectedFolderId!)"
            >{{ t('files.manage') }}</n-button>
            <input
              ref="fileInputRef"
              type="file"
              multiple
              style="display: none"
              @change="handleFileInput"
            />
          </div>
        </div>

        <!-- Upload progress -->
        <n-alert v-if="uploading" type="info" :title="t('files.uploading')" style="margin-bottom: 12px" />

        <!-- File list -->
        <div v-if="loadingDetail" class="files-loading">{{ t('common.loading') }}</div>
        <div v-else-if="!ncItems.length" class="files-empty">
          <n-empty :description="t('files.emptyFolder')" />
        </div>
        <div v-else class="files-list">
          <div
            v-for="item in ncItems"
            :key="item.nc_path"
            class="files-item"
            :class="{ 'files-item--dir': item.is_dir }"
            @click="item.is_dir ? openSubFolder(item) : null"
          >
            <div class="files-item__icon">
              <span class="file-type-icon">{{ getFileIcon(item) }}</span>
            </div>
            <div class="files-item__info">
              <span class="files-item__name">{{ item.name }}</span>
              <span class="files-item__meta">
                <template v-if="!item.is_dir">{{ formatFileSize(item.size_bytes) }}</template>
                <template v-if="item.last_modified"> · {{ formatDate(item.last_modified) }}</template>
              </span>
            </div>
            <div class="files-item__actions" @click.stop>
              <n-button
                v-if="!item.is_dir"
                size="tiny"
                tag="a"
                :href="getDownloadUrl(item)"
                download
              >{{ t('files.download') }}</n-button>
              <n-button
                v-if="!item.is_dir && isCollaboraFile(item)"
                size="tiny"
                type="primary"
                ghost
                @click="openCollabora(item)"
              >{{ t('files.edit') }}</n-button>
              <n-button
                v-if="canUpload && !item.is_dir"
                size="tiny"
                type="error"
                ghost
                @click="confirmDeleteFile(item)"
              >{{ t('common.delete') }}</n-button>
            </div>
          </div>
        </div>
      </template>
    </main>

    <!-- Create folder modal -->
    <n-modal v-model:show="showCreateModal" :title="t('files.folders.create')" preset="card" style="width: 480px">
      <n-form>
        <n-form-item :label="t('files.folders.name')">
          <n-input v-model:value="createForm.name" :placeholder="t('files.folders.namePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('files.folders.description')">
          <n-input v-model:value="createForm.description" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <n-button @click="showCreateModal = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="creating" @click="submitCreate">{{ t('common.create') }}</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Permissions modal -->
    <n-modal v-model:show="showPermsModal" :title="t('files.permissions.title')" preset="card" style="width: 560px">
      <div v-if="loadingPerms" class="files-loading">{{ t('common.loading') }}</div>
      <template v-else>
        <n-data-table
          :columns="permColumns"
          :data="permissions"
          size="small"
          style="margin-bottom: 16px"
        />
        <n-divider />
        <h4 style="margin: 8px 0">{{ t('files.permissions.grant') }}</h4>
        <div class="perm-grant-form">
          <n-select
            v-model:value="grantForm.subject_type"
            :options="[{ label: t('files.permissions.user'), value: 'user' }, { label: t('files.permissions.group'), value: 'group' }]"
            style="width: 120px"
          />
          <n-input v-model:value="grantForm.subject_id" :placeholder="t('files.permissions.subjectId')" style="flex: 1" />
          <n-input v-model:value="grantForm.subject_name" :placeholder="t('files.permissions.subjectName')" style="flex: 1" />
          <n-select
            v-model:value="grantForm.permission"
            :options="[
              { label: t('files.permission.viewer'), value: 'viewer' },
              { label: t('files.permission.editor'), value: 'editor' },
              { label: t('files.permission.manager'), value: 'manager' },
            ]"
            style="width: 130px"
          />
          <n-button type="primary" :loading="granting" @click="submitGrant">{{ t('files.permissions.add') }}</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Collabora iframe modal -->
    <n-modal v-model:show="showCollaboraModal" style="width: 95vw; height: 90vh" :title="collaboraFile?.name">
      <iframe
        v-if="collaboraUrl"
        :src="collaboraUrl"
        style="width: 100%; height: calc(90vh - 80px); border: none"
        allow="fullscreen"
      />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NDataTable,
  NDivider,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import FileFolderNode from '../components/FileFolderNode.vue'
import { useAuthStore } from '../stores/auth'
import {
  type FileFolderPublic,
  type FileFolderTreeNode,
  type FilePermission,
  type NCItem,
  createFolder,
  deleteFile,
  deleteFolder,
  fetchFolderDetail,
  fetchFolderTree,
  fetchPermissions,
  fileIcon,
  formatFileSize,
  grantPermission,
  isCollaboraFile,
  openInCollabora,
  revokePermission,
  uploadFiles,
  downloadFile,
} from '../api/files'

const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()
const dialog = useDialog()

const tree = ref<FileFolderTreeNode[]>([])
const loadingTree = ref(false)
const selectedFolderId = ref<string | null>(null)
const currentFolder = ref<FileFolderPublic | null>(null)
const ncItems = ref<NCItem[]>([])
const breadcrumbs = ref<FileFolderPublic[]>([])
const loadingDetail = ref(false)

const showCreateModal = ref(false)
const createParentId = ref<string | null>(null)
const creating = ref(false)
const createForm = ref({ name: '', description: '' })

const showPermsModal = ref(false)
const permsForFolderId = ref<string | null>(null)
const permissions = ref<FilePermission[]>([])
const loadingPerms = ref(false)
const granting = ref(false)
const grantForm = ref({ subject_type: 'user' as 'user' | 'group', subject_id: '', subject_name: '', permission: 'viewer' as 'viewer' | 'editor' | 'manager' })

const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const showCollaboraModal = ref(false)
const collaboraUrl = ref<string | null>(null)
const collaboraFile = ref<NCItem | null>(null)

const canUpload = computed(() => {
  const p = currentFolder.value?.permission
  return p === 'editor' || p === 'manager' || auth.isAdmin
})

const canManage = computed(() => {
  const p = currentFolder.value?.permission
  return p === 'manager' || auth.isAdmin
})

function getFileIcon(item: NCItem): string {
  return fileIcon(item)
}

function formatDate(dt: string | null): string {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString()
}

function getDownloadUrl(item: NCItem): string {
  if (!selectedFolderId.value) return '#'
  return downloadFile(selectedFolderId.value, item.nc_path)
}

function permTagType(perm: string) {
  if (perm === 'manager') return 'success'
  if (perm === 'editor') return 'info'
  return 'default'
}

async function loadTree() {
  loadingTree.value = true
  try {
    const data = await fetchFolderTree()
    tree.value = data.items
  } catch {
    message.error(t('files.error.loadTree'))
  } finally {
    loadingTree.value = false
  }
}

async function loadDetail(folderId: string) {
  loadingDetail.value = true
  try {
    const data = await fetchFolderDetail(folderId)
    currentFolder.value = data.folder
    ncItems.value = data.items
    breadcrumbs.value = data.breadcrumbs
  } catch {
    message.error(t('files.error.loadFolder'))
  } finally {
    loadingDetail.value = false
  }
}

function selectFolder(id: string) {
  selectedFolderId.value = id
}

function openSubFolder(item: NCItem) {
  const node = findNodeByNcPath(tree.value, item.nc_path)
  if (node) selectFolder(node.id)
}

function findNodeByNcPath(nodes: FileFolderTreeNode[], path: string): FileFolderTreeNode | null {
  for (const n of nodes) {
    if (n.nc_path === path) return n
    const child = findNodeByNcPath(n.children, path)
    if (child) return child
  }
  return null
}

watch(selectedFolderId, (id) => {
  if (id) loadDetail(id)
})

function openCreateRoot() {
  createParentId.value = null
  createForm.value = { name: '', description: '' }
  showCreateModal.value = true
}

function openCreateChild(folderId: string) {
  createParentId.value = folderId
  createForm.value = { name: '', description: '' }
  showCreateModal.value = true
}

async function submitCreate() {
  if (!createForm.value.name.trim()) return
  creating.value = true
  try {
    await createFolder({
      name: createForm.value.name.trim(),
      parent_id: createParentId.value,
      description: createForm.value.description || null,
    })
    showCreateModal.value = false
    message.success(t('files.folders.created'))
    await loadTree()
  } catch {
    message.error(t('files.error.createFolder'))
  } finally {
    creating.value = false
  }
}

function confirmDeleteFolder(folderId: string) {
  dialog.warning({
    title: t('files.folders.deleteTitle'),
    content: t('files.folders.deleteConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await deleteFolder(folderId)
        message.success(t('files.folders.deleted'))
        if (selectedFolderId.value === folderId) selectedFolderId.value = null
        await loadTree()
      } catch {
        message.error(t('files.error.deleteFolder'))
      }
    },
  })
}

function openManage(folderId: string) {
  permsForFolderId.value = folderId
  grantForm.value = { subject_type: 'user', subject_id: '', subject_name: '', permission: 'viewer' }
  showPermsModal.value = true
  loadPermissions(folderId)
}

async function loadPermissions(folderId: string) {
  loadingPerms.value = true
  try {
    const data = await fetchPermissions(folderId)
    permissions.value = data.items
  } catch {
    message.error(t('files.error.loadPerms'))
  } finally {
    loadingPerms.value = false
  }
}

async function submitGrant() {
  if (!permsForFolderId.value || !grantForm.value.subject_id || !grantForm.value.subject_name) return
  granting.value = true
  try {
    await grantPermission(permsForFolderId.value, grantForm.value)
    message.success(t('files.permissions.granted'))
    await loadPermissions(permsForFolderId.value)
    grantForm.value.subject_id = ''
    grantForm.value.subject_name = ''
  } catch {
    message.error(t('files.error.grantPerm'))
  } finally {
    granting.value = false
  }
}

async function revokePermHandler(perm: FilePermission) {
  if (!permsForFolderId.value) return
  try {
    await revokePermission(permsForFolderId.value, perm.id)
    message.success(t('files.permissions.revoked'))
    await loadPermissions(permsForFolderId.value)
  } catch {
    message.error(t('files.error.revokePerm'))
  }
}

const permColumns = computed(() => [
  { title: t('files.permissions.type'), key: 'subject_type', width: 80 },
  { title: t('files.permissions.name'), key: 'subject_name' },
  { title: t('files.permissions.level'), key: 'permission', width: 100 },
  {
    title: '',
    key: 'actions',
    width: 80,
    render: (row: FilePermission) =>
      h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: () => revokePermHandler(row) }, () => t('common.delete')),
  },
])

function triggerUpload() {
  fileInputRef.value?.click()
}

async function handleFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length || !selectedFolderId.value) return
  const files = Array.from(input.files)
  input.value = ''
  uploading.value = true
  try {
    const result = await uploadFiles(selectedFolderId.value, files)
    if (result.uploaded.length) {
      message.success(t('files.uploaded', { n: result.uploaded.length }))
    }
    if (result.failed.length) {
      message.warning(t('files.uploadFailed', { n: result.failed.length }))
    }
    await loadDetail(selectedFolderId.value)
  } catch {
    message.error(t('files.error.upload'))
  } finally {
    uploading.value = false
  }
}

function confirmDeleteFile(item: NCItem) {
  dialog.warning({
    title: t('files.deleteFileTitle'),
    content: `${t('files.deleteFileConfirm')} "${item.name}"?`,
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      if (!selectedFolderId.value) return
      try {
        await deleteFile(selectedFolderId.value, item.nc_path)
        message.success(t('files.fileDeleted'))
        await loadDetail(selectedFolderId.value)
      } catch {
        message.error(t('files.error.deleteFile'))
      }
    },
  })
}

async function openCollabora(item: NCItem) {
  if (!selectedFolderId.value) return
  try {
    const resp = await openInCollabora(selectedFolderId.value, item.nc_path)
    window.open(resp.url, '_blank', 'noopener,noreferrer')
  } catch {
    message.error(t('files.error.collabora'))
  }
}

onMounted(loadTree)
</script>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({ name: 'FilesPage' })
</script>

<style scoped>
.files-page {
  display: flex;
  height: 100%;
  min-height: 0;
  gap: 0;
}

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

.folder-tree {
  list-style: none;
  margin: 0;
  padding: 0;
}

.files-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 20px 24px;
  overflow-y: auto;
}

.files-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding-top: 60px;
}

.files-breadcrumbs {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  margin-bottom: 12px;
  color: var(--n-text-color-3, #666);
}

.files-breadcrumb__link {
  cursor: pointer;
  color: var(--n-primary-color, #18a058);
}

.files-breadcrumb__link:hover {
  text-decoration: underline;
}

.files-breadcrumb__sep {
  margin: 0 2px;
}

.files-breadcrumb--current {
  font-weight: 600;
  color: var(--n-text-color, #333);
}

.files-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.files-toolbar__left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.files-toolbar__right {
  display: flex;
  gap: 8px;
}

.files-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}

.files-loading {
  padding: 20px 0;
  color: var(--n-text-color-3, #999);
}

.files-empty {
  padding: 40px 0;
  text-align: center;
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.files-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--n-border-color, #e8e8e8);
  background: var(--n-card-color, #fff);
  transition: background 0.15s;
}

.files-item--dir {
  cursor: pointer;
}

.files-item--dir:hover {
  background: var(--n-hover-color, #f5f5f5);
}

.files-item__icon {
  font-size: 20px;
  flex-shrink: 0;
  width: 28px;
  text-align: center;
}

.file-type-icon {
  font-size: 20px;
  line-height: 1;
}

.files-item__info {
  flex: 1;
  min-width: 0;
}

.files-item__name {
  font-size: 14px;
  font-weight: 500;
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.files-item__meta {
  font-size: 12px;
  color: var(--n-text-color-3, #999);
}

.files-item__actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.perm-grant-form {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
