import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import type { Photo } from '../../src/api/photos'

const mockCreateShareLink = vi.fn()
const mockCreateFolderShareLink = vi.fn()

const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('naive-ui', () => ({
  useMessage: () => ({
    success: mockMessageSuccess,
    error: mockMessageError,
    warning: vi.fn(),
  }),
}))

vi.mock('../../src/api/photos', () => ({
  createShareLink: (...args: unknown[]) => mockCreateShareLink(...args),
  createFolderShareLink: (...args: unknown[]) => mockCreateFolderShareLink(...args),
}))

vi.mock('@/utils/photoShareUrls', () => ({
  buildPhotoShareUrl: (token: string) => `photo-url:${token}`,
  buildFolderShareUrl: (token: string) => `folder-url:${token}`,
}))

vi.mock('../../src/api/index', () => ({ api: vi.fn() }))

import { useLightboxShare } from '../../src/composables/useLightboxShare'

type ShareApi = ReturnType<typeof useLightboxShare>

async function setupHost(params?: {
  photo?: Photo | null
  folderId?: string | null
}): Promise<{
  api: ShareApi
  router: Router
  currentPhoto: Ref<Photo | null>
  selectedFolderId: Ref<string | null>
}> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()

  const currentPhoto = ref<Photo | null>(params?.photo ?? null)
  const selectedFolderId = ref<string | null>(params?.folderId ?? null)

  let api: ShareApi | null = null
  const Host = defineComponent({
    setup() {
      api = useLightboxShare({
        currentPhoto: () => currentPhoto.value,
        selectedFolderId: () => selectedFolderId.value,
      })
      return () => h('div')
    },
  })

  mount(Host, { global: { plugins: [router] } })
  return {
    api: api as unknown as ShareApi,
    router,
    currentPhoto,
    selectedFolderId,
  }
}

function makePhoto(id = 'p1'): Photo {
  return {
    id,
    folder_id: 'f1',
    owner_id: 'u1',
    original_name: 'x.jpg',
    stored_name: 'x.jpg',
    mime_type: 'image/jpeg',
    size_bytes: 100,
    width: 10,
    height: 10,
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

describe('cov-media useLightboxShare', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('computes expiry options and opens modals with reset defaults', async () => {
    const { api } = await setupHost()

    expect(api.expiryOptions.value).toHaveLength(5)
    expect(api.expiryOptions.value.map((o) => o.label)).toContain('photos.lightbox.expires7d')

    api.shareUrl.value = 'old'
    api.shareExpiresInDays.value = 30
    api.openShareModal()
    expect(api.shareModalOpen.value).toBe(true)
    expect(api.shareUrl.value).toBe('')
    expect(api.shareExpiresInDays.value).toBe(7)

    api.folderShareUrl.value = 'old2'
    api.folderShareExpiresInDays.value = 90
    api.openFolderShareModal()
    expect(api.folderShareModalOpen.value).toBe(true)
    expect(api.folderShareUrl.value).toBe('')
    expect(api.folderShareExpiresInDays.value).toBe(7)
  })

  it('generateShareLink handles no-photo guard, success and error', async () => {
    const { api, currentPhoto } = await setupHost({ photo: null })

    await api.generateShareLink()
    expect(mockCreateShareLink).not.toHaveBeenCalled()

    currentPhoto.value = makePhoto('photo-1')
    api.shareExpiresInDays.value = 30

    mockCreateShareLink.mockResolvedValueOnce({ token: 'abc' })
    await api.generateShareLink()

    expect(mockCreateShareLink).toHaveBeenCalledWith('photo-1', 30)
    expect(api.shareUrl.value).toBe('photo-url:abc')
    expect(mockMessageSuccess).toHaveBeenCalledWith('photos.lightbox.shareLinkCreated')
    expect(api.creatingShare.value).toBe(false)

    mockCreateShareLink.mockRejectedValueOnce(new Error('x'))
    await api.generateShareLink()

    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
    expect(api.creatingShare.value).toBe(false)
  })

  it('copyShareUrl covers secure clipboard success/failure', async () => {
    const { api } = await setupHost()

    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: true,
    })

    api.shareUrl.value = 'https://x'
    await api.copyShareUrl()

    expect(writeText).toHaveBeenCalledWith('https://x')
    expect(mockMessageSuccess).toHaveBeenCalledWith('photos.lightbox.copied')

    writeText.mockRejectedValueOnce(new Error('no'))
    await api.copyShareUrl()
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('copyShareUrl fallback uses execCommand branch', async () => {
    const { api } = await setupHost()

    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: undefined,
    })
    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: false,
    })

    const execSpy = vi.fn()
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: execSpy,
    })
    execSpy.mockReturnValueOnce(true)

    api.shareUrl.value = 'fallback://ok'
    await api.copyShareUrl()
    expect(mockMessageSuccess).toHaveBeenCalledWith('photos.lightbox.copied')

    execSpy.mockReturnValueOnce(false)
    await api.copyShareUrl()
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('generateFolderShareLink handles guard, success and error', async () => {
    const { api, selectedFolderId } = await setupHost({ folderId: null })

    await api.generateFolderShareLink()
    expect(mockCreateFolderShareLink).not.toHaveBeenCalled()

    selectedFolderId.value = 'folder-5'
    api.folderShareExpiresInDays.value = 1

    mockCreateFolderShareLink.mockResolvedValueOnce({ token: 'f-token' })
    await api.generateFolderShareLink()

    expect(mockCreateFolderShareLink).toHaveBeenCalledWith('folder-5', 1)
    expect(api.folderShareUrl.value).toBe('folder-url:f-token')
    expect(mockMessageSuccess).toHaveBeenCalledWith('photos.lightbox.shareLinkCreated')
    expect(api.creatingFolderShare.value).toBe(false)

    mockCreateFolderShareLink.mockRejectedValueOnce(new Error('x'))
    await api.generateFolderShareLink()
    expect(mockMessageError).toHaveBeenCalledWith('errors.generic')
  })

  it('copyFolderShareUrl and copyInPortalLink cover URL composition branches', async () => {
    const { api, currentPhoto, selectedFolderId } = await setupHost({
      photo: makePhoto('p77'),
      folderId: 'fold-1',
    })

    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: true,
    })

    api.folderShareUrl.value = 'folder://share'
    await api.copyFolderShareUrl()
    expect(writeText).toHaveBeenCalledWith('folder://share')

    await api.copyInPortalLink()
    expect(writeText).toHaveBeenLastCalledWith(`${window.location.origin}/photos?folder=fold-1&photo=p77`)

    selectedFolderId.value = null
    await api.copyInPortalLink()
    expect(writeText).toHaveBeenLastCalledWith(`${window.location.origin}/photos?photo=p77`)

    currentPhoto.value = null
    await api.copyInPortalLink()
    expect(writeText).toHaveBeenCalledTimes(3)
  })
})
