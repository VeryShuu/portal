import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()
const apiUploadMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
  apiUpload: (...args: unknown[]) => apiUploadMock(...args),
}))

import {
  createBookmark,
  createLink,
  deleteBookmark,
  deleteLink,
  deleteLinkIcon,
  fetchBookmarks,
  fetchLinks,
  getSsoUrl,
  reorderBookmarks,
  reorderLinks,
  updateLink,
  uploadLinkIcon,
} from '../../src/api/links'

describe('links/bookmarks API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiUploadMock.mockReset()
    apiMock.mockResolvedValue({ items: [], total: 0 })
    apiUploadMock.mockResolvedValue({})
  })

  it('fetchLinks passes filter params', async () => {
    await fetchLinks({ category: 'tools', include_inactive: true })
    expect(apiMock).toHaveBeenCalledWith('/links', {
      params: { category: 'tools', include_inactive: true },
    })
  })

  it('fetchLinks works without params', async () => {
    await fetchLinks()
    expect(apiMock).toHaveBeenCalledWith('/links', { params: undefined })
  })

  it('getSsoUrl GETs nested SSO endpoint', async () => {
    apiMock.mockResolvedValueOnce({ url: 'https://x', sso: true })
    const r = await getSsoUrl('abc')
    expect(apiMock).toHaveBeenCalledWith('/links/abc/sso-url')
    expect(r.url).toBe('https://x')
  })

  it('createLink POSTs body', async () => {
    await createLink({ title: 't', url: 'http://u' })
    expect(apiMock).toHaveBeenCalledWith('/links', {
      method: 'POST',
      body: { title: 't', url: 'http://u' },
    })
  })

  it('updateLink PUTs at /links/:id', async () => {
    await updateLink('id-1', { title: 'new' })
    expect(apiMock).toHaveBeenCalledWith('/links/id-1', {
      method: 'PUT',
      body: { title: 'new' },
    })
  })

  it('deleteLink issues DELETE', async () => {
    await deleteLink('rm')
    expect(apiMock).toHaveBeenCalledWith('/links/rm', { method: 'DELETE' })
  })

  it('uploadLinkIcon sends FormData via apiUpload', async () => {
    const file = new File(['x'], 'i.png', { type: 'image/png' })
    await uploadLinkIcon('id-9', file)
    expect(apiUploadMock).toHaveBeenCalledTimes(1)
    const [path, fd] = apiUploadMock.mock.calls[0]
    expect(path).toBe('/links/id-9/icon')
    expect(fd).toBeInstanceOf(FormData)
    expect((fd as FormData).get('file')).toBeInstanceOf(File)
  })

  it('deleteLinkIcon DELETEs nested icon URL', async () => {
    await deleteLinkIcon('id-9')
    expect(apiMock).toHaveBeenCalledWith('/links/id-9/icon', { method: 'DELETE' })
  })

  it('fetchBookmarks GETs /bookmarks', async () => {
    await fetchBookmarks()
    expect(apiMock).toHaveBeenCalledWith('/bookmarks')
  })

  it('createBookmark POSTs body', async () => {
    await createBookmark({ title: 't', url: 'http://u' })
    expect(apiMock).toHaveBeenCalledWith('/bookmarks', {
      method: 'POST',
      body: { title: 't', url: 'http://u' },
    })
  })

  it('deleteBookmark issues DELETE', async () => {
    await deleteBookmark('b1')
    expect(apiMock).toHaveBeenCalledWith('/bookmarks/b1', { method: 'DELETE' })
  })

  it('reorderBookmarks PATCHes with items', async () => {
    await reorderBookmarks([{ id: 'b1', sort_order: 0 }])
    expect(apiMock).toHaveBeenCalledWith('/bookmarks/reorder', {
      method: 'PATCH',
      body: { items: [{ id: 'b1', sort_order: 0 }] },
    })
  })

  it('reorderLinks PATCHes with items', async () => {
    await reorderLinks([{ id: 'l1', sort_order: 5 }])
    expect(apiMock).toHaveBeenCalledWith('/links/reorder', {
      method: 'PATCH',
      body: { items: [{ id: 'l1', sort_order: 5 }] },
    })
  })

  it('propagates errors from api()', async () => {
    apiMock.mockRejectedValueOnce(Object.assign(new Error('forbidden'), { status: 403 }))
    await expect(fetchLinks()).rejects.toMatchObject({ status: 403 })
  })
})
