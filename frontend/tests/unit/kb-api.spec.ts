import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()
const apiUploadMock = vi.fn()
const triggerDownloadMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
  apiUpload: (...args: unknown[]) => apiUploadMock(...args),
}))

vi.mock('../../src/utils/download', () => ({
  triggerDownload: (...args: unknown[]) => triggerDownloadMock(...args),
}))

import {
  createArticle,
  createComment,
  createSection,
  deleteArticle,
  deleteComment,
  deleteSection,
  exportArticleDocx,
  exportArticlePdf,
  exportKbVault,
  exportSectionZip,
  fetchArticle,
  fetchArticles,
  fetchComments,
  fetchSections,
  fetchTags,
  fetchVersions,
  globalSearch,
  importMarkdownFile,
  importVaultZip,
  restoreArticle,
  restoreVersion,
  saveDraft,
  searchSuggest,
  submitFeedback,
  suggestEdit,
  updateArticle,
  updateSection,
} from '../../src/api/kb'

describe('KB API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiUploadMock.mockReset()
    triggerDownloadMock.mockReset()
    apiMock.mockResolvedValue({})
    apiUploadMock.mockResolvedValue({})
  })

  describe('tags', () => {
    it('fetchTags GETs /kb/tags', async () => {
      await fetchTags()
      expect(apiMock).toHaveBeenCalledWith('/kb/tags')
    })
  })

  describe('sections', () => {
    it('fetchSections GETs /kb/sections', async () => {
      await fetchSections()
      expect(apiMock).toHaveBeenCalledWith('/kb/sections')
    })

    it('createSection POSTs dto', async () => {
      await createSection({ title: 'Intro', parent_id: null, description: 'desc', sort_order: 0 })
      expect(apiMock).toHaveBeenCalledWith('/kb/sections', {
        method: 'POST',
        body: { title: 'Intro', parent_id: null, description: 'desc', sort_order: 0 },
      })
    })

    it('updateSection PUTs dto to /kb/sections/:id', async () => {
      await updateSection('s-1', { title: 'Renamed' })
      expect(apiMock).toHaveBeenCalledWith('/kb/sections/s-1', {
        method: 'PUT',
        body: { title: 'Renamed' },
      })
    })

    it('deleteSection DELETEs without force flag by default', async () => {
      await deleteSection('s-2')
      expect(apiMock).toHaveBeenCalledWith('/kb/sections/s-2', {
        method: 'DELETE',
        params: { force: false },
      })
    })

    it('deleteSection DELETEs with force=true', async () => {
      await deleteSection('s-3', true)
      expect(apiMock).toHaveBeenCalledWith('/kb/sections/s-3', {
        method: 'DELETE',
        params: { force: true },
      })
    })
  })

  describe('articles', () => {
    it('fetchArticles GETs /kb/articles without params', async () => {
      await fetchArticles()
      expect(apiMock).toHaveBeenCalledWith('/kb/articles', { params: undefined })
    })

    it('fetchArticles passes filter params', async () => {
      await fetchArticles({ section_id: 's-1', tag: 'vue', status: 'published', q: 'search', limit: 10, offset: 0 })
      expect(apiMock).toHaveBeenCalledWith('/kb/articles', {
        params: { section_id: 's-1', tag: 'vue', status: 'published', q: 'search', limit: 10, offset: 0 },
      })
    })

    it('fetchArticle GETs /kb/articles/:id', async () => {
      await fetchArticle('a-1')
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-1')
    })

    it('createArticle POSTs dto', async () => {
      await createArticle({ title: 'New Article', body: 'body', status: 'draft', tags: ['tag1'] })
      expect(apiMock).toHaveBeenCalledWith('/kb/articles', {
        method: 'POST',
        body: { title: 'New Article', body: 'body', status: 'draft', tags: ['tag1'] },
      })
    })

    it('updateArticle PUTs dto with version', async () => {
      await updateArticle('a-2', { title: 'Updated', body: 'new body', version: 3, change_comment: 'typo fix' })
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-2', {
        method: 'PUT',
        body: { title: 'Updated', body: 'new body', version: 3, change_comment: 'typo fix' },
      })
    })

    it('saveDraft PUTs partial dto to /kb/articles/:id/draft', async () => {
      await saveDraft('a-3', { body: 'draft content' })
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-3/draft', {
        method: 'PUT',
        body: { body: 'draft content' },
      })
    })

    it('deleteArticle DELETEs /kb/articles/:id', async () => {
      await deleteArticle('a-4')
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-4', { method: 'DELETE' })
    })

    it('restoreArticle POSTs to /kb/articles/:id/restore', async () => {
      await restoreArticle('a-5')
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-5/restore', { method: 'POST' })
    })
  })

  describe('versions', () => {
    it('fetchVersions GETs /kb/articles/:id/versions without params', async () => {
      await fetchVersions('a-10')
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-10/versions', { params: undefined })
    })

    it('fetchVersions passes limit and offset', async () => {
      await fetchVersions('a-11', { limit: 5, offset: 10 })
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-11/versions', {
        params: { limit: 5, offset: 10 },
      })
    })

    it('restoreVersion POSTs to /kb/articles/:id/versions/:num/restore', async () => {
      await restoreVersion('a-12', 2)
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-12/versions/2/restore', { method: 'POST' })
    })
  })

  describe('comments', () => {
    it('fetchComments GETs /kb/articles/:id/comments without params', async () => {
      await fetchComments('a-20')
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-20/comments', { params: undefined })
    })

    it('fetchComments passes pagination params', async () => {
      await fetchComments('a-21', { limit: 10, offset: 0 })
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-21/comments', {
        params: { limit: 10, offset: 0 },
      })
    })

    it('createComment POSTs body', async () => {
      await createComment('a-22', 'Great article!')
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-22/comments', {
        method: 'POST',
        body: { body: 'Great article!' },
      })
    })

    it('deleteComment DELETEs nested URL', async () => {
      await deleteComment('a-23', 'c-5')
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-23/comments/c-5', { method: 'DELETE' })
    })
  })

  describe('suggestEdit', () => {
    it('POSTs suggestion dto', async () => {
      await suggestEdit('a-30', { body: 'corrected text', comment: 'typo' })
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-30/suggest', {
        method: 'POST',
        body: { body: 'corrected text', comment: 'typo' },
      })
    })

    it('POSTs suggestion without comment', async () => {
      await suggestEdit('a-31', { body: 'text only' })
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-31/suggest', {
        method: 'POST',
        body: { body: 'text only' },
      })
    })
  })

  describe('submitFeedback', () => {
    it('POSTs helpful=true', async () => {
      await submitFeedback('a-40', true)
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-40/feedback', {
        method: 'POST',
        body: { is_helpful: true },
      })
    })

    it('POSTs helpful=false', async () => {
      await submitFeedback('a-41', false)
      expect(apiMock).toHaveBeenCalledWith('/kb/articles/a-41/feedback', {
        method: 'POST',
        body: { is_helpful: false },
      })
    })
  })

  describe('export functions', () => {
    it('exportArticlePdf triggers download with pdf URL', async () => {
      await exportArticlePdf('a-50')
      expect(triggerDownloadMock).toHaveBeenCalledWith(
        '/api/v1/kb/articles/a-50/export/pdf',
        { target: '_blank', rel: 'noopener noreferrer' },
      )
    })

    it('exportArticleDocx triggers download with docx URL', async () => {
      await exportArticleDocx('a-51')
      expect(triggerDownloadMock).toHaveBeenCalledWith(
        '/api/v1/kb/articles/a-51/export/docx',
        { target: '_blank', rel: 'noopener noreferrer' },
      )
    })

    it('exportSectionZip triggers download with zip URL', () => {
      exportSectionZip('s-10')
      expect(triggerDownloadMock).toHaveBeenCalledWith('/api/v1/kb/sections/s-10/export/zip')
    })

    it('exportKbVault triggers download with vault URL', () => {
      exportKbVault()
      expect(triggerDownloadMock).toHaveBeenCalledWith('/api/v1/kb/export/vault.zip')
    })
  })

  describe('import functions', () => {
    it('importMarkdownFile uploads file via apiUpload', async () => {
      const file = new File(['# Hello'], 'article.md', { type: 'text/markdown' })
      await importMarkdownFile(file)
      expect(apiUploadMock).toHaveBeenCalledTimes(1)
      const [path, fd] = apiUploadMock.mock.calls[0]
      expect(path).toBe('/kb/articles/import')
      expect(fd).toBeInstanceOf(FormData)
      expect((fd as FormData).get('file')).toBeInstanceOf(File)
    })

    it('importVaultZip uploads with default skip strategy', async () => {
      const file = new File(['zip'], 'vault.zip', { type: 'application/zip' })
      await importVaultZip(file)
      expect(apiUploadMock).toHaveBeenCalledTimes(1)
      const [path] = apiUploadMock.mock.calls[0]
      expect(path).toBe('/kb/import/vault?strategy=skip')
    })

    it('importVaultZip uses provided strategy', async () => {
      const file = new File(['zip'], 'vault.zip', { type: 'application/zip' })
      await importVaultZip(file, 'overwrite')
      const [path] = apiUploadMock.mock.calls[0]
      expect(path).toBe('/kb/import/vault?strategy=overwrite')
    })

    it('importVaultZip sends FormData', async () => {
      const file = new File(['zip'], 'vault.zip')
      await importVaultZip(file, 'create_new')
      const [, fd] = apiUploadMock.mock.calls[0]
      expect(fd).toBeInstanceOf(FormData)
      expect((fd as FormData).get('file')).toBeInstanceOf(File)
    })
  })

  describe('search', () => {
    it('globalSearch GETs /search with q param', async () => {
      await globalSearch('fastapi')
      expect(apiMock).toHaveBeenCalledWith('/search', { params: { q: 'fastapi' }, signal: undefined })
    })

    it('globalSearch passes extra params and signal', async () => {
      const ctrl = new AbortController()
      await globalSearch('vue', { type: 'article', limit: 5, offset: 0 }, { signal: ctrl.signal })
      expect(apiMock).toHaveBeenCalledWith('/search', {
        params: { q: 'vue', type: 'article', limit: 5, offset: 0 },
        signal: ctrl.signal,
      })
    })

    it('searchSuggest GETs /search/suggest with q', async () => {
      await searchSuggest('fast')
      expect(apiMock).toHaveBeenCalledWith('/search/suggest', { params: { q: 'fast' } })
    })
  })

  describe('error propagation', () => {
    it('propagates api errors', async () => {
      apiMock.mockRejectedValueOnce(Object.assign(new Error('not found'), { status: 404 }))
      await expect(fetchArticle('missing')).rejects.toMatchObject({ status: 404 })
    })

    it('propagates apiUpload errors', async () => {
      apiUploadMock.mockRejectedValueOnce(Object.assign(new Error('bad file'), { status: 422 }))
      await expect(importMarkdownFile(new File(['x'], 'x.md'))).rejects.toMatchObject({ status: 422 })
    })
  })
})
