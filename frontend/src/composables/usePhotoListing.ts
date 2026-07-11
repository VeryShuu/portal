import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import {
  deletePhoto,
  type FolderPhotosParams,
  type Photo,
  type PhotoTag,
} from '@/api/photos'
import { usePhotosStore, RECENT_LIMIT } from '@/stores/photos'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { usePhotoFolderPhotosQuery, usePhotoAllTagsQuery } from '@/queries/photos'
import { queryKeys } from '@/queries/keys'
import { parseApiError } from '@/utils/parseApiError'

export interface UsePhotoListingOptions {
  selectedFolderId: Ref<string | null>
  pageSize?: number
}

export function usePhotoListing(opts: UsePhotoListingOptions) {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()
  const photosStore = usePhotosStore()
  const queryClient = useQueryClient()

  const pageSize = opts.pageSize ?? 60

  const photos = ref<Photo[]>([])
  const totalPhotos = ref(0)
  const page = ref(1)

  const sortBy = ref<'created_at' | 'taken_at' | 'original_name'>('created_at')

  const photoTagsMap = ref<Record<string, PhotoTag[]>>({})
  const activeTagFilter = ref<string | null>(null)

  const hasActiveFilters = computed(() => !!activeTagFilter.value)

  const queryParams = computed<FolderPhotosParams>(() => {
    const p: FolderPhotosParams = {
      page: page.value,
      per_page: pageSize,
      sort: sortBy.value,
    }
    if (activeTagFilter.value) {
      p.tag_id = activeTagFilter.value
    }
    return p
  })

  const photosQuery = usePhotoFolderPhotosQuery(opts.selectedFolderId, queryParams)
  const loadingPhotos = computed(() => photosQuery.isFetching.value)

  const tagsQuery = usePhotoAllTagsQuery()
  const tags = computed(() => tagsQuery.data.value ?? [])

  watch(
    () => photosQuery.error.value,
    (err) => {
      if (err) {
        message.error(t('errors.generic'))
      }
    }
  )

  watch(
    () => photosQuery.data.value,
    (newData) => {
      if (!newData) return
      if (page.value === 1) {
        photos.value = newData.items
      } else {
        const existingIds = new Set(photos.value.map(p => p.id))
        const newItems = newData.items.filter(p => !existingIds.has(p.id))
        photos.value = [...photos.value, ...newItems]
      }
      totalPhotos.value = newData.total
    },
    { immediate: true }
  )

  async function loadPhotos() {
    await photosQuery.refetch()
  }

  async function loadMorePhotos() {
    if (loadingPhotos.value) return
    page.value++
  }

  function onSortChange() {
    page.value = 1
    photos.value = []
  }

  async function reloadFromFirstPage() {
    page.value = 1
    photos.value = []
    await photosQuery.refetch()
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
      await queryClient.invalidateQueries({
        queryKey: queryKeys.photos.folderPhotos(opts.selectedFolderId.value ?? '', {}),
        exact: false,
      })
      message.success(t('photos.deleted'))
      photosStore.loadRecent(RECENT_LIMIT)
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }

  async function loadTags() {
    await tagsQuery.refetch()
  }

  function setTagFilter(tag: PhotoTag) {
    activeTagFilter.value = activeTagFilter.value === tag.id ? null : tag.id
    page.value = 1
    photos.value = []
  }

  function clearTagFilter() {
    activeTagFilter.value = null
    page.value = 1
    photos.value = []
  }

  function onTagsUpdated(photoId: string, updatedTags: PhotoTag[]) {
    photoTagsMap.value = { ...photoTagsMap.value, [photoId]: updatedTags }
  }

  function resetForFolder() {
    page.value = 1
    photos.value = []
    totalPhotos.value = 0
  }

  let _refetchTimer: ReturnType<typeof setTimeout> | null = null
  function _scheduleRefetch() {
    if (_refetchTimer) return
    _refetchTimer = setTimeout(() => {
      _refetchTimer = null
      const fid = opts.selectedFolderId.value
      if (!fid) return
      queryClient.invalidateQueries({
        queryKey: queryKeys.photos.folderPhotos(fid, {}),
        exact: false,
      })
    }, 400)
  }

  function _onPhotoProcessed(ev: Event) {
    const detail = (ev as CustomEvent<{ photo_id: string; folder_id?: string }>).detail
    if (!detail) return
    const fid = opts.selectedFolderId.value
    if (!fid || (detail.folder_id && detail.folder_id !== fid)) return
    _scheduleRefetch()
  }

  onMounted(() => {
    window.addEventListener('photos:processed', _onPhotoProcessed)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('photos:processed', _onPhotoProcessed)
    if (_refetchTimer) {
      clearTimeout(_refetchTimer)
      _refetchTimer = null
    }
  })

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
