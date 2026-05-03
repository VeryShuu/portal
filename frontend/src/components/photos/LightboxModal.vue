<template>
  <div
    v-if="modelValue !== null"
    class="lightbox"
    @click.self="close"
    @wheel.prevent="onLightboxWheel"
  >
    <button class="lightbox__close" :title="t('common.close')" @click="close">✕</button>
    <button class="lightbox__nav lightbox__nav--prev" :title="t('common.prev')" @click="prevManual">‹</button>

    <div class="lightbox__stage" @click.self="close">
      <picture v-if="currentPhoto">
        <source
          :srcset="`${thumbUrl(currentPhoto.id, 1000)} 1000w, ${thumbUrl(currentPhoto.id, 1600)} 1600w`"
          sizes="(max-width: 1000px) 1000px, 1600px"
        />
        <img
          :src="thumbUrl(currentPhoto.id, 1600)"
          :alt="currentPhoto.original_name"
          class="lightbox__img"
          :style="imgStyle"
          @click.stop
        />
      </picture>
    </div>

    <button class="lightbox__nav lightbox__nav--next" :title="t('common.next')" @click="nextManual">›</button>

    <div class="lightbox__toolbar" @click.stop>
      <button class="lb-btn" :title="t('photos.lightbox.zoomOut')" @click="zoomOut">−</button>
      <span class="lb-zoom">{{ Math.round(zoom * 100) }}%</span>
      <button class="lb-btn" :title="t('photos.lightbox.zoomIn')" @click="zoomIn">+</button>
      <button class="lb-btn" :title="t('photos.lightbox.rotate')" @click="rotateLeft">⟲</button>
      <button class="lb-btn" :title="t('photos.lightbox.rotateRight')" @click="rotateRight">⟳</button>
      <button class="lb-btn" :title="t('photos.lightbox.reset')" @click="resetView">⤾</button>
      <n-dropdown :options="slideshowOptions" trigger="click" @select="onSlideshowSelect">
        <button
          class="lb-btn"
          :class="{ 'lb-btn--active': slideshowActive }"
          :title="slideshowActive ? t('photos.lightbox.slideshowStop') : t('photos.lightbox.slideshow')"
        >{{ slideshowActive ? '⏸' : '▶' }}</button>
      </n-dropdown>
      <a
        v-if="currentPhoto"
        class="lb-btn lb-btn--link"
        :href="originalUrl(currentPhoto.id, true)"
        :download="currentPhoto.original_name"
        :title="t('photos.lightbox.download')"
      >⬇</a>
      <button class="lb-btn" :title="t('photos.lightbox.copyLink')" @click="copyInPortalLink">🔗</button>
      <button
        v-if="canUpload"
        class="lb-btn"
        :title="t('photos.lightbox.createShareLink')"
        :disabled="creatingShare"
        @click="openShareModal"
      >🌐</button>
      <button
        v-if="canManage && currentPhoto"
        class="lb-btn"
        :title="t('photos.myShares.shareFolder')"
        :disabled="creatingFolderShare"
        @click="openFolderShareModal"
      >📂</button>
    </div>

    <div v-if="currentPhoto" class="lightbox__info">
      <div class="lightbox__info-row">
        <span class="lightbox__breadcrumb" @click="close">{{ selectedFolder?.name }}</span>
        <span v-if="selectedFolder"> / </span>
        <strong>{{ currentPhoto.original_name }}</strong>
        <span v-if="currentPhoto.taken_at"> · {{ new Date(currentPhoto.taken_at).toLocaleString() }}</span>
        <span v-if="currentPhoto.width"> · {{ currentPhoto.width }}×{{ currentPhoto.height }}</span>
      </div>
      <div class="lightbox__tags-row" @click.stop>
        <template v-if="!editingPhotoTags">
          <n-tag
            v-for="tag in currentPhotoTags"
            :key="tag.id"
            size="small"
            class="lightbox__tag"
          >{{ tag.name }}</n-tag>
          <button v-if="canUpload" class="lightbox__tags-edit-btn" @click="startEditTags">
            {{ currentPhotoTags.length ? '✎' : t('photos.tags.addTags') }}
          </button>
        </template>
        <template v-else>
          <n-select
            v-model:value="editingTagIds"
            multiple
            filterable
            :options="tagOptions"
            size="small"
            style="min-width: 200px; max-width: 400px"
            :placeholder="t('photos.tags.addTags')"
          />
          <n-button size="tiny" type="primary" :loading="savingTags" @click="savePhotoTags">
            {{ t('photos.tags.saveTags') }}
          </n-button>
          <n-button size="tiny" @click="editingPhotoTags = false">{{ t('common.cancel') }}</n-button>
        </template>
      </div>
    </div>
  </div>

  <!-- Share photo modal -->
  <n-modal
    v-model:show="shareModalOpen"
    preset="card"
    :title="t('photos.lightbox.createShareLink')"
    style="width:520px;max-width:94vw"
  >
    <n-form>
      <n-form-item :label="t('photos.lightbox.expiresIn')">
        <n-select v-model:value="shareExpiresInDays" :options="expiryOptions" />
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

  <!-- Share folder modal -->
  <n-modal
    v-model:show="folderShareModalOpen"
    preset="card"
    :title="t('photos.myShares.shareFolder')"
    style="width:520px;max-width:94vw"
  >
    <n-form>
      <n-form-item :label="t('photos.lightbox.expiresIn')">
        <n-select v-model:value="folderShareExpiresInDays" :options="expiryOptions" />
      </n-form-item>
      <div v-if="folderShareUrl" class="share-result">
        <n-input :value="folderShareUrl" readonly />
        <n-button size="small" @click="copyFolderShareUrl">{{ t('common.copy') }}</n-button>
      </div>
      <div class="share-actions">
        <n-button @click="folderShareModalOpen = false">{{ t('common.close') }}</n-button>
        <n-button type="primary" :loading="creatingFolderShare" @click="generateFolderShareLink">
          {{ t('photos.lightbox.generate') }}
        </n-button>
      </div>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDropdown, NForm, NFormItem, NInput, NModal, NSelect, NTag, useMessage } from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import {
  thumbUrl, originalUrl, createShareLink, createFolderShareLink,
  fetchPhotoTags, setPhotoTags,
  type Photo, type PhotoFolder, type PhotoTag,
} from '@/api/photos'

const props = defineProps<{
  modelValue: number | null
  photos: Photo[]
  selectedFolder: PhotoFolder | null
  selectedFolderId: string | null
  canUpload: boolean
  canManage: boolean
  tags: PhotoTag[]
  photoTagsMap: Record<string, PhotoTag[]>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', idx: number | null): void
  (e: 'tags-updated', photoId: string, tags: PhotoTag[]): void
}>()

const { t } = useI18n()
const message = useMessage()

const currentPhoto = computed(() =>
  props.modelValue !== null ? props.photos[props.modelValue] : null,
)

const zoom = ref(1)
const rotation = ref(0)
const imgStyle = computed(() => ({
  transform: `rotate(${rotation.value}deg) scale(${zoom.value})`,
  transition: 'transform 0.15s ease-out',
}))

function resetView() { zoom.value = 1; rotation.value = 0 }
function zoomIn() { zoom.value = Math.min(8, +(zoom.value + 0.25).toFixed(2)) }
function zoomOut() { zoom.value = Math.max(0.25, +(zoom.value - 0.25).toFixed(2)) }
function rotateLeft() { rotation.value = (rotation.value - 90) % 360 }
function rotateRight() { rotation.value = (rotation.value + 90) % 360 }
function onLightboxWheel(e: WheelEvent) { if (e.deltaY < 0) zoomIn(); else zoomOut() }

function close() { stopSlideshow(); emit('update:modelValue', null); resetView() }
function prev() {
  if (props.modelValue === null) return
  emit('update:modelValue', (props.modelValue - 1 + props.photos.length) % props.photos.length)
  resetView()
}
function next() {
  if (props.modelValue === null) return
  emit('update:modelValue', (props.modelValue + 1) % props.photos.length)
  resetView()
}
function prevManual() { stopSlideshow(); prev() }
function nextManual() { stopSlideshow(); next() }

const slideshowActive = ref(false)
const slideshowInterval = ref<ReturnType<typeof setInterval> | null>(null)
const slideshowDelay = ref(5000)

const slideshowOptions = computed(() => {
  const opts: { label: string; key: string }[] = [
    { label: t('photos.lightbox.slideshow5s'), key: '5000' },
    { label: t('photos.lightbox.slideshow10s'), key: '10000' },
    { label: t('photos.lightbox.slideshow30s'), key: '30000' },
  ]
  if (slideshowActive.value) opts.unshift({ label: t('photos.lightbox.slideshowStop'), key: 'stop' })
  return opts
})

function startSlideshow(delay: number) {
  stopSlideshow()
  slideshowDelay.value = delay
  slideshowActive.value = true
  slideshowInterval.value = setInterval(() => next(), delay)
}
function stopSlideshow() {
  if (slideshowInterval.value !== null) { clearInterval(slideshowInterval.value); slideshowInterval.value = null }
  slideshowActive.value = false
}
function onSlideshowSelect(key: string) {
  if (key === 'stop') stopSlideshow(); else startSlideshow(Number(key))
}

const shareModalOpen = ref(false)
const shareExpiresInDays = ref<number | null>(7)
const shareUrl = ref('')
const creatingShare = ref(false)
const folderShareModalOpen = ref(false)
const folderShareExpiresInDays = ref<number | null>(7)
const folderShareUrl = ref('')
const creatingFolderShare = ref(false)

const expiryOptions = computed(() => [
  { label: t('photos.lightbox.expires1d'), value: 1 },
  { label: t('photos.lightbox.expires7d'), value: 7 },
  { label: t('photos.lightbox.expires30d'), value: 30 },
  { label: t('photos.lightbox.expires90d'), value: 90 },
  { label: t('photos.lightbox.expiresNever'), value: null },
] as SelectOption[])

function openShareModal() {
  shareUrl.value = ''
  shareExpiresInDays.value = 7
  shareModalOpen.value = true
}
async function generateShareLink() {
  const photo = currentPhoto.value
  if (!photo) return
  creatingShare.value = true
  try {
    const link = await createShareLink(photo.id, shareExpiresInDays.value)
    shareUrl.value = `${window.location.origin}/p/${link.token}`
    message.success(t('photos.lightbox.shareLinkCreated'))
  } catch { message.error(t('errors.generic')) }
  finally { creatingShare.value = false }
}

function openFolderShareModal() {
  folderShareUrl.value = ''
  folderShareExpiresInDays.value = 7
  folderShareModalOpen.value = true
}
async function generateFolderShareLink() {
  if (!props.selectedFolderId) return
  creatingFolderShare.value = true
  try {
    const link = await createFolderShareLink(props.selectedFolderId, folderShareExpiresInDays.value)
    folderShareUrl.value = `${window.location.origin}/photos/public/${link.token}`
    message.success(t('photos.lightbox.shareLinkCreated'))
  } catch { message.error(t('errors.generic')) }
  finally { creatingFolderShare.value = false }
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true }
    console.warn('[LightboxModal] navigator.clipboard unavailable, falling back to deprecated execCommand("copy")')
    const ta = document.createElement('textarea')
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'
    document.body.appendChild(ta); ta.focus(); ta.select()
    const ok = document.execCommand('copy'); document.body.removeChild(ta); return ok
  } catch (err) {
    console.warn('[LightboxModal] copyToClipboard failed', err)
    return false
  }
}
async function copyShareUrl() {
  const ok = await copyToClipboard(shareUrl.value)
  ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
}
async function copyFolderShareUrl() {
  const ok = await copyToClipboard(folderShareUrl.value)
  ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
}
async function copyInPortalLink() {
  const p = currentPhoto.value
  if (!p) return
  const folderQ = props.selectedFolderId ? `folder=${props.selectedFolderId}&` : ''
  const url = `${window.location.origin}/photos?${folderQ}photo=${p.id}`
  const ok = await copyToClipboard(url)
  ok ? message.success(t('photos.lightbox.copied')) : message.error(t('errors.generic'))
}

const editingPhotoTags = ref(false)
const editingTagIds = ref<string[]>([])
const savingTags = ref(false)

const currentPhotoTags = computed(() =>
  currentPhoto.value ? (props.photoTagsMap[currentPhoto.value.id] ?? []) : [],
)
const tagOptions = computed(() => props.tags.map(tag => ({ label: tag.name, value: tag.id })))

function startEditTags() {
  editingTagIds.value = currentPhotoTags.value.map(tag => tag.id)
  editingPhotoTags.value = true
}
async function savePhotoTags() {
  const photo = currentPhoto.value
  if (!photo) return
  savingTags.value = true
  try {
    const updated = await setPhotoTags(photo.id, editingTagIds.value)
    emit('tags-updated', photo.id, updated)
    editingPhotoTags.value = false
    message.success(t('photos.tags.saved'))
  } catch { message.error(t('errors.generic')) }
  finally { savingTags.value = false }
}

async function loadPhotoTags(photoId: string) {
  if (props.photoTagsMap[photoId]) return
  try {
    const data = await fetchPhotoTags(photoId)
    emit('tags-updated', photoId, data)
  } catch (err) {
    console.warn('[LightboxModal] loadPhotoTags failed', photoId, err)
  }
}

watch(() => props.modelValue, (idx) => {
  editingPhotoTags.value = false
  editingTagIds.value = []
  if (idx !== null && props.photos[idx]) loadPhotoTags(props.photos[idx].id)
})

function handleKeydown(e: KeyboardEvent) {
  if (props.modelValue === null) return
  const target = e.target as HTMLElement | null
  if (target) {
    const tag = target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) {
      return
    }
  }
  if (e.key === 'Escape') { close() }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); prevManual() }
  else if (e.key === 'ArrowRight') { e.preventDefault(); nextManual() }
  else if (e.key === 'Home') { e.preventDefault(); emit('update:modelValue', 0); resetView() }
  else if (e.key === 'End') { e.preventDefault(); emit('update:modelValue', props.photos.length - 1); resetView() }
  else if (e.key === ' ') { e.preventDefault(); if (zoom.value < 1.5) zoomIn(); else resetView() }
}

onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => { window.removeEventListener('keydown', handleKeydown); stopSlideshow() })
</script>

<style scoped>
.lightbox {
  position: fixed; inset: 0; background: rgba(0,0,0,0.92); z-index: 1500;
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
  background: rgba(0,0,0,0.55); padding: 6px 10px; border-radius: 999px; z-index: 3;
}
.lb-btn {
  background: rgba(255,255,255,0.12); color: #fff; border: 0; cursor: pointer;
  width: 36px; height: 36px; border-radius: 50%; font-size: 16px;
  display: inline-flex; align-items: center; justify-content: center;
  text-decoration: none;
}
.lb-btn[disabled] { opacity: 0.5; cursor: not-allowed; }
.lb-btn:hover { background: rgba(255,255,255,0.22); }
.lb-btn--active { background: rgba(59,130,246,0.5); }
.lb-btn--active:hover { background: rgba(59,130,246,0.7); }
.lb-zoom { color: #fff; font-size: 12px; min-width: 44px; text-align: center; }
.lightbox__info {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,0.7); color: #fff; padding: 12px 20px;
  font-size: 13px; z-index: 2;
}
.lightbox__breadcrumb { cursor: pointer; opacity: 0.7; }
.lightbox__breadcrumb:hover { opacity: 1; text-decoration: underline; }
.lightbox__info-row { margin-bottom: 4px; }
.lightbox__tags-row {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 4px;
}
.lightbox__tag { margin: 0; }
.lightbox__tags-edit-btn {
  background: transparent; border: 0; cursor: pointer; font-size: 12px;
  color: rgba(255,255,255,0.6); padding: 0;
}
.lightbox__tags-edit-btn:hover { color: #fff; }
.share-result { display: flex; gap: 8px; align-items: center; margin: 12px 0; }
.share-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
</style>
