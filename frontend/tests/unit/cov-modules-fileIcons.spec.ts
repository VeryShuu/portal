import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mockApi = vi.fn()
const mockApiUpload = vi.fn()

vi.mock('../../src/api/index', () => ({ api: mockApi, apiUpload: mockApiUpload }))
vi.mock('../../src/api', () => ({ api: mockApi, apiUpload: mockApiUpload }))
vi.mock('../../src/assets/file-icons/microsoft-word.svg?url', () => ({ default: '/word.svg' }))
vi.mock('../../src/assets/file-icons/microsoft-excel.svg?url', () => ({ default: '/excel.svg' }))

describe('useFileIconsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('iconUrlFor resolves custom, bundled and unknown extensions', async () => {
    const { useFileIconsStore } = await import('../../src/stores/fileIcons')
    const store = useFileIconsStore()

    store.customByExt = { pdf: '/api/v1/files/icons/pdf?v=1' }
    expect(store.iconUrlFor('PDF')).toBe('/api/v1/files/icons/pdf?v=1')
    expect(store.iconUrlFor('docx')).toBe('/word.svg')
    expect(store.iconUrlFor('xlsx')).toBe('/excel.svg')
    expect(store.iconUrlFor('unknown')).toBeNull()
  })

  it('load success sets entries and loaded=true; second load returns early', async () => {
    const { useFileIconsStore } = await import('../../src/stores/fileIcons')
    const store = useFileIconsStore()

    mockApi.mockResolvedValueOnce({
      items: [
        { extension: 'pdf', url: 'ignored', updated_at: 10 },
        { extension: 'ppt', url: 'ignored', updated_at: 20 },
      ],
    })

    await store.load()
    expect(store.loaded).toBe(true)
    expect(store.customByExt.pdf).toBe('/api/v1/files/icons/pdf?v=10')
    expect(store.versions.ppt).toBe(20)

    await store.load()
    expect(mockApi).toHaveBeenCalledTimes(1)
  })

  it('load shares inflight promise and catches errors', async () => {
    const { useFileIconsStore } = await import('../../src/stores/fileIcons')
    const store = useFileIconsStore()

    let resolveApi: ((v: any) => void) | null = null
    mockApi.mockImplementationOnce(() => new Promise((resolve) => { resolveApi = resolve }))

    const p1 = store.load()
    const p2 = store.load()
    expect(mockApi).toHaveBeenCalledTimes(1)
    resolveApi?.({ items: [{ extension: 'svg', url: 'ignored', updated_at: 33 }] })
    await Promise.all([p1, p2])
    expect(store.customByExt.svg).toBe('/api/v1/files/icons/svg?v=33')

    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    store.loaded = false
    mockApi.mockRejectedValueOnce(new Error('network'))
    await expect(store.load()).resolves.toBeUndefined()
    expect(errSpy).toHaveBeenCalled()
    expect(store.loaded).toBe(false)
    errSpy.mockRestore()
  })

  it('refresh forces reload', async () => {
    const { useFileIconsStore } = await import('../../src/stores/fileIcons')
    const store = useFileIconsStore()

    store.loaded = true
    mockApi.mockResolvedValueOnce({ items: [{ extension: 'txt', url: 'ignored', updated_at: 5 }] })
    await store.refresh()
    expect(store.loaded).toBe(true)
    expect(store.customByExt.txt).toBe('/api/v1/files/icons/txt?v=5')
  })

  it('upload normalizes ext and updates maps', async () => {
    const { useFileIconsStore } = await import('../../src/stores/fileIcons')
    const store = useFileIconsStore()

    const file = new File(['hello'], 'icon.svg', { type: 'image/svg+xml' })
    mockApiUpload.mockResolvedValueOnce({ extension: 'pdf', url: 'ignored', updated_at: 77 })

    const entry = await store.upload(' .PDF ', file)
    expect(entry.extension).toBe('pdf')
    expect(mockApiUpload).toHaveBeenCalledWith('/admin/files/icons/pdf', expect.any(FormData))
    expect(store.customByExt.pdf).toBe('/api/v1/files/icons/pdf?v=77')
    expect(store.versions.pdf).toBe(77)
  })

  it('remove normalizes ext and removes existing entries', async () => {
    const { useFileIconsStore } = await import('../../src/stores/fileIcons')
    const store = useFileIconsStore()

    store.customByExt = { pdf: '/api/v1/files/icons/pdf?v=1', doc: '/word.svg' }
    store.versions = { pdf: 1, doc: 1 }

    mockApi.mockResolvedValueOnce({})
    await store.remove(' .PDF ')
    expect(mockApi).toHaveBeenCalledWith('/admin/files/icons/pdf', { method: 'DELETE' })
    expect(store.customByExt.pdf).toBeUndefined()
    expect(store.versions.pdf).toBeUndefined()
    expect(store.customByExt.doc).toBe('/word.svg')
  })
})
