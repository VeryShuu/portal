import { isRef } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetchNewsList = vi.fn()
const mockFetchNewsById = vi.fn()
const mockFetchNewsCategories = vi.fn()
const mockFetchNewsUploadLimits = vi.fn()
const mockFetchGallery = vi.fn()
const mockFetchAttachments = vi.fn()
const mockCreateNews = vi.fn()
const mockUpdateNews = vi.fn()
const mockDeleteNews = vi.fn()
const mockUploadGalleryImage = vi.fn()
const mockDeleteGalleryImage = vi.fn()
const mockReorderGallery = vi.fn()
const mockUploadAttachment = vi.fn()
const mockDeleteAttachment = vi.fn()
const mockFetchNewsPoll = vi.fn()
const mockCreateNewsPoll = vi.fn()
const mockUpdateNewsPoll = vi.fn()
const mockDeleteNewsPoll = vi.fn()
const mockCloseNewsPoll = vi.fn()
const mockReopenNewsPoll = vi.fn()
const mockVoteNewsPoll = vi.fn()
const mockRevokeNewsPollVote = vi.fn()

vi.mock('../../src/api/news', () => ({
  fetchNewsList: mockFetchNewsList,
  fetchNewsById: mockFetchNewsById,
  fetchNewsCategories: mockFetchNewsCategories,
  fetchNewsUploadLimits: mockFetchNewsUploadLimits,
  fetchGallery: mockFetchGallery,
  fetchAttachments: mockFetchAttachments,
  createNews: mockCreateNews,
  updateNews: mockUpdateNews,
  deleteNews: mockDeleteNews,
  uploadGalleryImage: mockUploadGalleryImage,
  deleteGalleryImage: mockDeleteGalleryImage,
  reorderGallery: mockReorderGallery,
  uploadAttachment: mockUploadAttachment,
  deleteAttachment: mockDeleteAttachment,
  fetchNewsPoll: mockFetchNewsPoll,
  createNewsPoll: mockCreateNewsPoll,
  updateNewsPoll: mockUpdateNewsPoll,
  deleteNewsPoll: mockDeleteNewsPoll,
  closeNewsPoll: mockCloseNewsPoll,
  reopenNewsPoll: mockReopenNewsPoll,
  voteNewsPoll: mockVoteNewsPoll,
  revokeNewsPollVote: mockRevokeNewsPollVote,
}))

const _capturedQueries: any[] = []
const _capturedMutations: any[] = []
const mockInvalidate = vi.fn()
const mockRemove = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    _capturedQueries.push(opts)
    return { data: { value: undefined }, isLoading: { value: false } }
  }),
  useMutation: vi.fn((opts: any) => {
    _capturedMutations.push(opts)
    return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: { value: false } }
  }),
  useQueryClient: vi.fn(() => ({
    invalidateQueries: mockInvalidate,
    removeQueries: mockRemove,
  })),
}))

function resolveKey(k: unknown): unknown {
  if (isRef(k)) return resolveKey(k.value)
  return k
}

const VALID_UUID = '550e8400-e29b-41d4-a716-446655440000'

describe('src/queries/news', () => {
  beforeEach(() => {
    _capturedQueries.length = 0
    _capturedMutations.length = 0
    vi.clearAllMocks()
  })

  describe('useNewsListQuery', () => {
    it('registers a query', async () => {
      const { useNewsListQuery } = await import('../../src/queries/news')
      useNewsListQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchNewsList with params', async () => {
      const { useNewsListQuery } = await import('../../src/queries/news')
      useNewsListQuery({ status: 'published', page: 1 })
      mockFetchNewsList.mockResolvedValueOnce({ items: [], total: 0 })
      await _capturedQueries[0].queryFn()
      expect(mockFetchNewsList).toHaveBeenCalledWith({ status: 'published', page: 1 })
    })

    it('queryKey contains news namespace', async () => {
      const { useNewsListQuery } = await import('../../src/queries/news')
      useNewsListQuery()
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('news')
    })
  })

  describe('useNewsDetailQuery', () => {
    it('registers a query', async () => {
      const { useNewsDetailQuery } = await import('../../src/queries/news')
      useNewsDetailQuery(VALID_UUID)
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchNewsById for valid uuid', async () => {
      const { useNewsDetailQuery } = await import('../../src/queries/news')
      useNewsDetailQuery(VALID_UUID)
      mockFetchNewsById.mockResolvedValueOnce({ id: VALID_UUID })
      await _capturedQueries[0].queryFn()
      expect(mockFetchNewsById).toHaveBeenCalledWith(VALID_UUID)
    })

    it('queryFn throws for invalid id', async () => {
      const { useNewsDetailQuery } = await import('../../src/queries/news')
      useNewsDetailQuery('not-a-uuid')
      expect(() => _capturedQueries[0].queryFn()).toThrow('invalid news id')
    })

    it('enabled is false when id is not a valid uuid', async () => {
      const { useNewsDetailQuery } = await import('../../src/queries/news')
      useNewsDetailQuery('bad-id')
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(false)
    })

    it('enabled is true for valid uuid', async () => {
      const { useNewsDetailQuery } = await import('../../src/queries/news')
      useNewsDetailQuery(VALID_UUID)
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(true)
    })
  })

  describe('useNewsGalleryQuery', () => {
    it('registers a query', async () => {
      const { useNewsGalleryQuery } = await import('../../src/queries/news')
      useNewsGalleryQuery(VALID_UUID)
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchGallery for valid newsId', async () => {
      const { useNewsGalleryQuery } = await import('../../src/queries/news')
      useNewsGalleryQuery(VALID_UUID)
      mockFetchGallery.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchGallery).toHaveBeenCalledWith(VALID_UUID)
    })

    it('queryFn returns empty array for invalid newsId', async () => {
      const { useNewsGalleryQuery } = await import('../../src/queries/news')
      useNewsGalleryQuery('bad')
      const result = await _capturedQueries[0].queryFn()
      expect(result).toEqual([])
      expect(mockFetchGallery).not.toHaveBeenCalled()
    })

    it('queryFn swallows errors and returns empty array', async () => {
      const { useNewsGalleryQuery } = await import('../../src/queries/news')
      useNewsGalleryQuery(VALID_UUID)
      mockFetchGallery.mockRejectedValueOnce(new Error('network'))
      const result = await _capturedQueries[0].queryFn()
      expect(result).toEqual([])
    })

    it('enabled respects options.enabled=false', async () => {
      const { useNewsGalleryQuery } = await import('../../src/queries/news')
      useNewsGalleryQuery(VALID_UUID, { enabled: false })
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(false)
    })
  })

  describe('useNewsAttachmentsQuery', () => {
    it('queryFn calls fetchAttachments for valid newsId', async () => {
      const { useNewsAttachmentsQuery } = await import('../../src/queries/news')
      useNewsAttachmentsQuery(VALID_UUID)
      mockFetchAttachments.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchAttachments).toHaveBeenCalledWith(VALID_UUID)
    })

    it('queryFn returns empty array for invalid newsId', async () => {
      const { useNewsAttachmentsQuery } = await import('../../src/queries/news')
      useNewsAttachmentsQuery('bad')
      const result = await _capturedQueries[0].queryFn()
      expect(result).toEqual([])
    })

    it('queryFn swallows errors', async () => {
      const { useNewsAttachmentsQuery } = await import('../../src/queries/news')
      useNewsAttachmentsQuery(VALID_UUID)
      mockFetchAttachments.mockRejectedValueOnce(new Error('err'))
      const result = await _capturedQueries[0].queryFn()
      expect(result).toEqual([])
    })
  })

  describe('useNewsCategoriesQuery', () => {
    it('queryFn calls fetchNewsCategories', async () => {
      const { useNewsCategoriesQuery } = await import('../../src/queries/news')
      useNewsCategoriesQuery()
      mockFetchNewsCategories.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchNewsCategories).toHaveBeenCalled()
    })
  })

  describe('useNewsUploadLimitsQuery', () => {
    it('queryFn calls fetchNewsUploadLimits', async () => {
      const { useNewsUploadLimitsQuery } = await import('../../src/queries/news')
      useNewsUploadLimitsQuery()
      mockFetchNewsUploadLimits.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockFetchNewsUploadLimits).toHaveBeenCalled()
    })
  })

  describe('useCreateNewsMutation', () => {
    it('mutationFn calls createNews', async () => {
      const { useCreateNewsMutation } = await import('../../src/queries/news')
      useCreateNewsMutation()
      mockCreateNews.mockResolvedValueOnce({ id: 'new-news' })
      await _capturedMutations[0].mutationFn({ title: 'Test', status: 'draft' })
      expect(mockCreateNews).toHaveBeenCalledWith({ title: 'Test', status: 'draft' })
    })

    it('onSuccess invalidates news queries', async () => {
      const { useCreateNewsMutation } = await import('../../src/queries/news')
      useCreateNewsMutation()
      await _capturedMutations[0].onSuccess({})
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useUpdateNewsMutation', () => {
    it('mutationFn calls updateNews', async () => {
      const { useUpdateNewsMutation } = await import('../../src/queries/news')
      useUpdateNewsMutation()
      mockUpdateNews.mockResolvedValueOnce({ id: 'n1' })
      await _capturedMutations[0].mutationFn({ id: 'n1', dto: { title: 'Updated' } })
      expect(mockUpdateNews).toHaveBeenCalledWith('n1', { title: 'Updated' })
    })

    it('onSuccess invalidates news all and detail', async () => {
      const { useUpdateNewsMutation } = await import('../../src/queries/news')
      useUpdateNewsMutation()
      await _capturedMutations[0].onSuccess({}, { id: 'n1', dto: {} })
      expect(mockInvalidate).toHaveBeenCalledTimes(2)
    })
  })

  describe('useDeleteNewsMutation', () => {
    it('mutationFn calls deleteNews', async () => {
      const { useDeleteNewsMutation } = await import('../../src/queries/news')
      useDeleteNewsMutation()
      mockDeleteNews.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn('n1')
      expect(mockDeleteNews).toHaveBeenCalledWith('n1')
    })

    it('onSuccess removes gallery, attachments, and invalidates all', async () => {
      const { useDeleteNewsMutation } = await import('../../src/queries/news')
      useDeleteNewsMutation()
      await _capturedMutations[0].onSuccess(undefined, 'n1')
      expect(mockRemove).toHaveBeenCalledTimes(3)
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useUploadGalleryImageMutation', () => {
    it('mutationFn calls uploadGalleryImage', async () => {
      const { useUploadGalleryImageMutation } = await import('../../src/queries/news')
      useUploadGalleryImageMutation()
      const file = new File([''], 'img.jpg', { type: 'image/jpeg' })
      mockUploadGalleryImage.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn({ newsId: 'n1', file })
      expect(mockUploadGalleryImage).toHaveBeenCalledWith('n1', file)
    })

    it('onSuccess invalidates gallery query', async () => {
      const { useUploadGalleryImageMutation } = await import('../../src/queries/news')
      useUploadGalleryImageMutation()
      await _capturedMutations[0].onSuccess({}, { newsId: 'n1', file: {} })
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useDeleteGalleryImageMutation', () => {
    it('mutationFn calls deleteGalleryImage', async () => {
      const { useDeleteGalleryImageMutation } = await import('../../src/queries/news')
      useDeleteGalleryImageMutation()
      mockDeleteGalleryImage.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn({ newsId: 'n1', imgId: 'img-1' })
      expect(mockDeleteGalleryImage).toHaveBeenCalledWith('n1', 'img-1')
    })

    it('onSuccess invalidates gallery query', async () => {
      const { useDeleteGalleryImageMutation } = await import('../../src/queries/news')
      useDeleteGalleryImageMutation()
      await _capturedMutations[0].onSuccess(undefined, { newsId: 'n1', imgId: 'img-1' })
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useReorderGalleryMutation', () => {
    it('mutationFn calls reorderGallery', async () => {
      const { useReorderGalleryMutation } = await import('../../src/queries/news')
      useReorderGalleryMutation()
      mockReorderGallery.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn({ newsId: 'n1', items: [{ id: 'img-1', order: 1 }] })
      expect(mockReorderGallery).toHaveBeenCalledWith('n1', [{ id: 'img-1', order: 1 }])
    })

    it('onSuccess invalidates gallery query', async () => {
      const { useReorderGalleryMutation } = await import('../../src/queries/news')
      useReorderGalleryMutation()
      await _capturedMutations[0].onSuccess(undefined, { newsId: 'n1', items: [] })
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useUploadAttachmentMutation', () => {
    it('mutationFn calls uploadAttachment', async () => {
      const { useUploadAttachmentMutation } = await import('../../src/queries/news')
      useUploadAttachmentMutation()
      const file = new File([''], 'doc.pdf', { type: 'application/pdf' })
      mockUploadAttachment.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn({ newsId: 'n1', file })
      expect(mockUploadAttachment).toHaveBeenCalledWith('n1', file)
    })

    it('onSuccess invalidates attachments query', async () => {
      const { useUploadAttachmentMutation } = await import('../../src/queries/news')
      useUploadAttachmentMutation()
      await _capturedMutations[0].onSuccess({}, { newsId: 'n1', file: {} })
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useDeleteAttachmentMutation', () => {
    it('mutationFn calls deleteAttachment', async () => {
      const { useDeleteAttachmentMutation } = await import('../../src/queries/news')
      useDeleteAttachmentMutation()
      mockDeleteAttachment.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn({ newsId: 'n1', attId: 'att-1' })
      expect(mockDeleteAttachment).toHaveBeenCalledWith('n1', 'att-1')
    })

    it('onSuccess invalidates attachments query', async () => {
      const { useDeleteAttachmentMutation } = await import('../../src/queries/news')
      useDeleteAttachmentMutation()
      await _capturedMutations[0].onSuccess(undefined, { newsId: 'n1', attId: 'att-1' })
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useNewsPollQuery', () => {
    it('registers a query', async () => {
      const { useNewsPollQuery } = await import('../../src/queries/news')
      useNewsPollQuery(VALID_UUID)
      expect(_capturedQueries).toHaveLength(1)
    })
  })

  describe('useCreateNewsPollMutation', () => {
    it('mutationFn calls createNewsPoll', async () => {
      const { useCreateNewsPollMutation } = await import('../../src/queries/news')
      useCreateNewsPollMutation()
      const dto = { question: 'Q', options: [] }
      mockCreateNewsPoll.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn({ newsId: 'n1', dto })
      expect(mockCreateNewsPoll).toHaveBeenCalledWith('n1', dto)
    })
  })

  describe('useUpdateNewsPollMutation', () => {
    it('mutationFn calls updateNewsPoll', async () => {
      const { useUpdateNewsPollMutation } = await import('../../src/queries/news')
      useUpdateNewsPollMutation()
      const dto = { question: 'Q' }
      mockUpdateNewsPoll.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn({ newsId: 'n1', dto })
      expect(mockUpdateNewsPoll).toHaveBeenCalledWith('n1', dto)
    })
  })

  describe('useDeleteNewsPollMutation', () => {
    it('mutationFn calls deleteNewsPoll', async () => {
      const { useDeleteNewsPollMutation } = await import('../../src/queries/news')
      useDeleteNewsPollMutation()
      mockDeleteNewsPoll.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn('n1')
      expect(mockDeleteNewsPoll).toHaveBeenCalledWith('n1')
    })
  })

  describe('useCloseNewsPollMutation', () => {
    it('mutationFn calls closeNewsPoll', async () => {
      const { useCloseNewsPollMutation } = await import('../../src/queries/news')
      useCloseNewsPollMutation()
      mockCloseNewsPoll.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn('n1')
      expect(mockCloseNewsPoll).toHaveBeenCalledWith('n1')
    })
  })

  describe('useReopenNewsPollMutation', () => {
    it('mutationFn calls reopenNewsPoll', async () => {
      const { useReopenNewsPollMutation } = await import('../../src/queries/news')
      useReopenNewsPollMutation()
      mockReopenNewsPoll.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn('n1')
      expect(mockReopenNewsPoll).toHaveBeenCalledWith('n1')
    })
  })

  describe('useVoteNewsPollMutation', () => {
    it('mutationFn calls voteNewsPoll', async () => {
      const { useVoteNewsPollMutation } = await import('../../src/queries/news')
      useVoteNewsPollMutation()
      const dto = { option_ids: ['opt-1'] }
      mockVoteNewsPoll.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn({ newsId: 'n1', dto })
      expect(mockVoteNewsPoll).toHaveBeenCalledWith('n1', dto)
    })
  })

  describe('useRevokeNewsPollVoteMutation', () => {
    it('mutationFn calls revokeNewsPollVote', async () => {
      const { useRevokeNewsPollVoteMutation } = await import('../../src/queries/news')
      useRevokeNewsPollVoteMutation()
      mockRevokeNewsPollVote.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn('n1')
      expect(mockRevokeNewsPollVote).toHaveBeenCalledWith('n1')
    })
  })
})
