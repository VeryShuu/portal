import { isRef } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetchMyShares = vi.fn()
const mockFetchRecentPhotos = vi.fn()
const mockRevokePhotoShare = vi.fn()
const mockRevokeFolderShare = vi.fn()

vi.mock('../../src/api/photos', () => ({
  fetchMyShares: mockFetchMyShares,
  fetchRecentPhotos: mockFetchRecentPhotos,
  revokePhotoShare: mockRevokePhotoShare,
  revokeFolderShare: mockRevokeFolderShare,
}))

const _capturedQueries: any[] = []
const _capturedMutations: any[] = []
const mockInvalidate = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    _capturedQueries.push(opts)
    return { data: { value: undefined }, isLoading: { value: false } }
  }),
  useMutation: vi.fn((opts: any) => {
    _capturedMutations.push(opts)
    return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: { value: false } }
  }),
  useQueryClient: vi.fn(() => ({ invalidateQueries: mockInvalidate })),
}))

function resolveKey(k: unknown): unknown {
  if (isRef(k)) return resolveKey(k.value)
  return k
}

describe('src/queries/photos', () => {
  beforeEach(() => {
    _capturedQueries.length = 0
    _capturedMutations.length = 0
    vi.clearAllMocks()
  })

  describe('useMySharesQuery', () => {
    it('registers a query', async () => {
      const { useMySharesQuery } = await import('../../src/queries/photos')
      useMySharesQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchMyShares', async () => {
      const { useMySharesQuery } = await import('../../src/queries/photos')
      useMySharesQuery()
      mockFetchMyShares.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchMyShares).toHaveBeenCalled()
    })

    it('queryKey contains photos namespace', async () => {
      const { useMySharesQuery } = await import('../../src/queries/photos')
      useMySharesQuery()
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('photos')
    })
  })

  describe('useRecentPhotosQuery', () => {
    it('registers a query', async () => {
      const { useRecentPhotosQuery } = await import('../../src/queries/photos')
      useRecentPhotosQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchRecentPhotos with default limit 8', async () => {
      const { useRecentPhotosQuery } = await import('../../src/queries/photos')
      useRecentPhotosQuery()
      mockFetchRecentPhotos.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchRecentPhotos).toHaveBeenCalledWith(8)
    })

    it('queryFn calls fetchRecentPhotos with custom limit', async () => {
      const { useRecentPhotosQuery } = await import('../../src/queries/photos')
      useRecentPhotosQuery(20)
      mockFetchRecentPhotos.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchRecentPhotos).toHaveBeenCalledWith(20)
    })

    it('queryKey contains recent', async () => {
      const { useRecentPhotosQuery } = await import('../../src/queries/photos')
      useRecentPhotosQuery()
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('recent')
    })
  })

  describe('useRevokePhotoShareMutation', () => {
    it('registers a mutation', async () => {
      const { useRevokePhotoShareMutation } = await import('../../src/queries/photos')
      useRevokePhotoShareMutation()
      expect(_capturedMutations).toHaveLength(1)
    })

    it('mutationFn calls revokePhotoShare with tokenId', async () => {
      const { useRevokePhotoShareMutation } = await import('../../src/queries/photos')
      useRevokePhotoShareMutation()
      mockRevokePhotoShare.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn('token-1')
      expect(mockRevokePhotoShare).toHaveBeenCalledWith('token-1')
    })

    it('onSuccess invalidates photos shares query', async () => {
      const { useRevokePhotoShareMutation } = await import('../../src/queries/photos')
      useRevokePhotoShareMutation()
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: expect.anything() }),
      )
    })
  })

  describe('useRevokeFolderShareMutation', () => {
    it('registers a mutation', async () => {
      const { useRevokeFolderShareMutation } = await import('../../src/queries/photos')
      useRevokeFolderShareMutation()
      expect(_capturedMutations).toHaveLength(1)
    })

    it('mutationFn calls revokeFolderShare with tokenId', async () => {
      const { useRevokeFolderShareMutation } = await import('../../src/queries/photos')
      useRevokeFolderShareMutation()
      mockRevokeFolderShare.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn('folder-token-99')
      expect(mockRevokeFolderShare).toHaveBeenCalledWith('folder-token-99')
    })

    it('onSuccess invalidates photos shares query', async () => {
      const { useRevokeFolderShareMutation } = await import('../../src/queries/photos')
      useRevokeFolderShareMutation()
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })
})
