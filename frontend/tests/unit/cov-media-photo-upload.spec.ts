import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

const mockUploadPhotosBatchXhr = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const mockMessageSuccess = vi.fn()
const mockMessageWarning = vi.fn()
const mockMessageError = vi.fn()

vi.mock('naive-ui', () => ({
  useMessage: () => ({
    success: mockMessageSuccess,
    warning: mockMessageWarning,
    error: mockMessageError,
  }),
}))

vi.mock('@/api/photos', () => ({
  uploadPhotosBatchXhr: (...args: unknown[]) => mockUploadPhotosBatchXhr(...args),
  UploadResult: {},
}))

vi.mock('../../src/api/index', () => ({ api: vi.fn() }))

import { usePhotoUpload } from '../../src/composables/usePhotoUpload'

type UploadApi = ReturnType<typeof usePhotoUpload>

async function setupHost(folderId: string | null = 'folder-1'): Promise<{
  api: UploadApi
  router: Router
  selectedFolderId: Ref<string | null>
  onSuccess: ReturnType<typeof vi.fn>
}> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()

  const selectedFolderId = ref<string | null>(folderId)
  const onSuccess = vi.fn().mockResolvedValue(undefined)

  let api: UploadApi | null = null
  const Host = defineComponent({
    setup() {
      api = usePhotoUpload(selectedFolderId, onSuccess)
      return () => h('div')
    },
  })

  mount(Host, { global: { plugins: [router] } })

  return {
    api: api as unknown as UploadApi,
    router,
    selectedFolderId,
    onSuccess,
  }
}

function makeImage(name: string, size = 10, type = 'image/jpeg') {
  const data = new Uint8Array(size)
  return new File([data], name, { type })
}

describe('cov-media usePhotoUpload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUploadPhotosBatchXhr.mockReset()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns early when folder is not selected', async () => {
    const { api, onSuccess } = await setupHost(null)

    await api.runUploadQueue([makeImage('a.jpg')])

    expect(mockUploadPhotosBatchXhr).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
    expect(api.uploadQueue.value).toEqual([])
  })

  it('returns early when already uploading', async () => {
    const { api, onSuccess } = await setupHost('folder-1')
    api.uploadQueue.value = [{ file: makeImage('busy.jpg'), status: 'uploading', progress: 20 }]

    await api.runUploadQueue([makeImage('a.jpg')])

    expect(mockUploadPhotosBatchXhr).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('uploads successfully and sets done states plus success message', async () => {
    const { api, onSuccess } = await setupHost('folder-1')
    const f1 = makeImage('a.jpg')
    const f2 = makeImage('b.jpg')

    mockUploadPhotosBatchXhr.mockImplementationOnce(async (_folder, batch, onProgress) => {
      onProgress(55)
      onProgress(100)
      return {
        items: (batch as File[]).map((f) => ({
          original_name: f.name,
          ok: true,
          photo_id: `${f.name}-id`,
        })),
      }
    })

    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:ok')
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)

    await api.runUploadQueue([f1, f2])

    expect(mockUploadPhotosBatchXhr).toHaveBeenCalledTimes(1)
    expect(api.uploadQueue.value.map((i) => i.status)).toEqual(['done', 'done'])
    expect(api.uploadDoneCount.value).toBe(2)
    expect(api.totalProgress.value).toBe(100)
    expect(mockMessageSuccess).toHaveBeenCalledWith('photos.upload.done')
    expect(mockMessageWarning).not.toHaveBeenCalled()
    expect(mockMessageError).not.toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(createObjectURLSpy).toHaveBeenCalledTimes(2)

    api.releaseAllPreviews()
    expect(revokeObjectURLSpy).toHaveBeenCalled()
  })

  it('handles partial success (done + error) with warning message', async () => {
    const { api, onSuccess } = await setupHost('folder-1')
    const f1 = makeImage('a.jpg')
    const f2 = makeImage('b.jpg')

    mockUploadPhotosBatchXhr.mockResolvedValueOnce({
      items: [
        { original_name: 'a.jpg', ok: true, photo_id: 'p1' },
        { original_name: 'b.jpg', ok: false, error: 'boom' },
      ],
    })

    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:ok')

    await api.runUploadQueue([f1, f2])

    expect(api.uploadQueue.value[0].status).toBe('done')
    expect(api.uploadQueue.value[1].status).toBe('error')
    expect(api.uploadQueue.value[1].error).toBe('boom')
    expect(mockMessageWarning).toHaveBeenCalledWith('photos.upload.partialSuccess')
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  it('handles all failed uploads with error message', async () => {
    const { api, onSuccess } = await setupHost('folder-1')

    mockUploadPhotosBatchXhr.mockRejectedValueOnce({ status: 500 })

    await api.runUploadQueue([makeImage('a.jpg')])

    expect(api.uploadQueue.value[0].status).toBe('error')
    expect(api.uploadQueue.value[0].error).toBe('photos.upload.error')
    expect(mockMessageError).toHaveBeenCalledWith('photos.upload.failedAll')
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  it('retries rate-limited upload and eventually succeeds', async () => {
    vi.useFakeTimers()

    const { api, onSuccess } = await setupHost('folder-1')

    mockUploadPhotosBatchXhr
      .mockRejectedValueOnce({ status: 429 })
      .mockResolvedValueOnce({ items: [{ original_name: 'a.jpg', ok: true, photo_id: 'x1' }] })

    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:ok')

    const runPromise = api.runUploadQueue([makeImage('a.jpg')])
    await vi.runAllTimersAsync()
    await runPromise

    expect(mockUploadPhotosBatchXhr).toHaveBeenCalledTimes(2)
    expect(api.uploadQueue.value[0].status).toBe('done')
    expect(mockMessageSuccess).toHaveBeenCalledWith('photos.upload.done')
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  it('marks pending items as aborted when abortUpload is triggered mid-run', async () => {
    const { api, onSuccess } = await setupHost('folder-1')

    mockUploadPhotosBatchXhr.mockImplementationOnce(async (_folderId, _files, _onProgress, signal: AbortSignal) => {
      return await new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject({ name: 'AbortError' }))
      })
    })

    const runPromise = api.runUploadQueue([makeImage('a.jpg'), makeImage('b.jpg')])
    api.abortUpload()
    await runPromise

    expect(api.uploadAborted.value).toBe(true)
    expect(api.uploadQueue.value.every((i) => i.status === 'error')).toBe(true)
    expect(api.uploadQueue.value.some((i) => i.error === 'photos.upload.aborted')).toBe(true)
    expect(mockMessageWarning).toHaveBeenCalledWith('photos.upload.aborted')
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  it('onFilesPicked clears input value and uploads files', async () => {
    const { api } = await setupHost('folder-1')
    mockUploadPhotosBatchXhr.mockResolvedValueOnce({ items: [{ original_name: 'picked.jpg', ok: true }] })

    const input = {
      files: [makeImage('picked.jpg')],
      value: 'x',
    } as unknown as HTMLInputElement

    await api.onFilesPicked({ target: input } as unknown as Event)

    expect(mockUploadPhotosBatchXhr).toHaveBeenCalledTimes(1)
    expect(input.value).toBe('')
  })

  it('onDrop ignores invalid drops and uploads only accepted files', async () => {
    const { api, selectedFolderId } = await setupHost('folder-1')

    mockUploadPhotosBatchXhr.mockResolvedValue({ items: [] })

    const invalid = {
      dataTransfer: { types: ['text/plain'], files: [makeImage('a.jpg')] },
    } as unknown as DragEvent
    api.onDrop(invalid)

    const mixedFiles = [
      makeImage('ok.jpg', 10, 'image/jpeg'),
      new File(['x'], 'ok.heic', { type: '' }),
      new File(['x'], 'bad.txt', { type: 'text/plain' }),
    ]

    const valid = {
      dataTransfer: {
        types: ['Files'],
        files: mixedFiles,
      },
    } as unknown as DragEvent
    api.onDrop(valid)
    await Promise.resolve()

    selectedFolderId.value = null
    api.onDrop(valid)
    await Promise.resolve()

    expect(mockUploadPhotosBatchXhr).toHaveBeenCalledTimes(1)
    expect(mockUploadPhotosBatchXhr.mock.calls[0][1].map((f: File) => f.name)).toEqual(['ok.jpg', 'ok.heic'])
  })

  it('triggerUpload clicks input when present', async () => {
    const { api } = await setupHost('folder-1')
    const click = vi.fn()
    api.fileInputRef.value = { click } as unknown as HTMLInputElement

    api.triggerUpload()

    expect(click).toHaveBeenCalledTimes(1)
  })

  it('copy preview lifecycle via photos:processed event', async () => {
    const { api } = await setupHost('folder-1')

    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:event')
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)

    mockUploadPhotosBatchXhr.mockResolvedValueOnce({
      items: [{ original_name: 'a.jpg', ok: true, photo_id: 'photo-1' }],
    })

    await api.runUploadQueue([makeImage('a.jpg')])
    expect(api.previewUrls.value['photo-1']).toBe('blob:event')

    window.dispatchEvent(new CustomEvent('photos:processed', { detail: { photo_id: 'photo-1' } }))
    expect(api.previewUrls.value['photo-1']).toBeUndefined()
    expect(revokeObjectURLSpy).toHaveBeenCalled()
  })
})
