import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import type { Photo, PhotoTag } from '../../src/api/photos'

const mockFetchPhotoTags = vi.fn()
const mockSetPhotoTags = vi.fn()
const mockEnsureQueryData = vi.fn()
const mockSetQueryData = vi.fn()

const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('naive-ui', () => ({
  useMessage: () => ({ success: mockMessageSuccess, error: mockMessageError, warning: vi.fn() }),
}))

vi.mock('../../src/api/photos', () => ({
  fetchPhotoTags: (...args: unknown[]) => mockFetchPhotoTags(...args),
  setPhotoTags: (...args: unknown[]) => mockSetPhotoTags(...args),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({
    ensureQueryData: (...args: unknown[]) => mockEnsureQueryData(...args),
    setQueryData: (...args: unknown[]) => mockSetQueryData(...args),
  }),
}))

vi.mock('../../src/api/index', () => ({ api: vi.fn() }))

import { useLightboxPhotoTags } from '../../src/composables/useLightboxPhotoTags'

type TagsApi = ReturnType<typeof useLightboxPhotoTags>

type SetupResult = {
  api: TagsApi
  router: Router
  currentPhoto: Ref<Photo | null>
  photoTagsMap: Ref<Record<string, PhotoTag[]>>
  allTags: Ref<PhotoTag[]>
  photoIndex: Ref<number | null>
  photos: Ref<Photo[]>
  onTagsUpdated: ReturnType<typeof vi.fn>
  unmount: () => void
}

function makePhoto(id: string): Photo {
  return {
    id,
    folder_id: 'f',
    owner_id: 'u',
    original_name: `${id}.jpg`,
    stored_name: `${id}.jpg`,
    mime_type: 'image/jpeg',
    size_bytes: 1,
    width: 1,
    height: 1,
    captured_at: null,
    taken_at: null,
    camera_make: null,
    camera_model: null,
    exposure_time: null,
    aperture: null,
    iso: null,
    focal_length: null,
    hash_sha256: null,
    deleted_at: null,
    created_at: '',
    updated_at: '',
    versions: [],
    tags: [],
  }
}

function makeTag(id: string, name = id): PhotoTag {
  return {
    id,
    name,
    color: null,
    usage_count: 0,
    created_at: '',
    updated_at: '',
  }
}

async function setupHost(): Promise<SetupResult> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()

  const currentPhoto = ref<Photo | null>(makePhoto('p1'))
  const photoTagsMap = ref<Record<string, PhotoTag[]>>({ p1: [makeTag('t1', 'tag1')] })
  const allTags = ref<PhotoTag[]>([makeTag('t1', 'tag1'), makeTag('t2', 'tag2')])
  const photoIndex = ref<number | null>(0)
  const photos = ref<Photo[]>([makePhoto('p1'), makePhoto('p2')])
  const onTagsUpdated = vi.fn()

  let api: TagsApi | null = null
  const Host = defineComponent({
    setup() {
      api = useLightboxPhotoTags({
        currentPhoto: () => currentPhoto.value,
        photoTagsMap: () => photoTagsMap.value,
        allTags: () => allTags.value,
        onTagsUpdated,
        photoIndex: () => photoIndex.value,
        photos: () => photos.value,
      })
      return () => h('div')
    },
  })

  const wrapper = mount(Host, { global: { plugins: [router] } })

  return {
    api: api as unknown as TagsApi,
    router,
    currentPhoto,
    photoTagsMap,
    allTags,
    photoIndex,
    photos,
    onTagsUpdated,
    unmount: () => wrapper.unmount(),
  }
}

describe('cov-media useLightboxPhotoTags', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('computes currentPhotoTags and tagOptions; startEditTags fills ids', async () => {
    const { api, currentPhoto } = await setupHost()

    expect(api.currentPhotoTags.value.map((t) => t.id)).toEqual(['t1'])
    expect(api.tagOptions.value).toEqual([
      { label: 'tag1', value: 't1' },
      { label: 'tag2', value: 't2' },
    ])

    api.startEditTags()
    expect(api.editingPhotoTags.value).toBe(true)
    expect(api.editingTagIds.value).toEqual(['t1'])

    currentPhoto.value = null
    expect(api.currentPhotoTags.value).toEqual([])
  })

  it('savePhotoTags returns early without current photo', async () => {
    const { api, currentPhoto } = await setupHost()
    currentPhoto.value = null

    await api.savePhotoTags()

    expect(mockSetPhotoTags).not.toHaveBeenCalled()
    expect(mockSetQueryData).not.toHaveBeenCalled()
  })

  it('savePhotoTags success updates query cache and calls callback', async () => {
    const { api, onTagsUpdated } = await setupHost()
    api.editingTagIds.value = ['t2']

    const updated = [makeTag('t2', 'tag2')]
    mockSetPhotoTags.mockResolvedValueOnce(updated)

    await api.savePhotoTags()

    expect(mockSetPhotoTags).toHaveBeenCalledWith('p1', ['t2'])
    expect(mockSetQueryData).toHaveBeenCalledTimes(1)
    expect(onTagsUpdated).toHaveBeenCalledWith('p1', updated)
    expect(api.editingPhotoTags.value).toBe(false)
    expect(api.savingTags.value).toBe(false)
    expect(mockMessageSuccess).toHaveBeenCalledWith('photos.tags.saved')
  })

  it('savePhotoTags error path sets saving false and shows error', async () => {
    const { api } = await setupHost()
    mockSetPhotoTags.mockRejectedValueOnce(new Error('x'))

    await api.savePhotoTags()

    expect(api.savingTags.value).toBe(false)
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('watch on photoIndex resets editing state and debounced-loads tags when missing', async () => {
    const { api, photoIndex, photoTagsMap, photos, onTagsUpdated } = await setupHost()
    api.editingPhotoTags.value = true
    api.editingTagIds.value = ['x']

    photoTagsMap.value = { p1: [makeTag('t1')] }
    photos.value = [makePhoto('p1'), makePhoto('p2')]

    mockEnsureQueryData.mockResolvedValueOnce([makeTag('t2', 'tag2')])

    photoIndex.value = 1
    await Promise.resolve()

    expect(api.editingPhotoTags.value).toBe(false)
    expect(api.editingTagIds.value).toEqual([])

    await vi.advanceTimersByTimeAsync(210)

    expect(mockEnsureQueryData).toHaveBeenCalledTimes(1)
    expect(mockFetchPhotoTags).not.toHaveBeenCalled()
    expect(onTagsUpdated).toHaveBeenCalledWith('p2', [makeTag('t2', 'tag2')])
  })

  it('watch load skips when tags already cached and handles ensureQueryData rejection', async () => {
    const { photoIndex, photoTagsMap } = await setupHost()

    photoTagsMap.value = { p1: [makeTag('t1')], p2: [makeTag('t2')] }

    photoIndex.value = 1
    await vi.advanceTimersByTimeAsync(210)
    expect(mockEnsureQueryData).not.toHaveBeenCalled()

    photoTagsMap.value = { p1: [makeTag('t1')] }
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    mockEnsureQueryData.mockRejectedValueOnce(new Error('fail'))

    photoIndex.value = 0
    await Promise.resolve()
    photoIndex.value = 1
    await vi.advanceTimersByTimeAsync(210)

    expect(mockEnsureQueryData).toHaveBeenCalledTimes(1)
    expect(warnSpy).toHaveBeenCalled()
  })

  it('onBeforeUnmount clears pending debounce timer', async () => {
    const { photoIndex, unmount } = await setupHost()

    photoIndex.value = 1
    unmount()

    await vi.advanceTimersByTimeAsync(250)
    expect(mockEnsureQueryData).not.toHaveBeenCalled()
  })
})
