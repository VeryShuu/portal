<template>
  <div class="photos-page">
    <!-- Sidebar: folder tree -->
    <aside class="photos-side">
      <div class="photos-side__head">
        <h2 class="photos-side__title">{{ t('photos.folders.title') }}</h2>
        <n-button
          v-if="auth.isAdmin"
          size="tiny"
          type="primary"
          ghost
          @click="openCreateRoot"
        >+ {{ t('photos.folders.newRoot') }}</n-button>
      </div>

      <div v-if="loadingTree" class="photos-side__loading">{{ t('common.loading') }}</div>
      <ul v-else-if="tree.length" class="folder-tree">
        <FolderNode
          v-for="n in tree"
          :key="n.id"
          :node="n"
          :selected-id="selectedFolderId"
          @select="selectFolder"
          @subfolder="openCreateChild"
          @permissions="openPermissions"
          @delete="confirmDeleteFolder"
        />
      </ul>
      <p v-else class="photos-side__empty">{{ t('photos.folders.empty') }}</p>
    </aside>

    <!-- Main: photos in folder -->
    <main class="photos-main">
      <div v-if="!selectedFolder" class="photos-empty-state">
        <p>{{ t('photos.selectFolder') }}</p>
      </div>

      <template v-else>
        <header class="photos-header">
          <div>
            <h1 class="photos-title">{{ selectedFolder.name }}</h1>
            <p v-if="selectedFolder.description" class="photos-desc">{{ selectedFolder.description }}</p>
            <p class="photos-meta">{{ t('photos.count', { n: selectedFolder.photos_count }) }}</p>
          </div>
          <div class="photos-actions">
            <n-button v-if="canUpload" type="primary" @click="triggerUpload">
              + {{ t('photos.upload.button') }}
            </n-button>
            <n-button v-if="canManage" @click="openPermissions(selectedFolder)">
              {{ t('photos.permissions.manage') }}
            </n-button>
            <input
              ref="fileInputRef"
              type="file"
              multiple
              accept="image/*,.heic,.heif"
              style="display:none"
              @change="onFilesPicked"
            />
          </div>
        </header>

        <div v-if="uploading" class="upload-progress">
          {{ t('photos.upload.inProgress', { done: uploadedCount, total: uploadTotal }) }}
        </div>

        <div v-if="loadingPhotos" class="photo-grid">
          <div v-for="i in 12" :key="`pgsk-${i}`" class="photo-skeleton" />
        </div>
        <div v-else-if="photos.length" class="photo-grid">
          <div
            v-for="(p, idx) in photos"
            :key="p.id"
            class="photo-cell"
            @click="openLightbox(idx)"
          >
            <img
              :src="thumbUrl(p.id, 600)"
              :alt="p.original_name"
              loading="lazy"
              class="photo-cell__img"
            />
            <button
              v-if="canDelete(p)"
              class="photo-cell__del"
              :aria-label="t('common.delete')"
              @click.stop="confirmDeletePhoto(p)"
            >×</button>
          </div>
        </div>
        <p v-else class="photos-empty-state">{{ t('photos.empty') }}</p>

        <div v-if="totalPhotos > photos.length" class="photo-loadmore">
          <n-button @click="loadMorePhotos">{{ t('common.loadMore') }}</n-button>
        </div>
      </template>
    </main>

    <!-- Lightbox -->
    <div v-if="lightboxIdx !== null" class="lightbox" @click.self="closeLightbox" @wheel.prevent="onLightboxWheel">
      <button class="lightbox__close" :title="t('common.close')" @click="closeLightbox">✕</button>
      <button class="lightbox__nav lightbox__nav--prev" :title="t('common.prev')" @click="prev">‹</button>
      <div class="lightbox__stage" @click.self="closeLightbox">
        <img
          v-if="currentLightboxPhoto"
          :src="thumbUrl(currentLightboxPhoto.id, 1600)"
          :alt="currentLightboxPhoto.original_name"
          class="lightbox__img"
          :style="lightboxImgStyle"
          @click.stop
        />
      </div>
      <button class="lightbox__nav lightbox__nav--next" :title="t('common.next')" @click="next">›</button>

      <div class="lightbox__toolbar" @click.stop>
        <button class="lb-btn" :title="t('photos.lightbox.zoomOut')" @click="zoomOut">−</button>
        <span class="lb-zoom">{{ Math.round(zoom * 100) }}%</span>
        <button class="lb-btn" :title="t('photos.lightbox.zoomIn')" @click="zoomIn">+</button>
        <button class="lb-btn" :title="t('photos.lightbox.rotate')" @click="rotateLeft">⟲</button>
        <button class="lb-btn" :title="t('photos.lightbox.rotateRight')" @click="rotateRight">⟳</button>
        <button class="lb-btn" :title="t('photos.lightbox.reset')" @click="resetView">⤾</button>
        <a
          v-if="currentLightboxPhoto"
          class="lb-btn lb-btn--link"
          :href="originalUrl(currentLightboxPhoto.id, true)"
          :download="currentLightboxPhoto.original_name"
          :title="t('photos.lightbox.download')"
        >⬇</a>
        <button class="lb-btn" :title="t('photos.lightbox.copyLink')" @click="copyInPortalLink">🔗</button>
        <button
          v-if="canShareCurrent"
          class="lb-btn"
          :title="t('photos.lightbox.createShareLink')"
          :disabled="creatingShare"
          @click="openShareModal"
        >🌐</button>
      </div>

      <div v-if="currentLightboxPhoto" class="lightbox__info">
        <strong>{{ currentLightboxPhoto.original_name }}</strong>
        <span v-if="currentLightboxPhoto.taken_at"> · {{ new Date(currentLightboxPhoto.taken_at).toLocaleString() }}</span>
        <span v-if="currentLightboxPhoto.width">  · {{ currentLightboxPhoto.width }}×{{ currentLightboxPhoto.height }}</span>
      </div>
    </div>

    <!-- Share modal -->
    <n-modal
      v-model:show="shareModalOpen"
      preset="card"
      :title="t('photos.lightbox.createShareLink')"
      style="width:520px;max-width:94vw"
    >
      <n-form>
        <n-form-item :label="t('photos.lightbox.expiresIn')">
          <n-select
            v-model:value="shareExpiresInDays"
            :options="[
              { label: t('photos.lightbox.expires1d'), value: 1 },
              { label: t('photos.lightbox.expires7d'), value: 7 },
              { label: t('photos.lightbox.expires30d'), value: 30 },
              { label: t('photos.lightbox.expires90d'), value: 90 },
              { label: t('photos.lightbox.expiresNever'), value: null as unknown as number },
            ]"
          />
        </n-form-item>
        <div v-if="shareUrl" class="share-result">
          <n-input :value="shareUrl" readonly />
          <n-button size="small" @click="copyShareUrl">{{ t('common.copy') }}</n-button>
        </div>
        <div class="share-actions">
          <n-button @click="shareModalOpen = false">{{ t('common.close') }}</n-button>
          <n-button type="primary" :loading="creatingShare" @click="generateShareLink">
            {{ t('photos.lightbox.generate') }}
          </n-button>
        </div>
      </n-form>
    </n-modal>

    <!-- Create folder modal -->
    <n-modal
      v-model:show="folderModalOpen"
      preset="dialog"
      :title="t('photos.folders.create')"
      :positive-text="t('common.create')"
      :negative-text="t('common.cancel')"
      @positive-click="submitCreateFolder"
      @negative-click="folderModalOpen = false"
    >
      <n-form>
        <n-form-item :label="t('photos.folders.name')">
          <n-input v-model:value="newFolderName" :placeholder="t('photos.folders.namePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('photos.folders.description')">
          <n-input v-model:value="newFolderDesc" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
    </n-modal>

    <!-- Permissions modal -->
    <n-modal
      v-model:show="permsModalOpen"
      preset="card"
      :title="t('photos.permissions.title')"
      style="width:540px;max-width:94vw"
      :mask-closable="true"
    >
      <div v-if="permsTarget">
        <p class="perms-target"><strong>{{ permsTarget.name }}</strong></p>
        <ul v-if="permsList.length" class="perms-list">
          <li v-for="p in permsList" :key="p.id" class="perms-row">
            <span>{{ p.subject_name }} <em>({{ t(`photos.permissions.perm_${p.permission}`) }})</em></span>
            <n-button size="tiny" type="error" ghost @click="revoke(p)">{{ t('common.delete') }}</n-button>
          </li>
        </ul>
        <p v-else class="perms-empty">{{ t('photos.permissions.empty') }}</p>

        <div class="perms-add">
          <h4>{{ t('photos.permissions.add') }}</h4>
          <n-form>
            <n-form-item :label="t('photos.permissions.subjectType')">
              <n-select
                v-model:value="newPerm.subject_type"
                :options="[
                  { label: t('photos.permissions.subjectUser'), value: 'user' },
                  { label: t('photos.permissions.subjectGroup'), value: 'group' },
                ]"
              />
            </n-form-item>
            <n-form-item :label="t('photos.permissions.subjectId')">
              <n-input v-model:value="newPerm.subject_id" placeholder="keycloak-id или group-id" />
            </n-form-item>
            <n-form-item :label="t('photos.permissions.subjectName')">
              <n-input v-model:value="newPerm.subject_name" />
            </n-form-item>
            <n-form-item :label="t('photos.permissions.level')">
              <n-select
                v-model:value="newPerm.permission"
                :options="[
                  { label: t('photos.permissions.perm_viewer'), value: 'viewer' },
                  { label: t('photos.permissions.perm_uploader'), value: 'uploader' },
                  { label: t('photos.permissions.perm_manager'), value: 'manager' },
                ]"
              />
            </n-form-item>
            <n-button type="primary" :loading="permsAdding" @click="addPerm">
              {{ t('photos.permissions.add') }}
            </n-button>
          </n-form>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NButton, NModal, NForm, NFormItem, NInput, NSelect, useMessage, useDialog,
} from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import {
  fetchFolderTree, fetchFolder, fetchFolderPhotos, createFolder, deleteFolder,
  uploadPhotos, deletePhoto, fetchPermissions, grantPermission, revokePermission,
  thumbUrl, originalUrl, createShareLink,
  type Photo, type PhotoFolder, type PhotoFolderTreeNode, type PhotoPermission,
} from '@/api/photos'
import FolderNode from '@/components/photos/FolderNode.vue'

const route = useRoute()
const { t } = useI18n()
const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()

const tree = ref<PhotoFolderTreeNode[]>([])
const loadingTree = ref(false)
const selectedFolderId = ref<string | null>(null)
const selectedFolder = ref<PhotoFolder | null>(null)
const photos = ref<Photo[]>([])
const totalPhotos = ref(0)
const page = ref(1)
const pageSize = 60
const loadingPhotos = ref(false)

const fileInputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadedCount = ref(0)
const uploadTotal = ref(0)

const folderModalOpen = ref(false)
const newFolderParent = ref<string | null>(null)
const newFolderName = ref('')
const newFolderDesc = ref('')

const permsModalOpen = ref(false)
const permsTarget = ref<PhotoFolder | PhotoFolderTreeNode | null>(null)
const permsList = ref<PhotoPermission[]>([])
const permsAdding = ref(false)
const newPerm = ref<{ subject_type: 'user' | 'group'; subject_id: string; subject_name: string; permission: 'viewer' | 'uploader' | 'manager' }>({
  subject_type: 'user', subject_id: '', subject_name: '', permission: 'viewer',
})

const lightboxIdx = ref<number | null>(null)
const currentLightboxPhoto = computed(() => lightboxIdx.value !== null ? photos.value[lightboxIdx.value] : null)

const zoom = ref(1)
const rotation = ref(0)
const lightboxImgStyle = computed(() => ({
  transform: `rotate(${rotation.value}deg) scale(${zoom.value})`,
  transition: 'transform 0.15s ease-out',
}))

const shareModalOpen = ref(false)
const shareExpiresInDays = ref<number | null>(7)
const shareUrl = ref('')
const creatingShare = ref(false)
const canShareCurrent = computed(() => {
  const p = selectedFolder.value?.permission
  return p === 'uploader' || p === 'manager' || auth.isAdmin
})

const canUpload = computed(() => {
  const p = selectedFolder.value?.permission
  return p === 'uploader' || p === 'manager' || auth.isAdmin
})
const canManage = computed(() => {
  const p = selectedFolder.value?.permission
  return p === 'manager' || auth.isAdmin
})
function canDelete(p: Photo): boolean {
  return canManage.value || (auth.user?.id === p.uploaded_by)
}

async function loadTree() {
  loadingTree.value = true
  try {
    const data = await fetchFolderTree()
    tree.value = data.items
  } catch {
    message.error(t('errors.generic'))
  } finally {
    loadingTree.value = false
  }
}

async function selectFolder(node: PhotoFolderTreeNode) {
  selectedFolderId.value = node.id
  page.value = 1
  photos.value = []
  totalPhotos.value = 0
  try {
    selectedFolder.value = await fetchFolder(node.id)
    await loadPhotos()
  } catch {
    message.error(t('errors.generic'))
  }
}

async function loadPhotos() {
  if (!selectedFolderId.value) return
  loadingPhotos.value = true
  try {
    const res = await fetchFolderPhotos(selectedFolderId.value, { page: page.value, per_page: pageSize, sort: 'created_at' })
    if (page.value === 1) photos.value = res.items
    else photos.value = [...photos.value, ...res.items]
    totalPhotos.value = res.total
  } finally {
    loadingPhotos.value = false
  }
}

async function loadMorePhotos() {
  page.value++
  await loadPhotos()
}

function openCreateRoot() {
  newFolderParent.value = null
  newFolderName.value = ''
  newFolderDesc.value = ''
  folderModalOpen.value = true
}

function openCreateChild(node: PhotoFolderTreeNode) {
  newFolderParent.value = node.id
  newFolderName.value = ''
  newFolderDesc.value = ''
  folderModalOpen.value = true
}

async function submitCreateFolder() {
  if (!newFolderName.value.trim()) { message.warning(t('photos.folders.nameRequired')); return false }
  try {
    await createFolder({
      parent_id: newFolderParent.value,
      name: newFolderName.value.trim(),
      description: newFolderDesc.value.trim() || null,
    })
    message.success(t('photos.folders.created'))
    folderModalOpen.value = false
    await loadTree()
  } catch {
    message.error(t('errors.generic'))
    return false
  }
}

function confirmDeleteFolder(node: PhotoFolderTreeNode) {
  dialog.warning({
    title: t('photos.folders.deleteTitle'),
    content: t('photos.folders.deleteConfirm', { name: node.name }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await deleteFolder(node.id)
        message.success(t('photos.folders.deleted'))
        if (selectedFolderId.value === node.id) {
          selectedFolderId.value = null
          selectedFolder.value = null
          photos.value = []
        }
        await loadTree()
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

function triggerUpload() { fileInputRef.value?.click() }

async function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files || !input.files.length || !selectedFolderId.value) return
  const files = Array.from(input.files)
  uploading.value = true
  uploadTotal.value = files.length
  uploadedCount.value = 0
  try {
    const batchSize = 10
    for (let i = 0; i < files.length; i += batchSize) {
      const slice = files.slice(i, i + batchSize)
      await uploadPhotos(selectedFolderId.value, slice)
      uploadedCount.value += slice.length
    }
    message.success(t('photos.upload.done', { n: files.length }))
    page.value = 1
    await loadPhotos()
  } catch {
    message.error(t('photos.upload.error'))
  } finally {
    uploading.value = false
    if (input) input.value = ''
  }
}

function confirmDeletePhoto(p: Photo) {
  dialog.warning({
    title: t('photos.deleteTitle'),
    content: t('photos.deleteConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await deletePhoto(p.id)
        photos.value = photos.value.filter(x => x.id !== p.id)
        totalPhotos.value = Math.max(0, totalPhotos.value - 1)
        message.success(t('photos.deleted'))
      } catch {
        message.error(t('errors.generic'))
      }
    },
  })
}

async function openPermissions(node: PhotoFolder | PhotoFolderTreeNode) {
  permsTarget.value = node
  try {
    const r = await fetchPermissions(node.id)
    permsList.value = r.items
  } catch {
    permsList.value = []
  }
  permsModalOpen.value = true
}

async function addPerm() {
  if (!permsTarget.value) return
  if (!newPerm.value.subject_id.trim() || !newPerm.value.subject_name.trim()) {
    message.warning(t('photos.permissions.fieldsRequired'))
    return
  }
  permsAdding.value = true
  try {
    const created = await grantPermission(permsTarget.value.id, { ...newPerm.value })
    permsList.value = [...permsList.value.filter(p => p.subject_id !== created.subject_id), created]
    newPerm.value.subject_id = ''
    newPerm.value.subject_name = ''
    message.success(t('photos.permissions.granted'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    permsAdding.value = false
  }
}

async function revoke(p: PhotoPermission) {
  if (!permsTarget.value) return
  try {
    await revokePermission(permsTarget.value.id, p.subject_id)
    permsList.value = permsList.value.filter(x => x.id !== p.id)
    message.success(t('photos.permissions.revoked'))
  } catch {
    message.error(t('errors.generic'))
  }
}

function resetView() { zoom.value = 1; rotation.value = 0 }
function openLightbox(idx: number) { lightboxIdx.value = idx; resetView() }
function closeLightbox() { lightboxIdx.value = null; resetView() }
function prev() {
  if (lightboxIdx.value === null) return
  lightboxIdx.value = (lightboxIdx.value - 1 + photos.value.length) % photos.value.length
  resetView()
}
function next() {
  if (lightboxIdx.value === null) return
  lightboxIdx.value = (lightboxIdx.value + 1) % photos.value.length
  resetView()
}
function zoomIn() { zoom.value = Math.min(8, +(zoom.value + 0.25).toFixed(2)) }
function zoomOut() { zoom.value = Math.max(0.25, +(zoom.value - 0.25).toFixed(2)) }
function rotateLeft() { rotation.value = (rotation.value - 90) % 360 }
function rotateRight() { rotation.value = (rotation.value + 90) % 360 }
function onLightboxWheel(e: WheelEvent) {
  if (e.deltaY < 0) zoomIn(); else zoomOut()
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.focus(); ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch { return false }
}

async function copyInPortalLink() {
  const p = currentLightboxPhoto.value
  if (!p) return
  const folderQ = selectedFolderId.value ? `folder=${selectedFolderId.value}&` : ''
  const url = `${window.location.origin}/photos?${folderQ}photo=${p.id}`
  const ok = await copyToClipboard(url)
  ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
}

function openShareModal() {
  shareUrl.value = ''
  shareExpiresInDays.value = 7
  shareModalOpen.value = true
}

async function generateShareLink() {
  const p = currentLightboxPhoto.value
  if (!p) return
  creatingShare.value = true
  try {
    const link = await createShareLink(p.id, shareExpiresInDays.value)
    shareUrl.value = link.url
    message.success(t('photos.lightbox.shareLinkCreated'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    creatingShare.value = false
  }
}

async function copyShareUrl() {
  if (!shareUrl.value) return
  const ok = await copyToClipboard(shareUrl.value)
  ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
}

onMounted(async () => {
  await loadTree()
  const id = (route.query.folder as string) || null
  if (id) {
    const flat = flatten(tree.value).find(n => n.id === id)
    if (flat) await selectFolder(flat)
  }
  const photoId = (route.query.photo as string) || null
  if (photoId) {
    const idx = photos.value.findIndex(p => p.id === photoId)
    if (idx >= 0) openLightbox(idx)
  }
})

function flatten(nodes: PhotoFolderTreeNode[]): PhotoFolderTreeNode[] {
  const out: PhotoFolderTreeNode[] = []
  const walk = (ns: PhotoFolderTreeNode[]) => {
    for (const n of ns) {
      out.push(n)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(nodes)
  return out
}
</script>

<style scoped>
.photos-page {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 24px;
  max-width: 1440px;
  margin: 0 auto;
}
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
.photos-side__title { margin: 0; font-size: 14px; font-weight: 700; }
.photos-side__loading, .photos-side__empty {
  font-size: 13px; color: var(--color-text-muted); margin: 12px 0;
}
.folder-tree { list-style: none; margin: 0; padding: 0; }

.photos-main {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px;
  min-height: 400px;
}
.photos-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 20px; gap: 16px;
}
.photos-title { margin: 0 0 4px; font-size: 22px; }
.photos-desc { margin: 0 0 4px; color: var(--color-text-muted); }
.photos-meta { margin: 0; font-size: 12px; color: var(--color-text-muted); }
.photos-actions { display: flex; gap: 8px; }
.photos-empty-state {
  text-align: center; color: var(--color-text-muted); padding: 60px 20px;
}

.photo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.photo-cell {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: var(--color-bg-muted);
  cursor: pointer;
}
.photo-cell__img {
  width: 100%; height: 100%; object-fit: cover;
  transition: transform 0.2s ease;
}
.photo-cell:hover .photo-cell__img { transform: scale(1.04); }
.photo-cell__del {
  position: absolute; top: 4px; right: 4px;
  background: rgba(0,0,0,0.6); color: #fff; border: 0; cursor: pointer;
  width: 24px; height: 24px; border-radius: 50%; font-size: 16px; line-height: 1;
  display: none;
}
.photo-cell:hover .photo-cell__del { display: inline-flex; align-items: center; justify-content: center; }

.photo-skeleton {
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-border) 50%, var(--color-bg-muted) 75%);
  background-size: 200% 100%;
  animation: skel 1.4s infinite;
}
@keyframes skel { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

.photo-loadmore { text-align: center; margin-top: 16px; }
.upload-progress {
  background: var(--color-bg-muted); padding: 8px 12px;
  border-radius: var(--radius-sm); margin-bottom: 12px;
  font-size: 13px;
}

.lightbox {
  position: fixed; inset: 0; background: rgba(0,0,0,0.92); z-index: 9999;
  display: flex; align-items: center; justify-content: center;
}
.lightbox__stage {
  width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.lightbox__img { max-width: 95vw; max-height: 90vh; object-fit: contain; user-select: none; -webkit-user-drag: none; }
.lightbox__close, .lightbox__nav {
  position: absolute; background: rgba(255,255,255,0.1); color: #fff;
  border: 0; cursor: pointer; font-size: 24px;
  width: 44px; height: 44px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; z-index: 2;
}
.lightbox__close { top: 16px; right: 16px; }
.lightbox__nav--prev { left: 16px; top: 50%; transform: translateY(-50%); }
.lightbox__nav--next { right: 16px; top: 50%; transform: translateY(-50%); }
.lightbox__toolbar {
  position: absolute; top: 16px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 6px;
  background: rgba(0,0,0,0.55); padding: 6px 10px; border-radius: 999px;
  z-index: 3;
}
.lb-btn {
  background: rgba(255,255,255,0.12); color: #fff; border: 0; cursor: pointer;
  width: 36px; height: 36px; border-radius: 50%; font-size: 16px;
  display: inline-flex; align-items: center; justify-content: center;
  text-decoration: none;
}
.lb-btn[disabled] { opacity: 0.5; cursor: not-allowed; }
.lb-btn:hover { background: rgba(255,255,255,0.22); }
.lb-zoom { color: #fff; font-size: 12px; min-width: 44px; text-align: center; }
.lightbox__info {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,0.7); color: #fff; padding: 12px 20px;
  font-size: 13px; z-index: 2;
}
.share-result { display: flex; gap: 8px; align-items: center; margin: 12px 0; }
.share-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }

.perms-target { margin-bottom: 12px; }
.perms-list { list-style: none; margin: 0 0 16px; padding: 0; }
.perms-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid var(--color-border);
}
.perms-empty { color: var(--color-text-muted); font-size: 13px; margin: 0 0 16px; }
.perms-add h4 { margin: 16px 0 8px; }

@media (max-width: 900px) {
  .photos-page { grid-template-columns: 1fr; }
  .photos-side { position: static; }
}
</style>
