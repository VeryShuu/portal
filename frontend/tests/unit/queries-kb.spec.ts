import { isRef } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetchArticles = vi.fn()
const mockFetchArticle = vi.fn()
const mockFetchTags = vi.fn()
const mockFetchSections = vi.fn()
const mockFetchComments = vi.fn()
const mockCreateComment = vi.fn()
const mockDeleteComment = vi.fn()
const mockFetchVersions = vi.fn()
const mockRestoreVersion = vi.fn()
const mockCreateArticle = vi.fn()
const mockUpdateArticle = vi.fn()
const mockDeleteArticle = vi.fn()
const mockCreateSection = vi.fn()
const mockDeleteSection = vi.fn()

vi.mock('../../src/api/kb', () => ({
  fetchArticles: mockFetchArticles,
  fetchArticle: mockFetchArticle,
  fetchTags: mockFetchTags,
  fetchSections: mockFetchSections,
  fetchComments: mockFetchComments,
  createComment: mockCreateComment,
  deleteComment: mockDeleteComment,
  fetchVersions: mockFetchVersions,
  restoreVersion: mockRestoreVersion,
  createArticle: mockCreateArticle,
  updateArticle: mockUpdateArticle,
  deleteArticle: mockDeleteArticle,
  createSection: mockCreateSection,
  deleteSection: mockDeleteSection,
}))

const _capturedQueries: any[] = []
const _capturedMutations: any[] = []
const mockInvalidate = vi.fn()
const mockRemove = vi.fn()
const mockSetQueryData = vi.fn()

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
    setQueryData: mockSetQueryData,
  })),
}))

function resolveKey(k: unknown): unknown {
  if (isRef(k)) return resolveKey(k.value)
  return k
}

describe('src/queries/kb', () => {
  beforeEach(() => {
    _capturedQueries.length = 0
    _capturedMutations.length = 0
    vi.clearAllMocks()
  })

  describe('useKbArticlesQuery', () => {
    it('registers a query', async () => {
      const { useKbArticlesQuery } = await import('../../src/queries/kb')
      useKbArticlesQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchArticles with default params', async () => {
      const { useKbArticlesQuery } = await import('../../src/queries/kb')
      useKbArticlesQuery()
      mockFetchArticles.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchArticles).toHaveBeenCalledWith({})
    })

    it('queryFn passes params to fetchArticles', async () => {
      const { useKbArticlesQuery } = await import('../../src/queries/kb')
      useKbArticlesQuery({ section: 's1' })
      mockFetchArticles.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchArticles).toHaveBeenCalledWith({ section: 's1' })
    })

    it('queryKey contains kb namespace', async () => {
      const { useKbArticlesQuery } = await import('../../src/queries/kb')
      useKbArticlesQuery()
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('kb')
    })
  })

  describe('useKbArticleQuery', () => {
    it('registers a query', async () => {
      const { useKbArticleQuery } = await import('../../src/queries/kb')
      useKbArticleQuery('art-1')
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchArticle with id', async () => {
      const { useKbArticleQuery } = await import('../../src/queries/kb')
      useKbArticleQuery('art-1')
      mockFetchArticle.mockResolvedValueOnce({ id: 'art-1' })
      await _capturedQueries[0].queryFn()
      expect(mockFetchArticle).toHaveBeenCalledWith('art-1')
    })

    it('enabled is false when id is empty', async () => {
      const { useKbArticleQuery } = await import('../../src/queries/kb')
      useKbArticleQuery('')
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(false)
    })

    it('enabled is true when id is non-empty', async () => {
      const { useKbArticleQuery } = await import('../../src/queries/kb')
      useKbArticleQuery('art-1')
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(true)
    })
  })

  describe('useKbTagsQuery', () => {
    it('registers a query and calls fetchTags', async () => {
      const { useKbTagsQuery } = await import('../../src/queries/kb')
      useKbTagsQuery()
      expect(_capturedQueries).toHaveLength(1)
      mockFetchTags.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchTags).toHaveBeenCalled()
    })
  })

  describe('useKbSectionsQuery', () => {
    it('registers a query and calls fetchSections', async () => {
      const { useKbSectionsQuery } = await import('../../src/queries/kb')
      useKbSectionsQuery()
      expect(_capturedQueries).toHaveLength(1)
      mockFetchSections.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchSections).toHaveBeenCalled()
    })
  })

  describe('useKbCommentsQuery', () => {
    it('registers a query', async () => {
      const { useKbCommentsQuery } = await import('../../src/queries/kb')
      useKbCommentsQuery('art-1')
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchComments with articleId and limit', async () => {
      const { useKbCommentsQuery } = await import('../../src/queries/kb')
      useKbCommentsQuery('art-1')
      mockFetchComments.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchComments).toHaveBeenCalledWith('art-1', { limit: 50 })
    })

    it('enabled is false when articleId is empty', async () => {
      const { useKbCommentsQuery } = await import('../../src/queries/kb')
      useKbCommentsQuery('')
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(false)
    })
  })

  describe('useKbVersionsQuery', () => {
    it('registers a query', async () => {
      const { useKbVersionsQuery } = await import('../../src/queries/kb')
      useKbVersionsQuery('art-1')
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchVersions with articleId and limit', async () => {
      const { useKbVersionsQuery } = await import('../../src/queries/kb')
      useKbVersionsQuery('art-1')
      mockFetchVersions.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchVersions).toHaveBeenCalledWith('art-1', { limit: 50 })
    })

    it('enabled is false when articleId is empty', async () => {
      const { useKbVersionsQuery } = await import('../../src/queries/kb')
      useKbVersionsQuery('')
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(false)
    })
  })

  describe('useCreateKbCommentMutation', () => {
    it('registers a mutation', async () => {
      const { useCreateKbCommentMutation } = await import('../../src/queries/kb')
      useCreateKbCommentMutation()
      expect(_capturedMutations).toHaveLength(1)
    })

    it('mutationFn calls createComment', async () => {
      const { useCreateKbCommentMutation } = await import('../../src/queries/kb')
      useCreateKbCommentMutation()
      mockCreateComment.mockResolvedValueOnce({ id: 'c1' })
      await _capturedMutations[0].mutationFn({ articleId: 'art-1', body: 'Hello' })
      expect(mockCreateComment).toHaveBeenCalledWith('art-1', 'Hello')
    })

    it('onSuccess invalidates comments query for articleId', async () => {
      const { useCreateKbCommentMutation } = await import('../../src/queries/kb')
      useCreateKbCommentMutation()
      await _capturedMutations[0].onSuccess({}, { articleId: 'art-1', body: 'x' })
      expect(mockInvalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: expect.anything() }),
      )
    })
  })

  describe('useDeleteKbCommentMutation', () => {
    it('mutationFn calls deleteComment', async () => {
      const { useDeleteKbCommentMutation } = await import('../../src/queries/kb')
      useDeleteKbCommentMutation()
      mockDeleteComment.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn({ articleId: 'art-1', commentId: 'c1' })
      expect(mockDeleteComment).toHaveBeenCalledWith('art-1', 'c1')
    })

    it('onSuccess invalidates comments query', async () => {
      const { useDeleteKbCommentMutation } = await import('../../src/queries/kb')
      useDeleteKbCommentMutation()
      await _capturedMutations[0].onSuccess({}, { articleId: 'art-1', commentId: 'c1' })
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useRestoreKbVersionMutation', () => {
    it('mutationFn calls restoreVersion', async () => {
      const { useRestoreKbVersionMutation } = await import('../../src/queries/kb')
      useRestoreKbVersionMutation()
      const restored = { id: 'art-1', title: 'v2' }
      mockRestoreVersion.mockResolvedValueOnce(restored)
      await _capturedMutations[0].mutationFn({ articleId: 'art-1', versionNum: 2 })
      expect(mockRestoreVersion).toHaveBeenCalledWith('art-1', 2)
    })

    it('onSuccess calls setQueryData and invalidates versions and articles', async () => {
      const { useRestoreKbVersionMutation } = await import('../../src/queries/kb')
      useRestoreKbVersionMutation()
      const restored = { id: 'art-1', title: 'v2' }
      await _capturedMutations[0].onSuccess(restored)
      expect(mockSetQueryData).toHaveBeenCalled()
      expect(mockInvalidate).toHaveBeenCalledTimes(2)
    })
  })

  describe('useCreateKbArticleMutation', () => {
    it('mutationFn calls createArticle', async () => {
      const { useCreateKbArticleMutation } = await import('../../src/queries/kb')
      useCreateKbArticleMutation()
      mockCreateArticle.mockResolvedValueOnce({ id: 'new-art' })
      await _capturedMutations[0].mutationFn({ title: 'New Article', section_id: 's1' })
      expect(mockCreateArticle).toHaveBeenCalledWith({ title: 'New Article', section_id: 's1' })
    })

    it('onSuccess invalidates articles and tags', async () => {
      const { useCreateKbArticleMutation } = await import('../../src/queries/kb')
      useCreateKbArticleMutation()
      await _capturedMutations[0].onSuccess({})
      expect(mockInvalidate).toHaveBeenCalledTimes(2)
    })
  })

  describe('useUpdateKbArticleMutation', () => {
    it('mutationFn calls updateArticle', async () => {
      const { useUpdateKbArticleMutation } = await import('../../src/queries/kb')
      useUpdateKbArticleMutation()
      mockUpdateArticle.mockResolvedValueOnce({ id: 'art-1' })
      await _capturedMutations[0].mutationFn({ id: 'art-1', dto: { title: 'Updated' } })
      expect(mockUpdateArticle).toHaveBeenCalledWith('art-1', { title: 'Updated' })
    })

    it('onSuccess invalidates article, versions, and articles list', async () => {
      const { useUpdateKbArticleMutation } = await import('../../src/queries/kb')
      useUpdateKbArticleMutation()
      await _capturedMutations[0].onSuccess({}, { id: 'art-1', dto: {} })
      expect(mockInvalidate).toHaveBeenCalledTimes(3)
    })
  })

  describe('useDeleteKbArticleMutation', () => {
    it('mutationFn calls deleteArticle', async () => {
      const { useDeleteKbArticleMutation } = await import('../../src/queries/kb')
      useDeleteKbArticleMutation()
      mockDeleteArticle.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn('art-1')
      expect(mockDeleteArticle).toHaveBeenCalledWith('art-1')
    })

    it('onSuccess removes article query and invalidates articles list', async () => {
      const { useDeleteKbArticleMutation } = await import('../../src/queries/kb')
      useDeleteKbArticleMutation()
      await _capturedMutations[0].onSuccess(undefined, 'art-1')
      expect(mockRemove).toHaveBeenCalled()
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useCreateKbSectionMutation', () => {
    it('mutationFn calls createSection', async () => {
      const { useCreateKbSectionMutation } = await import('../../src/queries/kb')
      useCreateKbSectionMutation()
      mockCreateSection.mockResolvedValueOnce({ id: 's1' })
      await _capturedMutations[0].mutationFn({ title: 'New Section' })
      expect(mockCreateSection).toHaveBeenCalledWith({ title: 'New Section' })
    })

    it('onSuccess invalidates all kb queries', async () => {
      const { useCreateKbSectionMutation } = await import('../../src/queries/kb')
      useCreateKbSectionMutation()
      await _capturedMutations[0].onSuccess({})
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })

  describe('useDeleteKbSectionMutation', () => {
    it('mutationFn calls deleteSection', async () => {
      const { useDeleteKbSectionMutation } = await import('../../src/queries/kb')
      useDeleteKbSectionMutation()
      mockDeleteSection.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn({ id: 's1', force: true })
      expect(mockDeleteSection).toHaveBeenCalledWith('s1', true)
    })

    it('mutationFn calls deleteSection without force', async () => {
      const { useDeleteKbSectionMutation } = await import('../../src/queries/kb')
      useDeleteKbSectionMutation()
      mockDeleteSection.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn({ id: 's1' })
      expect(mockDeleteSection).toHaveBeenCalledWith('s1', undefined)
    })

    it('onSuccess invalidates all kb queries', async () => {
      const { useDeleteKbSectionMutation } = await import('../../src/queries/kb')
      useDeleteKbSectionMutation()
      await _capturedMutations[0].onSuccess({})
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })
})
