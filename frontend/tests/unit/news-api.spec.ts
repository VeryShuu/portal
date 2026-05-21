import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()
const apiUploadMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
  apiUpload: (...args: unknown[]) => apiUploadMock(...args),
}))

import {
  createNews,
  createNewsCategory,
  deleteAttachment,
  deleteGalleryImage,
  deleteNews,
  deleteNewsCover,
  deleteNewsCategory,
  fetchAttachments,
  fetchGallery,
  fetchNewsById,
  fetchNewsCategories,
  fetchNewsList,
  fetchNewsUploadLimits,
  fetchNewsVersions,
  listTrashNews,
  purgeNews,
  reorderGallery,
  restoreNews,
  saveDraft,
  updateNews,
  updateNewsCategoryColor,
  uploadAttachment,
  uploadGalleryImage,
  uploadNewsCover,
  fetchNewsPoll,
  createNewsPoll,
  updateNewsPoll,
  deleteNewsPoll,
  closeNewsPoll,
  reopenNewsPoll,
  voteNewsPoll,
  revokeNewsPollVote,
} from '../../src/api/news'

describe('news API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiUploadMock.mockReset()
    apiMock.mockResolvedValue({})
    apiUploadMock.mockResolvedValue({})
  })

  describe('fetchNewsList', () => {
    it('GETs /news without params', async () => {
      await fetchNewsList()
      expect(apiMock).toHaveBeenCalledWith('/news', { params: undefined, signal: undefined })
    })

    it('passes query params', async () => {
      await fetchNewsList({ page: 2, page_size: 10, status: 'published', category: 'tech', q: 'test' })
      expect(apiMock).toHaveBeenCalledWith('/news', {
        params: { page: 2, page_size: 10, status: 'published', category: 'tech', q: 'test' },
        signal: undefined,
      })
    })

    it('passes AbortSignal', async () => {
      const ctrl = new AbortController()
      await fetchNewsList(undefined, { signal: ctrl.signal })
      const [, opts] = apiMock.mock.calls[0]
      expect(opts.signal).toBe(ctrl.signal)
    })
  })

  describe('fetchNewsById', () => {
    it('GETs /news/:id', async () => {
      await fetchNewsById('n-1')
      expect(apiMock).toHaveBeenCalledWith('/news/n-1')
    })
  })

  describe('createNews', () => {
    it('POSTs dto to /news', async () => {
      await createNews({ title: 'Hello', status: 'draft', is_pinned: false })
      expect(apiMock).toHaveBeenCalledWith('/news', {
        method: 'POST',
        body: { title: 'Hello', status: 'draft', is_pinned: false },
      })
    })
  })

  describe('updateNews', () => {
    it('PUTs dto to /news/:id', async () => {
      await updateNews('n-2', { title: 'Updated', status: 'published' })
      expect(apiMock).toHaveBeenCalledWith('/news/n-2', {
        method: 'PUT',
        body: { title: 'Updated', status: 'published' },
      })
    })
  })

  describe('saveDraft', () => {
    it('PUTs dto to /news/:id/draft', async () => {
      await saveDraft('n-3', { body: 'draft body' })
      expect(apiMock).toHaveBeenCalledWith('/news/n-3/draft', {
        method: 'PUT',
        body: { body: 'draft body' },
      })
    })
  })

  describe('deleteNews', () => {
    it('DELETEs /news/:id', async () => {
      await deleteNews('n-4')
      expect(apiMock).toHaveBeenCalledWith('/news/n-4', { method: 'DELETE' })
    })
  })

  describe('fetchNewsVersions', () => {
    it('GETs /news/:id/versions', async () => {
      await fetchNewsVersions('n-5')
      expect(apiMock).toHaveBeenCalledWith('/news/n-5/versions')
    })
  })

  describe('uploadNewsCover', () => {
    it('sends FormData via apiUpload', async () => {
      const file = new File(['data'], 'cover.jpg', { type: 'image/jpeg' })
      await uploadNewsCover('n-6', file)
      expect(apiUploadMock).toHaveBeenCalledTimes(1)
      const [path, fd] = apiUploadMock.mock.calls[0]
      expect(path).toBe('/news/n-6/cover')
      expect(fd).toBeInstanceOf(FormData)
      expect((fd as FormData).get('file')).toBeInstanceOf(File)
    })
  })

  describe('deleteNewsCover', () => {
    it('DELETEs /news/:id/cover', async () => {
      await deleteNewsCover('n-7')
      expect(apiMock).toHaveBeenCalledWith('/news/n-7/cover', { method: 'DELETE' })
    })
  })

  describe('gallery', () => {
    it('fetchGallery GETs /news/:id/gallery', async () => {
      await fetchGallery('n-10')
      expect(apiMock).toHaveBeenCalledWith('/news/n-10/gallery')
    })

    it('uploadGalleryImage sends FormData', async () => {
      const file = new File(['img'], 'photo.png', { type: 'image/png' })
      await uploadGalleryImage('n-11', file)
      expect(apiUploadMock).toHaveBeenCalledTimes(1)
      const [path, fd] = apiUploadMock.mock.calls[0]
      expect(path).toBe('/news/n-11/gallery')
      expect(fd).toBeInstanceOf(FormData)
    })

    it('reorderGallery PATCHes with items array', async () => {
      await reorderGallery('n-12', [{ id: 'img-1', sort_order: 0 }, { id: 'img-2', sort_order: 1 }])
      expect(apiMock).toHaveBeenCalledWith('/news/n-12/gallery/reorder', {
        method: 'PATCH',
        body: [{ id: 'img-1', sort_order: 0 }, { id: 'img-2', sort_order: 1 }],
      })
    })

    it('deleteGalleryImage DELETEs nested URL', async () => {
      await deleteGalleryImage('n-13', 'img-5')
      expect(apiMock).toHaveBeenCalledWith('/news/n-13/gallery/img-5', { method: 'DELETE' })
    })
  })

  describe('attachments', () => {
    it('fetchAttachments GETs /news/:id/attachments', async () => {
      await fetchAttachments('n-20')
      expect(apiMock).toHaveBeenCalledWith('/news/n-20/attachments')
    })

    it('uploadAttachment sends FormData via apiUpload', async () => {
      const file = new File(['pdf'], 'report.pdf', { type: 'application/pdf' })
      await uploadAttachment('n-21', file)
      expect(apiUploadMock).toHaveBeenCalledTimes(1)
      const [path, fd] = apiUploadMock.mock.calls[0]
      expect(path).toBe('/news/n-21/attachments')
      expect(fd).toBeInstanceOf(FormData)
      expect((fd as FormData).get('file')).toBeInstanceOf(File)
    })

    it('deleteAttachment DELETEs nested URL', async () => {
      await deleteAttachment('n-22', 'att-3')
      expect(apiMock).toHaveBeenCalledWith('/news/n-22/attachments/att-3', { method: 'DELETE' })
    })
  })

  describe('categories', () => {
    it('fetchNewsCategories GETs /news-categories and returns items', async () => {
      apiMock.mockResolvedValueOnce({ items: [{ name: 'Tech', color: '#fff', news_count: 5 }] })
      const cats = await fetchNewsCategories()
      expect(apiMock).toHaveBeenCalledWith('/news-categories')
      expect(cats).toHaveLength(1)
      expect(cats[0].name).toBe('Tech')
    })

    it('createNewsCategory POSTs and returns items', async () => {
      apiMock.mockResolvedValueOnce({ items: [{ name: 'HR', color: '#f00', news_count: 0 }] })
      const cats = await createNewsCategory('HR', '#f00')
      expect(apiMock).toHaveBeenCalledWith('/news-categories', {
        method: 'POST',
        body: { name: 'HR', color: '#f00' },
      })
      expect(cats[0].name).toBe('HR')
    })

    it('updateNewsCategoryColor PATCHes color', async () => {
      apiMock.mockResolvedValueOnce({ items: [] })
      await updateNewsCategoryColor('Tech', '#00f')
      expect(apiMock).toHaveBeenCalledWith('/news-categories/Tech/color', {
        method: 'PATCH',
        body: { color: '#00f' },
      })
    })

    it('updateNewsCategoryColor encodes category name', async () => {
      apiMock.mockResolvedValueOnce({ items: [] })
      await updateNewsCategoryColor('Science & Tech', '#0f0')
      expect(apiMock).toHaveBeenCalledWith('/news-categories/Science%20%26%20Tech/color', {
        method: 'PATCH',
        body: { color: '#0f0' },
      })
    })

    it('deleteNewsCategory DELETEs and returns items', async () => {
      apiMock.mockResolvedValueOnce({ items: [] })
      await deleteNewsCategory('HR')
      expect(apiMock).toHaveBeenCalledWith('/news-categories/HR', { method: 'DELETE' })
    })
  })

  describe('fetchNewsUploadLimits', () => {
    it('GETs /news/limits', async () => {
      await fetchNewsUploadLimits()
      expect(apiMock).toHaveBeenCalledWith('/news/limits')
    })
  })

  describe('trash', () => {
    it('listTrashNews GETs /news/trash without params', async () => {
      await listTrashNews()
      expect(apiMock).toHaveBeenCalledWith('/news/trash', { params: undefined })
    })

    it('listTrashNews passes pagination params', async () => {
      await listTrashNews({ page: 1, page_size: 20 })
      expect(apiMock).toHaveBeenCalledWith('/news/trash', {
        params: { page: 1, page_size: 20 },
      })
    })

    it('restoreNews POSTs to /news/:id/restore', async () => {
      await restoreNews('n-30')
      expect(apiMock).toHaveBeenCalledWith('/news/n-30/restore', { method: 'POST' })
    })

    it('purgeNews DELETEs /news/:id/purge', async () => {
      await purgeNews('n-31')
      expect(apiMock).toHaveBeenCalledWith('/news/n-31/purge', { method: 'DELETE' })
    })
  })

  describe('polls API client', () => {
    it('fetchNewsPoll GETs /news/:id/poll', async () => {
      await fetchNewsPoll('news-1')
      expect(apiMock).toHaveBeenCalledWith('/news/news-1/poll')
    })

    it('createNewsPoll POSTs /news/:id/poll', async () => {
      const dto = { question: 'Q', options: [] }
      await createNewsPoll('news-1', dto)
      expect(apiMock).toHaveBeenCalledWith('/news/news-1/poll', { method: 'POST', body: dto })
    })

    it('updateNewsPoll PATCHes /news/:id/poll', async () => {
      const dto = { question: 'New Q' }
      await updateNewsPoll('news-1', dto)
      expect(apiMock).toHaveBeenCalledWith('/news/news-1/poll', { method: 'PATCH', body: dto })
    })

    it('deleteNewsPoll DELETEs /news/:id/poll', async () => {
      await deleteNewsPoll('news-1')
      expect(apiMock).toHaveBeenCalledWith('/news/news-1/poll', { method: 'DELETE' })
    })

    it('closeNewsPoll POSTs /news/:id/poll/close', async () => {
      await closeNewsPoll('news-1')
      expect(apiMock).toHaveBeenCalledWith('/news/news-1/poll/close', { method: 'POST' })
    })

    it('reopenNewsPoll POSTs /news/:id/poll/reopen', async () => {
      await reopenNewsPoll('news-1')
      expect(apiMock).toHaveBeenCalledWith('/news/news-1/poll/reopen', { method: 'POST' })
    })

    it('voteNewsPoll POSTs /news/:id/poll/vote', async () => {
      const dto = { option_ids: ['opt-1'] }
      await voteNewsPoll('news-1', dto)
      expect(apiMock).toHaveBeenCalledWith('/news/news-1/poll/vote', { method: 'POST', body: dto })
    })

    it('revokeNewsPollVote DELETEs /news/:id/poll/vote', async () => {
      await revokeNewsPollVote('news-1')
      expect(apiMock).toHaveBeenCalledWith('/news/news-1/poll/vote', { method: 'DELETE' })
    })
  })

  describe('error propagation', () => {
    it('propagates api errors', async () => {
      apiMock.mockRejectedValueOnce(Object.assign(new Error('not found'), { status: 404 }))
      await expect(fetchNewsById('missing')).rejects.toMatchObject({ status: 404 })
    })

    it('propagates apiUpload errors', async () => {
      apiUploadMock.mockRejectedValueOnce(Object.assign(new Error('too large'), { status: 413 }))
      await expect(uploadNewsCover('n-1', new File(['x'], 'x.jpg'))).rejects.toMatchObject({ status: 413 })
    })
  })
})
