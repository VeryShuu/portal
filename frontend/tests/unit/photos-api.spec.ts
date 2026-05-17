import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()
const apiUploadMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
  apiUpload: (...args: unknown[]) => apiUploadMock(...args),
  BASE_URL: '/api/v1',
}))

import {
  bulkAction,
  createFolder,
  createFolderShareLink,
  createShareLink,
  createTag,
  deleteFolder,
  deletePhoto,
  deleteTag,
  emptyTrash,
  fetchDeletedFolders,
  fetchDeletedPhotos,
  fetchFolder,
  fetchFolderPhotos,
  fetchFolderPhotosFiltered,
  fetchFolderTree,
  fetchMyShares,
  fetchPermissions,
  fetchPhotoTags,
  fetchRecentPhotos,
  fetchTags,
  getImportScanStatus,
  getPhoto,
  getZipJob,
  grantPermission,
  importScan,
  moveFolder,
  originalUrl,
  publicFolderInfoUrl,
  publicFolderPhotosUrl,
  publicFolderThumbUrl,
  publicPhotoFileUrl,
  publicPhotoInfoUrl,
  publicPhotoThumbUrl,
  purgePhoto,
  restoreFolder,
  restorePhoto,
  revokePermission,
  revokeFolderShare,
  revokePhotoShare,
  searchSubjects,
  setPhotoTags,
  startFolderZip,
  thumbUrl,
  updateFolder,
  uploadPhotos,
  zipJobDownloadUrl,
} from '../../src/api/photos'

describe('photos API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiUploadMock.mockReset()
    apiMock.mockResolvedValue({})
    apiUploadMock.mockResolvedValue({})
  })

  describe('folders', () => {
    it('fetchFolderTree GETs /photos/folders/tree', async () => {
      await fetchFolderTree()
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/tree')
    })

    it('fetchFolder GETs /photos/folders/:id', async () => {
      await fetchFolder('f-1')
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-1')
    })

    it('createFolder POSTs body', async () => {
      await createFolder({ parent_id: null, name: 'Vacation', description: 'Summer 2025' })
      expect(apiMock).toHaveBeenCalledWith('/photos/folders', {
        method: 'POST',
        body: { parent_id: null, name: 'Vacation', description: 'Summer 2025' },
      })
    })

    it('updateFolder PATCHes body', async () => {
      await updateFolder('f-2', { name: 'Renamed', cover_photo_id: 'p-1' })
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-2', {
        method: 'PATCH',
        body: { name: 'Renamed', cover_photo_id: 'p-1' },
      })
    })

    it('deleteFolder DELETEs /photos/folders/:id', async () => {
      await deleteFolder('f-3')
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-3', { method: 'DELETE' })
    })

    it('fetchFolderPhotos GETs /photos/folders/:id/photos', async () => {
      await fetchFolderPhotos('f-4', { page: 2, per_page: 20, sort: 'created_at' })
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-4/photos', {
        params: { page: 2, per_page: 20, sort: 'created_at' },
      })
    })

    it('fetchFolderPhotos without params passes undefined', async () => {
      await fetchFolderPhotos('f-5')
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-5/photos', { params: undefined })
    })

    it('fetchDeletedFolders GETs /photos/folders/deleted', async () => {
      await fetchDeletedFolders()
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/deleted')
    })

    it('restoreFolder POSTs to /photos/folders/:id/restore', async () => {
      await restoreFolder('f-6')
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-6/restore', { method: 'POST' })
    })

    it('moveFolder PATCHes parent_id', async () => {
      await moveFolder('f-7', 'f-parent')
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-7', {
        method: 'PATCH',
        body: { parent_id: 'f-parent' },
      })
    })

    it('moveFolder accepts null parent (root)', async () => {
      await moveFolder('f-8', null)
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-8', {
        method: 'PATCH',
        body: { parent_id: null },
      })
    })
  })

  describe('photos', () => {
    it('fetchRecentPhotos GETs /photos/recent with default limit', async () => {
      await fetchRecentPhotos()
      expect(apiMock).toHaveBeenCalledWith('/photos/recent', { params: { limit: 8 } })
    })

    it('fetchRecentPhotos passes custom limit', async () => {
      await fetchRecentPhotos(24)
      expect(apiMock).toHaveBeenCalledWith('/photos/recent', { params: { limit: 24 } })
    })

    it('getPhoto GETs /photos/:id', async () => {
      await getPhoto('p-1')
      expect(apiMock).toHaveBeenCalledWith('/photos/p-1')
    })

    it('deletePhoto DELETEs /photos/:id', async () => {
      await deletePhoto('p-2')
      expect(apiMock).toHaveBeenCalledWith('/photos/p-2', { method: 'DELETE' })
    })

    it('uploadPhotos sends FormData via apiUpload with signal', async () => {
      const ctrl = new AbortController()
      const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' })
      const f2 = new File(['b'], 'b.png', { type: 'image/png' })
      await uploadPhotos('f-1', [f1, f2], ctrl.signal)
      expect(apiUploadMock).toHaveBeenCalledTimes(1)
      const [path, fd, method, signal] = apiUploadMock.mock.calls[0]
      expect(path).toBe('/photos/folders/f-1/upload')
      expect(method).toBe('POST')
      expect(fd).toBeInstanceOf(FormData)
      expect(signal).toBe(ctrl.signal)
      const entries = (fd as FormData).getAll('files')
      expect(entries).toHaveLength(2)
    })

    it('uploadPhotos works without signal', async () => {
      await uploadPhotos('f-2', [new File(['x'], 'x.jpg')])
      expect(apiUploadMock).toHaveBeenCalledTimes(1)
    })
  })

  describe('URL helpers', () => {
    it('thumbUrl builds thumbnail URL', () => {
      expect(thumbUrl('p-1', 400)).toBe('/api/v1/photos/thumbnail/p-1/400')
    })

    it('originalUrl builds original URL without download flag', () => {
      expect(originalUrl('p-2')).toBe('/api/v1/photos/original/p-2')
    })

    it('originalUrl adds download param when true', () => {
      expect(originalUrl('p-2', true)).toBe('/api/v1/photos/original/p-2?download=1')
    })

    it('publicPhotoInfoUrl encodes token', () => {
      const url = publicPhotoInfoUrl('tok/en')
      expect(url).toBe('/api/v1/photos/public/tok%2Fen/info')
    })

    it('publicPhotoThumbUrl builds public thumb URL', () => {
      expect(publicPhotoThumbUrl('abc', 600)).toBe('/api/v1/photos/public/abc/thumbnail/600')
    })

    it('publicPhotoFileUrl builds file URL without download', () => {
      expect(publicPhotoFileUrl('abc')).toBe('/api/v1/photos/public/abc/file')
    })

    it('publicPhotoFileUrl adds download param', () => {
      expect(publicPhotoFileUrl('abc', true)).toBe('/api/v1/photos/public/abc/file?download=1')
    })

    it('zipJobDownloadUrl builds zip download URL', () => {
      expect(zipJobDownloadUrl('job-1')).toBe('/api/v1/photos/zip-jobs/job-1/download')
    })

    it('publicFolderInfoUrl encodes token', () => {
      expect(publicFolderInfoUrl('tok/en')).toBe('/api/v1/photos/public-folder/tok%2Fen/info')
    })

    it('publicFolderPhotosUrl builds photos URL with pagination', () => {
      expect(publicFolderPhotosUrl('abc', 2, 20)).toBe(
        '/api/v1/photos/public-folder/abc/photos?page=2&per_page=20',
      )
    })

    it('publicFolderThumbUrl builds folder thumbnail URL', () => {
      expect(publicFolderThumbUrl('abc', 'p-1', 400)).toBe(
        '/api/v1/photos/public-folder/abc/thumbnail/p-1/400',
      )
    })
  })

  describe('permissions', () => {
    it('searchSubjects encodes query in URL', async () => {
      await searchSubjects('Иван Иванов')
      expect(apiMock).toHaveBeenCalledWith(
        `/photos/users/search?q=${encodeURIComponent('Иван Иванов')}`,
      )
    })

    it('fetchPermissions GETs /photos/folders/:id/permissions', async () => {
      await fetchPermissions('f-10')
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-10/permissions')
    })

    it('grantPermission POSTs body', async () => {
      await grantPermission('f-11', {
        subject_type: 'user',
        subject_id: 'u-1',
        subject_name: 'Alice',
        permission: 'viewer',
      })
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-11/permissions', {
        method: 'POST',
        body: { subject_type: 'user', subject_id: 'u-1', subject_name: 'Alice', permission: 'viewer' },
      })
    })

    it('revokePermission DELETEs and encodes subjectId', async () => {
      await revokePermission('f-12', 'u/1')
      expect(apiMock).toHaveBeenCalledWith(
        '/photos/folders/f-12/permissions/u%2F1',
        { method: 'DELETE' },
      )
    })
  })

  describe('shares', () => {
    it('createShareLink POSTs with expires_in_days', async () => {
      await createShareLink('p-3', 14)
      expect(apiMock).toHaveBeenCalledWith('/photos/p-3/share', {
        method: 'POST',
        body: { expires_in_days: 14 },
      })
    })

    it('createShareLink uses default 7 days', async () => {
      await createShareLink('p-4')
      expect(apiMock).toHaveBeenCalledWith('/photos/p-4/share', {
        method: 'POST',
        body: { expires_in_days: 7 },
      })
    })

    it('createFolderShareLink POSTs', async () => {
      await createFolderShareLink('f-20', null)
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-20/share', {
        method: 'POST',
        body: { expires_in_days: null },
      })
    })

    it('fetchMyShares GETs /photos/my-shares', async () => {
      await fetchMyShares()
      expect(apiMock).toHaveBeenCalledWith('/photos/my-shares')
    })

    it('revokePhotoShare DELETEs /photos/my-shares/photo/:id', async () => {
      await revokePhotoShare('tok-1')
      expect(apiMock).toHaveBeenCalledWith('/photos/my-shares/photo/tok-1', { method: 'DELETE' })
    })

    it('revokeFolderShare DELETEs /photos/my-shares/folder/:id', async () => {
      await revokeFolderShare('tok-2')
      expect(apiMock).toHaveBeenCalledWith('/photos/my-shares/folder/tok-2', { method: 'DELETE' })
    })
  })

  describe('trash', () => {
    it('fetchDeletedPhotos GETs /photos/deleted without params', async () => {
      await fetchDeletedPhotos()
      expect(apiMock).toHaveBeenCalledWith('/photos/deleted', { params: undefined })
    })

    it('fetchDeletedPhotos passes pagination params', async () => {
      await fetchDeletedPhotos({ page: 2, per_page: 10 })
      expect(apiMock).toHaveBeenCalledWith('/photos/deleted', { params: { page: 2, per_page: 10 } })
    })

    it('restorePhoto POSTs to /photos/:id/restore', async () => {
      await restorePhoto('p-5')
      expect(apiMock).toHaveBeenCalledWith('/photos/p-5/restore', { method: 'POST' })
    })

    it('purgePhoto DELETEs /photos/:id/purge', async () => {
      await purgePhoto('p-6')
      expect(apiMock).toHaveBeenCalledWith('/photos/p-6/purge', { method: 'DELETE' })
    })

    it('emptyTrash POSTs to /photos/trash/empty', async () => {
      await emptyTrash()
      expect(apiMock).toHaveBeenCalledWith('/photos/trash/empty', { method: 'POST' })
    })
  })

  describe('bulk actions', () => {
    it('bulkAction POSTs move action', async () => {
      await bulkAction({ action: 'move', photo_ids: ['p-1', 'p-2'], target_folder_id: 'f-dest' })
      expect(apiMock).toHaveBeenCalledWith('/photos/bulk', {
        method: 'POST',
        body: { action: 'move', photo_ids: ['p-1', 'p-2'], target_folder_id: 'f-dest' },
      })
    })

    it('bulkAction POSTs delete action', async () => {
      await bulkAction({ action: 'delete', photo_ids: ['p-3'] })
      expect(apiMock).toHaveBeenCalledWith('/photos/bulk', {
        method: 'POST',
        body: { action: 'delete', photo_ids: ['p-3'] },
      })
    })
  })

  describe('zip download', () => {
    it('startFolderZip POSTs to /photos/folders/:id/zip', async () => {
      await startFolderZip('f-30')
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-30/zip', { method: 'POST' })
    })

    it('getZipJob GETs /photos/zip-jobs/:id', async () => {
      await getZipJob('job-2')
      expect(apiMock).toHaveBeenCalledWith('/photos/zip-jobs/job-2')
    })
  })

  describe('import', () => {
    it('importScan POSTs to /photos/import/scan', async () => {
      await importScan()
      expect(apiMock).toHaveBeenCalledWith('/photos/import/scan', { method: 'POST' })
    })

    it('getImportScanStatus GETs /photos/import/scan/status/:id', async () => {
      await getImportScanStatus('job-3')
      expect(apiMock).toHaveBeenCalledWith('/photos/import/scan/status/job-3')
    })
  })

  describe('filtered photos', () => {
    it('fetchFolderPhotosFiltered passes all filter params', async () => {
      await fetchFolderPhotosFiltered('f-40', {
        page: 1,
        per_page: 20,
        sort: 'taken_at',
        min_date: '2025-01-01',
        max_date: '2025-12-31',
        tag_id: 'tag-1',
      })
      expect(apiMock).toHaveBeenCalledWith('/photos/folders/f-40/photos', {
        params: {
          page: 1, per_page: 20, sort: 'taken_at',
          min_date: '2025-01-01', max_date: '2025-12-31', tag_id: 'tag-1',
        },
      })
    })
  })

  describe('tags', () => {
    it('fetchTags GETs /photos/tags without query', async () => {
      await fetchTags()
      expect(apiMock).toHaveBeenCalledWith('/photos/tags', { params: undefined })
    })

    it('fetchTags passes query param', async () => {
      await fetchTags('nature')
      expect(apiMock).toHaveBeenCalledWith('/photos/tags', { params: { q: 'nature' } })
    })

    it('createTag POSTs name', async () => {
      await createTag('holiday')
      expect(apiMock).toHaveBeenCalledWith('/photos/tags', {
        method: 'POST',
        body: { name: 'holiday' },
      })
    })

    it('deleteTag DELETEs /photos/tags/:id', async () => {
      await deleteTag('tag-5')
      expect(apiMock).toHaveBeenCalledWith('/photos/tags/tag-5', { method: 'DELETE' })
    })

    it('fetchPhotoTags GETs /photos/:id/tags', async () => {
      await fetchPhotoTags('p-10')
      expect(apiMock).toHaveBeenCalledWith('/photos/p-10/tags')
    })

    it('setPhotoTags PATCHes tag_ids', async () => {
      await setPhotoTags('p-11', ['tag-1', 'tag-2'])
      expect(apiMock).toHaveBeenCalledWith('/photos/p-11/tags', {
        method: 'PATCH',
        body: { tag_ids: ['tag-1', 'tag-2'] },
      })
    })
  })

  describe('error propagation', () => {
    it('propagates api errors', async () => {
      apiMock.mockRejectedValueOnce(Object.assign(new Error('not found'), { status: 404 }))
      await expect(getPhoto('missing')).rejects.toMatchObject({ status: 404 })
    })

    it('propagates apiUpload errors', async () => {
      apiUploadMock.mockRejectedValueOnce(Object.assign(new Error('too large'), { status: 413 }))
      await expect(uploadPhotos('f-1', [new File(['x'], 'x.jpg')])).rejects.toMatchObject({ status: 413 })
    })
  })
})
