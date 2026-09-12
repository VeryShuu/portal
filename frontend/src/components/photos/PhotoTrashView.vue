<template>
  <div class="trash-view">
    <header class="photos-header">
      <div
        v-if="!embedded"
        class="photos-header__info"
      >
        <h1 class="photos-title">
          {{ t('photos.trash.button') }}
        </h1>
      </div>
      <div class="photos-actions">
        <n-button
          v-if="trashPhotos.length > 0 || trashFolders.length > 0"
          type="error"
          ghost
          @click="confirmEmptyTrash"
        >
          {{ t('photos.trash.emptyAll') }}
        </n-button>
        <n-button
          v-if="!embedded"
          @click="$emit('close')"
        >
          {{ t('photos.trash.back') }}
        </n-button>
      </div>
    </header>

    <PhotosGridBase
      :photos="trashPhotos"
      :loading="loading"
    >
      <template #cell="{ photo }">
        <PhotoThumb
          :photo-id="photo.id"
          :processed="photo.processed"
          :blurhash="photo.blurhash"
          :alt="photo.original_name"
          :sizes="[400, 600]"
          sizes-attr="(max-width: 400px) 400px, 600px"
          :avif="thumbAvifUrl"
          :webp="thumbUrl"
        />
        <button
          class="photo-cell__restore"
          :title="t('photos.trash.restore')"
          @click.stop="doRestorePhoto(photo)"
        >
          ↩
        </button>
        <button
          class="photo-cell__purge"
          :title="t('photos.trash.purge')"
          @click.stop="confirmPurgePhoto(photo)"
        >
          🗑
        </button>
      </template>
    </PhotosGridBase>

    <div
      v-if="hasMorePhotos"
      class="photo-loadmore"
    >
      <n-button
        :loading="loadingMore"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ t('common.loadMore') }}
      </n-button>
    </div>

    <template v-if="trashFolders.length">
      <h3 class="trash-section-title">
        {{ t('photos.folders.title') }}
      </h3>
      <ul class="trash-folders-list">
        <li
          v-for="f in trashFolders"
          :key="f.id"
          class="trash-folder-row"
        >
          <span>{{ f.name }}</span>
          <div class="trash-folder-row__actions">
            <n-button
              size="tiny"
              @click="doRestoreFolder(f)"
            >
              {{ t('photos.trash.restore') }}
            </n-button>
            <n-button
              size="tiny"
              type="error"
              ghost
              @click="confirmPurgeFolder(f)"
            >
              {{ t('photos.trash.purge') }}
            </n-button>
          </div>
        </li>
      </ul>
    </template>

    <p
      v-if="!loading && !trashPhotos.length && !trashFolders.length"
      class="photos-empty-state"
    >
      {{ t('photos.trash.emptyTitle') }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, useMessage } from 'naive-ui'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import PhotosGridBase from './PhotosGridBase.vue'
import PhotoThumb from './PhotoThumb.vue'
import { parseApiError } from '@/utils/parseApiError'
import {
  thumbUrl,
  thumbAvifUrl,
  fetchDeletedPhotos, fetchDeletedFolders,
  restorePhoto, restoreFolder, purgePhoto, purgeFolder, emptyTrash,
  type Photo, type PhotoFolder,
} from '@/api/photos'

withDefaults(defineProps<{
  isAdmin: boolean
  embedded?: boolean
}>(), {
  embedded: false,
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'total-changed', total: number): void
  (e: 'tree-refresh'): void
}>()

const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()

const loading = ref(false)
const trashPhotos = ref<Photo[]>([])
const trashFolders = ref<PhotoFolder[]>([])

const page = ref(1)
const perPage = ref(50)
const totalPhotos = ref(0)
const loadingMore = ref(false)

const hasMorePhotos = computed(() => {
  return trashPhotos.value.length < totalPhotos.value
})

async function load() {
  loading.value = true
  page.value = 1
  try {
    const photosRes = await fetchDeletedPhotos({ page: page.value, per_page: perPage.value })
    trashPhotos.value = photosRes.items
    totalPhotos.value = photosRes.total
    emit('total-changed', photosRes.total)
    try {
      trashFolders.value = await fetchDeletedFolders()
    } catch {
      trashFolders.value = []
    }
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loadingMore.value || !hasMorePhotos.value) return
  loadingMore.value = true
  try {
    const nextPage = page.value + 1
    const photosRes = await fetchDeletedPhotos({ page: nextPage, per_page: perPage.value })
    trashPhotos.value = [...trashPhotos.value, ...photosRes.items]
    page.value = nextPage
    totalPhotos.value = photosRes.total
    emit('total-changed', photosRes.total)
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    loadingMore.value = false
  }
}

async function doRestorePhoto(p: Photo) {
  try {
    await restorePhoto(p.id)
    trashPhotos.value = trashPhotos.value.filter(x => x.id !== p.id)
    totalPhotos.value = Math.max(0, totalPhotos.value - 1)
    emit('total-changed', totalPhotos.value)
    message.success(t('photos.trash.restoreDone'))
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

async function doRestoreFolder(f: PhotoFolder) {
  try {
    await restoreFolder(f.id)
    trashFolders.value = trashFolders.value.filter(x => x.id !== f.id)
    message.success(t('photos.trash.restoreDone'))
    emit('tree-refresh')
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

async function confirmPurgeFolder(f: PhotoFolder) {
  const ok = await confirm({
    title: t('photos.trash.purgeFolderTitle'),
    content: t('photos.trash.purgeFolderConfirm', { name: f.name }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await purgeFolder(f.id)
    trashFolders.value = trashFolders.value.filter(x => x.id !== f.id)
    message.success(t('photos.trash.purgeDone'))
    emit('tree-refresh')
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

async function confirmPurgePhoto(p: Photo) {
  const ok = await confirm({
    title: t('photos.trash.purgeTitle'),
    content: t('photos.trash.purgeConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await purgePhoto(p.id)
    trashPhotos.value = trashPhotos.value.filter(x => x.id !== p.id)
    totalPhotos.value = Math.max(0, totalPhotos.value - 1)
    emit('total-changed', totalPhotos.value)
    message.success(t('photos.trash.purgeDone'))
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

let emptyPollTimer: ReturnType<typeof setInterval> | null = null

function stopEmptyPolling() {
  if (emptyPollTimer) {
    clearInterval(emptyPollTimer)
    emptyPollTimer = null
  }
}

onUnmounted(() => {
  stopEmptyPolling()
})

async function confirmEmptyTrash() {
  const ok = await confirm({
    title: t('photos.trash.emptyAll'),
    content: t('photos.trash.emptyAllConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await emptyTrash()
    message.info(t('photos.trash.emptyQueued'))

    stopEmptyPolling()
    emptyPollTimer = setInterval(async () => {
      await load()
      const totalItems = trashPhotos.value.length + trashFolders.value.length
      if (totalItems === 0) {
        stopEmptyPolling()
      }
    }, 3000)
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

onMounted(load)
</script>

<style scoped>
.photos-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 20px; gap: 16px;
}
.photos-header__info { flex: 1; min-width: 0; }
.photos-title { margin: 0 0 4px; font-size: 22px; }
.photos-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-start; }
.photos-empty-state { text-align: center; color: var(--color-text-muted); padding: 60px 20px; }

.photo-loadmore { text-align: center; margin-top: 16px; }

.photo-cell__restore {
  position: absolute; top: 4px; right: 4px;
  background: rgba(0,0,0,0.6); color: #fff; border: 0; cursor: pointer;
  width: 28px; height: 28px; border-radius: 50%; font-size: 16px; line-height: 1;
  display: none; align-items: center; justify-content: center;
  z-index: 1;
}
:deep(.photo-cell:hover) .photo-cell__restore { display: inline-flex; }
.photo-cell__purge {
  position: absolute; top: 4px; right: 36px;
  background: rgba(180,30,30,0.75); color: #fff; border: 0; cursor: pointer;
  width: 28px; height: 28px; border-radius: 50%; font-size: 14px; line-height: 1;
  display: none; align-items: center; justify-content: center;
  z-index: 1;
}
:deep(.photo-cell:hover) .photo-cell__purge { display: inline-flex; }

.trash-section-title { margin: 16px 0 8px; font-size: 14px; font-weight: 600; }
.trash-folders-list { list-style: none; margin: 0; padding: 0; }
.trash-folder-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid var(--color-border); font-size: 13px;
}
.trash-folder-row:last-child { border-bottom: 0; }
.trash-folder-row__actions { display: flex; gap: 6px; }
</style>
