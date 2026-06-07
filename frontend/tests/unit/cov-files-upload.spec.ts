import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'

const mockMessage = {
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}

const mockApi = vi.fn()
const mockApiUpload = vi.fn()
const mockExtractDroppedFiles = vi.fn()

const mockStore = {
  canUpload: true,
}

vi.mock('../../src/api/index', () => ({
  api: mockApi,
  apiUpload: mockApiUpload,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, p?: Record<string, unknown>) => `${k}${p ? JSON.stringify(p) : ''}`,
  }),
}))

vi.mock('naive-ui', () => ({
  useMessage: () => mockMessage,
}))

vi.mock('../../src/composables/useFilesData', () => ({
  useFilesData: () => mockStore,
}))

vi.mock('../../src/utils/extractDroppedFiles', () => ({
  extractDroppedFiles: mockExtractDroppedFiles,
}))

type UploadApi = Awaited<ReturnType<typeof setupHost>>['api']

async function setupHost(initialFolderId: string | null = 'folder-1') {
  const folderId = ref<string | null>(initialFolderId)
  const onUploaded = vi.fn(async () => {})
  let api: any = null

  const { useFilesUpload } = await import('../../src/composables/useFilesUpload')

  const Host = defineComponent({
    setup() {
      api = useFilesUpload(folderId, onUploaded)
      return () => h('div')
    },
  })

  mount(Host)

  return {
    api: api as UploadApi,
    folderId,
    onUploaded,
  }
}

function makeInputEvent(files: File[] | null) {
  const input = document.createElement('input')
  const fileList = files
    ? (Object.assign(files, { item: (i: number) => files[i] }) as unknown as FileList)
    : null
  Object.defineProperty(input, 'files', { value: fileList, configurable: true })
  input.value = 'filled'
  return { target: input } as unknown as Event
}

describe('useFilesUpload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStore.canUpload = true
  })

  it('triggerUpload clicks hidden file input', async () => {
    const { api } = await setupHost()
    const click = vi.fn()
    api.fileInputRef.value = { click } as unknown as HTMLInputElement

    api.triggerUpload()

    expect(click).toHaveBeenCalledTimes(1)
  })

  it('handleFileInput returns early without files or folder', async () => {
    const { api, folderId } = await setupHost()

    await api.handleFileInput(makeInputEvent(null))
    expect(mockApiUpload).not.toHaveBeenCalled()

    folderId.value = null
    await api.handleFileInput(makeInputEvent([new File(['a'], 'a.txt')]))
    expect(mockApiUpload).not.toHaveBeenCalled()
  })

  it('handleFileInput resets input and uploads files', async () => {
    const { api } = await setupHost('folder-z')
    mockApiUpload.mockResolvedValueOnce({
      uploaded: [{ name: 'a.txt', nc_path: '/a.txt', size_bytes: 1, success: true, error: null }],
      failed: [],
    })

    const event = makeInputEvent([new File(['a'], 'a.txt')])
    const input = event.target as HTMLInputElement

    await api.handleFileInput(event)

    expect(input.value).toBe('')
    expect(mockApiUpload).toHaveBeenCalledTimes(1)
    expect(mockMessage.success).toHaveBeenCalledTimes(1)
  })

  it('runUpload returns early for guards', async () => {
    const { api, folderId } = await setupHost()

    await api.runUpload([])
    expect(mockApiUpload).not.toHaveBeenCalled()

    folderId.value = null
    await api.runUpload([new File(['x'], 'x.txt')])
    expect(mockApiUpload).not.toHaveBeenCalled()
  })

  it('runUpload handles success, multiple failures and unknown error details', async () => {
    const { api, onUploaded } = await setupHost('folder-ok')
    mockApiUpload.mockResolvedValueOnce({
      uploaded: [{ name: 'ok.txt', nc_path: '/ok.txt', size_bytes: 1, success: true, error: null }],
      failed: [
        { name: 'bad-1.txt', nc_path: '/bad-1.txt', size_bytes: 2, success: false, error: 'quota' },
        { name: 'bad-2.txt', nc_path: '/bad-2.txt', size_bytes: 2, success: false, error: null },
      ],
    })

    await api.runUpload([
      new File(['ok'], 'ok.txt'),
      new File(['bad1'], 'bad-1.txt'),
      new File(['bad2'], 'bad-2.txt'),
    ])

    expect(api.uploadProgress.value).toEqual({ done: 1, total: 3, failed: 2 })
    expect(mockMessage.success).toHaveBeenCalledTimes(1)
    expect(mockMessage.warning).toHaveBeenCalledTimes(3)
    expect(onUploaded).toHaveBeenCalledTimes(1)
    expect(api.uploading.value).toBe(false)
  })

  it('runUpload handles catch branch', async () => {
    const { api } = await setupHost('folder-fail')
    mockApiUpload.mockRejectedValueOnce(new Error('boom'))

    await api.runUpload([new File(['x'], 'x.txt')])

    expect(mockMessage.error).toHaveBeenCalledTimes(1)
    expect(api.uploading.value).toBe(false)
  })

  it('onMainDragEnter guards and increments depth for file drags', async () => {
    const { api, folderId } = await setupHost('folder-1')

    const validEvent = {
      dataTransfer: { types: ['Files'] },
    } as unknown as DragEvent

    mockStore.canUpload = false
    api.onMainDragEnter(validEvent)
    expect(api.dragDepth.value).toBe(0)

    mockStore.canUpload = true
    folderId.value = null
    api.onMainDragEnter(validEvent)
    expect(api.dragDepth.value).toBe(0)

    folderId.value = 'folder-1'
    api.onMainDragEnter({ dataTransfer: { types: ['text/plain'] } } as unknown as DragEvent)
    expect(api.dragDepth.value).toBe(0)

    api.onMainDragEnter(validEvent)
    expect(api.dragDepth.value).toBe(1)
  })

  it('onMainDragOver sets dropEffect and onMainDragLeave decrements depth', async () => {
    const { api } = await setupHost()
    const dt = { dropEffect: 'none' } as DataTransfer

    api.onMainDragOver({ dataTransfer: dt } as unknown as DragEvent)
    expect(dt.dropEffect).toBe('copy')

    api.dragDepth.value = 2
    api.onMainDragLeave({} as DragEvent)
    expect(api.dragDepth.value).toBe(1)

    api.dragDepth.value = 0
    api.onMainDragLeave({} as DragEvent)
    expect(api.dragDepth.value).toBe(0)
  })

  it('onMainDrop handles guards, folders info, empty files and upload flow', async () => {
    const { api, folderId } = await setupHost('folder-drop')

    api.dragDepth.value = 3
    await api.onMainDrop({ dataTransfer: null } as unknown as DragEvent)
    expect(api.dragDepth.value).toBe(0)

    mockStore.canUpload = false
    await api.onMainDrop({ dataTransfer: {} as DataTransfer } as unknown as DragEvent)
    expect(mockExtractDroppedFiles).not.toHaveBeenCalled()

    mockStore.canUpload = true
    folderId.value = null
    await api.onMainDrop({ dataTransfer: {} as DataTransfer } as unknown as DragEvent)
    expect(mockExtractDroppedFiles).not.toHaveBeenCalled()

    folderId.value = 'folder-drop'
    mockExtractDroppedFiles.mockResolvedValueOnce({ files: [], hadFolders: true })
    await api.onMainDrop({ dataTransfer: {} as DataTransfer } as unknown as DragEvent)
    expect(mockMessage.info).toHaveBeenCalledTimes(1)
    expect(mockApiUpload).not.toHaveBeenCalled()

    mockExtractDroppedFiles.mockResolvedValueOnce({
      files: [new File(['a'], 'a.txt')],
      hadFolders: false,
    })
    mockApiUpload.mockResolvedValueOnce({ uploaded: [], failed: [] })

    await api.onMainDrop({ dataTransfer: {} as DataTransfer } as unknown as DragEvent)

    expect(mockApiUpload).toHaveBeenCalledTimes(1)
  })
})
