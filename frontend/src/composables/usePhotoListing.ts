import { computed, ref } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  deletePhoto,
  fetchFolderPhotos,
  fetchFolderPhotosFiltered,
  fetchTags,
  type FolderPhotosParams,
  type Photo,
  type PhotoTag,
} from '@/api/photos'
import { usePhotosStore } from '@/stores/photos'
import { useConfirmDialog } from '@/composables/useConfirmDialog'

export interface UsePhotoListingOptions {
  selectedFolderId: Ref<string | null>
  pageSize?: number
}

export function usePhotoListing(opts: UsePhotoListingOptions) {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()
  const photosStore = usePhotosStore()

  const pageSize = opts.pageSize ?? 60

  const photos = ref<Photo[]>([])
  const totalPhotos = ref(0)
  const page = ref(1)
  const loadingPhotos = ref(false)

  const sortBy = ref<'created_at' | 'taken_at' | 'original_name'>('created_at')

  const tags = ref<PhotoTag[]>([])
  const photoTagsMap = ref<Record<string, PhotoTag[]>>({})
  const activeTagFilter = ref<string | null>(null)

  const hasActiveFilters = computed(() => !!activeTagFilter.value)

  async function loadPhotos() {
    if (!opts.selectedFolderId.value) return
    loadingPhotos.value = true
    try {
      const params: FolderPhotosParams = { page: page.value, per_page: pageSize, sort: sortBy.value }
      if (activeTagFilter.value) params.tag_id = activeTagFilter.value
      const res = hasActiveFilters.value
        ? await fetchFolderPhotosFiltered(opts.selectedFolderId.value, params)
        : await fetchFolderPhotos(opts.selectedFolderId.value, { page: page.value, per_page: pageSize, sort: sortBy.value })
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

  function onSortChange() {
    page.value = 1
    photos.value = []
    loadPhotos()
  }

  async function reloadFromFirstPage() {
    page.value = 1
    await loadPhotos()
  }

  async function confirmDeletePhoto(p: Photo) {
    const ok = await confirm({
      title: t('photos.deleteTitle'),
      content: t('photos.deleteConfirm'),
      positiveText: t('common.delete'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    try {
      await deletePhoto(p.id)
      photos.value = photos.value.filter(x => x.id !== p.id)
      totalPhotos.value = Math.max(0, totalPhotos.value - 1)
      message.success(t('photos.deleted'))
      photosStore.loadRecent(4)
    } catch {
      message.error(t('errors.generic'))
    }
  }

  async function loadTags() {
    try {
      const data = await fetchTags()
      tags.value = data.items
    } catch { /* noop */ }
  }

  function setTagFilter(tag: PhotoTag) {
    activeTagFilter.value = activeTagFilter.value === tag.id ? null : tag.id
    page.value = 1
    photos.value = []
    loadPhotos()
  }

  function clearTagFilter() {
    activeTagFilter.value = null
    page.value = 1
    photos.value = []
    loadPhotos()
  }

  function onTagsUpdated(photoId: string, updatedTags: PhotoTag[]) {
    photoTagsMap.value = { ...photoTagsMap.value, [photoId]: updatedTags }
  }

  function resetForFolder() {
    page.value = 1
    photos.value = []
    totalPhotos.value = 0
  }

  return {
    photos,
    totalPhotos,
    page,
    pageSize,
    loadingPhotos,
    sortBy,
    tags,
    photoTagsMap,
    activeTagFilter,
    hasActiveFilters,
    loadPhotos,
    loadMorePhotos,
    onSortChange,
    reloadFromFirstPage,
    confirmDeletePhoto,
    loadTags,
    setTagFilter,
    clearTagFilter,
    onTagsUpdated,
    resetForFolder,
  }
}
