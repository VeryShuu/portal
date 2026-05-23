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
          v-if="isAdmin && trashPhotos.length > 0"
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

    <div
      v-if="loading"
      class="photo-grid"
    >
      <div
        v-for="i in 12"
        :key="`tsk-${i}`"
        class="photo-skeleton"
      />
    </div>
    <div
      v-else-if="trashPhotos.length"
      class="photo-grid"
    >
      <div
        v-for="p in trashPhotos"
        :key="p.id"
        class="photo-cell"
        draggable="false"
      >
        <picture>
          <source
            type="image/avif"
            :srcset="`${thumbAvifUrl(p.id, 400)} 400w, ${thumbAvifUrl(p.id, 600)} 600w`"
            sizes="(max-width: 400px) 400px, 600px"
          >
          <source
            type="image/webp"
            :srcset="`${thumbUrl(p.id, 400)} 400w, ${thumbUrl(p.id, 600)} 600w`"
            sizes="(max-width: 400px) 400px, 600px"
          >
          <img
            :src="thumbUrl(p.id, 600)"
            :alt="p.original_name"
            loading="lazy"
            draggable="false"
            class="photo-cell__img"
          >
        </picture>
        <button
          class="photo-cell__restore"
          :title="t('photos.trash.restore')"
          @click.stop="doRestorePhoto(p)"
        >
          ↩
        </button>
        <button
          class="photo-cell__purge"
          :title="t('photos.trash.purge')"
          @click.stop="confirmPurgePhoto(p)"
        >
          🗑
        </button>
      </div>
    </div>

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
    <p
      v-else
      class="photos-empty-state"
    >
      {{ t('photos.trash.emptyTitle') }}
    </p>

    <template v-if="isAdmin && trashFolders.length">
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, useMessage } from 'naive-ui'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import {
  thumbUrl,
  thumbAvifUrl,
  fetchDeletedPhotos, fetchDeletedFolders,
  restorePhoto, restoreFolder, purgePhoto, purgeFolder, emptyTrash,
  type Photo, type PhotoFolder,
} from '@/api/photos'

const props = withDefaults(defineProps<{
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
    if (props.isAdmin) {
      try {
        trashFolders.value = await fetchDeletedFolders()
      } catch {
        trashFolders.value = []
      }
    }
  } catch {
    message.error(t('errors.generic'))
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
  } catch {
    message.error(t('errors.generic'))
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
  } catch {
    message.error(t('errors.generic'))
  }
}

async function doRestoreFolder(f: PhotoFolder) {
  try {
    await restoreFolder(f.id)
    trashFolders.value = trashFolders.value.filter(x => x.id !== f.id)
    message.success(t('photos.trash.restoreDone'))
    emit('tree-refresh')
  } catch {
    message.error(t('errors.generic'))
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
  } catch {
    message.error(t('errors.generic'))
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
  } catch {
    message.error(t('errors.generic'))
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
      const totalItems = trashPhotos.value.length + (props.isAdmin ? trashFolders.value.length : 0)
      if (totalItems === 0) {
        stopEmptyPolling()
      }
    }, 3000)
  } catch {
    message.error(t('errors.generic'))
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

.photo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.photo-cell {
  position: relative; aspect-ratio: 1; overflow: hidden;
  border-radius: var(--radius-sm); background: var(--color-bg-muted); cursor: pointer;
}
.photo-cell__img { width: 100%; height: 100%; object-fit: cover; }
.photo-skeleton {
  aspect-ratio: 1; border-radius: var(--radius-sm);
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-border) 50%, var(--color-bg-muted) 75%);
  background-size: 200% 100%; animation: skel 1.4s infinite;
}
@keyframes skel { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

.photo-cell__restore {
  position: absolute; top: 4px; right: 4px;
  background: rgba(0,0,0,0.6); color: #fff; border: 0; cursor: pointer;
  width: 28px; height: 28px; border-radius: 50%; font-size: 16px; line-height: 1;
  display: none; align-items: center; justify-content: center;
}
.photo-cell:hover .photo-cell__restore { display: inline-flex; }
.photo-cell__purge {
  position: absolute; top: 4px; right: 36px;
  background: rgba(180,30,30,0.75); color: #fff; border: 0; cursor: pointer;
  width: 28px; height: 28px; border-radius: 50%; font-size: 14px; line-height: 1;
  display: none; align-items: center; justify-content: center;
}
.photo-cell:hover .photo-cell__purge { display: inline-flex; }

.trash-section-title { margin: 16px 0 8px; font-size: 14px; font-weight: 600; }
.trash-folders-list { list-style: none; margin: 0; padding: 0; }
.trash-folder-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid var(--color-border); font-size: 13px;
}
.trash-folder-row:last-child { border-bottom: 0; }
.trash-folder-row__actions { display: flex; gap: 6px; }
</style>
