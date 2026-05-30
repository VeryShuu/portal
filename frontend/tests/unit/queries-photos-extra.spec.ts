import { isRef, ref } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetchFolderTree = vi.fn()
const mockFetchFolder = vi.fn()
const mockFetchFolderPhotos = vi.fn()
const mockFetchFolderPhotosFiltered = vi.fn()
const mockFetchTags = vi.fn()
const mockFetchPhotoTags = vi.fn()

vi.mock('../../src/api/photos', () => ({
  fetchMyShares: vi.fn(),
  fetchRecentPhotos: vi.fn(),
  revokePhotoShare: vi.fn(),
  revokeFolderShare: vi.fn(),
  fetchFolderTree: mockFetchFolderTree,
  fetchFolder: mockFetchFolder,
  fetchFolderPhotos: mockFetchFolderPhotos,
  fetchFolderPhotosFiltered: mockFetchFolderPhotosFiltered,
  fetchTags: mockFetchTags,
  fetchPhotoTags: mockFetchPhotoTags,
}))

const _capturedQueries: any[] = []

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    _capturedQueries.push(opts)
    return { data: { value: undefined }, isLoading: { value: false } }
  }),
  useMutation: vi.fn((opts: any) => ({ mutate: vi.fn(), mutateAsync: vi.fn() })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
}))

function resolveKey(k: unknown): unknown {
  if (isRef(k)) return resolveKey(k.value)
  return k
}

function resolveEnabled(e: unknown): unknown {
  if (isRef(e)) return e.value
  return e
}

beforeEach(() => {
  _capturedQueries.length = 0
  vi.clearAllMocks()
})

describe('usePhotoFolderTreeQuery', () => {
  it('registers query, queryFn calls fetchFolderTree', async () => {
    const { usePhotoFolderTreeQuery } = await import('../../src/queries/photos')
    usePhotoFolderTreeQuery()
    expect(_capturedQueries).toHaveLength(1)
    mockFetchFolderTree.mockResolvedValueOnce([])
    await _capturedQueries[0].queryFn()
    expect(mockFetchFolderTree).toHaveBeenCalled()
  })
})

describe('usePhotoFolderQuery', () => {
  it('disabled when folderId is null', async () => {
    const { usePhotoFolderQuery } = await import('../../src/queries/photos')
    usePhotoFolderQuery(null)
    expect(resolveEnabled(_capturedQueries[0].enabled)).toBe(false)
  })

  it('enabled when folderId is provided', async () => {
    const { usePhotoFolderQuery } = await import('../../src/queries/photos')
    usePhotoFolderQuery('folder-1')
    expect(resolveEnabled(_capturedQueries[0].enabled)).toBe(true)
  })

  it('queryFn calls fetchFolder with id', async () => {
    const { usePhotoFolderQuery } = await import('../../src/queries/photos')
    usePhotoFolderQuery('folder-42')
    mockFetchFolder.mockResolvedValueOnce({ id: 'folder-42' })
    const result = await _capturedQueries[0].queryFn()
    expect(mockFetchFolder).toHaveBeenCalledWith('folder-42')
    expect(result).toEqual({ id: 'folder-42' })
  })

  it('queryFn throws when folderId is null', async () => {
    const { usePhotoFolderQuery } = await import('../../src/queries/photos')
    const folderId = ref<string | null>(null)
    usePhotoFolderQuery(folderId)
    expect(() => _capturedQueries[0].queryFn()).toThrow('No folder ID provided')
  })

  it('queryKey contains folder id', async () => {
    const { usePhotoFolderQuery } = await import('../../src/queries/photos')
    usePhotoFolderQuery('folder-x')
    const key = resolveKey(_capturedQueries[0].queryKey)
    expect(JSON.stringify(key)).toContain('folder-x')
  })
})

describe('usePhotoFolderPhotosQuery', () => {
  it('disabled when folderId is null', async () => {
    const { usePhotoFolderPhotosQuery } = await import('../../src/queries/photos')
    usePhotoFolderPhotosQuery(null, {} as any)
    expect(resolveEnabled(_capturedQueries[0].enabled)).toBe(false)
  })

  it('queryFn calls fetchFolderPhotos when no tag_id', async () => {
    const { usePhotoFolderPhotosQuery } = await import('../../src/queries/photos')
    const params = { limit: 20 } as any
    usePhotoFolderPhotosQuery('f1', params)
    mockFetchFolderPhotos.mockResolvedValueOnce({ items: [] })
    await _capturedQueries[0].queryFn()
    expect(mockFetchFolderPhotos).toHaveBeenCalledWith('f1', params)
    expect(mockFetchFolderPhotosFiltered).not.toHaveBeenCalled()
  })

  it('queryFn calls fetchFolderPhotosFiltered when tag_id is set', async () => {
    const { usePhotoFolderPhotosQuery } = await import('../../src/queries/photos')
    const params = { limit: 20, tag_id: 'tag-1' } as any
    usePhotoFolderPhotosQuery('f1', params)
    mockFetchFolderPhotosFiltered.mockResolvedValueOnce({ items: [] })
    await _capturedQueries[0].queryFn()
    expect(mockFetchFolderPhotosFiltered).toHaveBeenCalledWith('f1', params)
    expect(mockFetchFolderPhotos).not.toHaveBeenCalled()
  })

  it('queryFn throws when folderId is null', async () => {
    const { usePhotoFolderPhotosQuery } = await import('../../src/queries/photos')
    const folderId = ref<string | null>(null)
    usePhotoFolderPhotosQuery(folderId, {} as any)
    await expect(_capturedQueries[0].queryFn()).rejects.toThrow('No folder ID provided')
  })
})

describe('usePhotoAllTagsQuery', () => {
  it('queryFn unwraps items from fetchTags response', async () => {
    const { usePhotoAllTagsQuery } = await import('../../src/queries/photos')
    usePhotoAllTagsQuery()
    mockFetchTags.mockResolvedValueOnce({ items: [{ id: 't1', name: 'sunset' }] })
    const result = await _capturedQueries[0].queryFn()
    expect(result).toEqual([{ id: 't1', name: 'sunset' }])
  })
})

describe('usePhotoTagsQuery', () => {
  it('disabled when photoId is null', async () => {
    const { usePhotoTagsQuery } = await import('../../src/queries/photos')
    usePhotoTagsQuery(null)
    expect(resolveEnabled(_capturedQueries[0].enabled)).toBe(false)
  })

  it('queryFn calls fetchPhotoTags with id', async () => {
    const { usePhotoTagsQuery } = await import('../../src/queries/photos')
    usePhotoTagsQuery('photo-1')
    mockFetchPhotoTags.mockResolvedValueOnce([])
    await _capturedQueries[0].queryFn()
    expect(mockFetchPhotoTags).toHaveBeenCalledWith('photo-1')
  })

  it('queryFn throws when photoId is null', async () => {
    const { usePhotoTagsQuery } = await import('../../src/queries/photos')
    const id = ref<string | null>(null)
    usePhotoTagsQuery(id)
    expect(() => _capturedQueries[0].queryFn()).toThrow('No photo ID provided')
  })
})
