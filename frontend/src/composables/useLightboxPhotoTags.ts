import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import { fetchPhotoTags, setPhotoTags } from '../api/photos'
import type { Photo, PhotoTag } from '../api/photos'
import { queryKeys } from '../queries/keys'
import { parseApiError } from '../utils/parseApiError'

export interface UseLightboxPhotoTagsOptions {
  currentPhoto: () => Photo | null
  photoTagsMap: () => Record<string, PhotoTag[]>
  allTags: () => PhotoTag[]
  onTagsUpdated: (photoId: string, tags: PhotoTag[]) => void
  photoIndex: () => number | null
  photos: () => Photo[]
}

export function useLightboxPhotoTags(opts: UseLightboxPhotoTagsOptions) {
  const { t } = useI18n()
  const message = useMessage()
  const queryClient = useQueryClient()

  const editingPhotoTags = ref(false)
  const editingTagIds = ref<string[]>([])
  const savingTags = ref(false)

  const currentPhotoTags = computed(() => {
    const photo = opts.currentPhoto()
    return photo ? (opts.photoTagsMap()[photo.id] ?? []) : []
  })

  const tagOptions = computed(() => opts.allTags().map(tag => ({ label: tag.name, value: tag.id })))

  function startEditTags() {
    editingTagIds.value = currentPhotoTags.value.map(tag => tag.id)
    editingPhotoTags.value = true
  }

  async function savePhotoTags() {
    const photo = opts.currentPhoto()
    if (!photo) return
    savingTags.value = true
    try {
      const updated = await setPhotoTags(photo.id, editingTagIds.value)
      queryClient.setQueryData(queryKeys.photos.photoTags(photo.id), updated)
      opts.onTagsUpdated(photo.id, updated)
      editingPhotoTags.value = false
      message.success(t('photos.tags.saved'))
    } catch (e) { message.error(parseApiError(e, t)) }
    finally { savingTags.value = false }
  }

  async function loadPhotoTags(photoId: string) {
    if (opts.photoTagsMap()[photoId]) return
    try {
      const data = await queryClient.ensureQueryData({
        queryKey: queryKeys.photos.photoTags(photoId),
        queryFn: () => fetchPhotoTags(photoId),
      })
      opts.onTagsUpdated(photoId, data)
    } catch (err) {
      console.warn('[LightboxModal] loadPhotoTags failed', photoId, err)
    }
  }

  let _tagsDebounceTimer: ReturnType<typeof setTimeout> | null = null

  onBeforeUnmount(() => {
    if (_tagsDebounceTimer !== null) {
      clearTimeout(_tagsDebounceTimer)
      _tagsDebounceTimer = null
    }
  })

  watch(() => opts.photoIndex(), (idx) => {
    editingPhotoTags.value = false
    editingTagIds.value = []
    if (_tagsDebounceTimer !== null) clearTimeout(_tagsDebounceTimer)
    if (idx !== null && opts.photos()[idx]) {
      const photoId = opts.photos()[idx].id
      _tagsDebounceTimer = setTimeout(() => {
        loadPhotoTags(photoId)
        _tagsDebounceTimer = null
      }, 200)
    }
  })

  return { editingPhotoTags, editingTagIds, savingTags, currentPhotoTags, tagOptions, startEditTags, savePhotoTags }
}
