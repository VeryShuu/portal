import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()
const apiUploadMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
  apiUpload: (...args: unknown[]) => apiUploadMock(...args),
}))

import {
  BULK_DOWNLOAD_LIMIT,
  BULK_MAX_FILES,
  bulkDeleteFiles,
  bulkMoveFiles,
  createFolder,
  deleteFile,
  deleteFolder,
  downloadFile,
  fetchFolderDetail,
  fetchFolderTree,
  fetchPermissions,
  fileIcon,
  formatFileSize,
  grantPermission,
  isCollaboraFile,
  isPreviewableImage,
  isPreviewablePdf,
  openInCollabora,
  previewFile,
  revokePermission,
  setFolderInheritance,
  syncFromNextcloud,
  updateFolder,
  uploadFiles,
  type NCItem,
} from '../../src/api/files'

function makeItem(overrides: Partial<NCItem> = {}): NCItem {
  return {
    name: 'file.txt',
    nc_path: '/path/file.txt',
    is_dir: false,
    size_bytes: 1024,
    mime_type: 'text/plain',
    last_modified: null,
    etag: null,
    uploaded_at: null,
    uploaded_by: null,
    ...overrides,
  }
}

describe('files API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiUploadMock.mockReset()
    apiMock.mockResolvedValue({})
    apiUploadMock.mockResolvedValue({})
  })

  describe('fetchFolderTree', () => {
    it('GETs /files/tree without params when parentId is absent', async () => {
      await fetchFolderTree()
      expect(apiMock).toHaveBeenCalledWith('/files/tree', { params: {} })
    })

    it('passes parent_id param when provided', async () => {
      await fetchFolderTree('folder-1')
      expect(apiMock).toHaveBeenCalledWith('/files/tree', { params: { parent_id: 'folder-1' } })
    })

    it('ignores null parentId', async () => {
      await fetchFolderTree(null)
      expect(apiMock).toHaveBeenCalledWith('/files/tree', { params: {} })
    })
  })

  describe('fetchFolderDetail', () => {
    it('GETs /files/folders/:id', async () => {
      await fetchFolderDetail('f-99')
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-99')
    })
  })

  describe('createFolder', () => {
    it('POSTs body to /files/folders', async () => {
      await createFolder({ name: 'docs', parent_id: 'p-1', description: 'My docs' })
      expect(apiMock).toHaveBeenCalledWith('/files/folders', {
        method: 'POST',
        body: { name: 'docs', parent_id: 'p-1', description: 'My docs' },
      })
    })
  })

  describe('updateFolder', () => {
    it('PATCHes /files/folders/:id', async () => {
      await updateFolder('f-1', { name: 'renamed', description: null })
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-1', {
        method: 'PATCH',
        body: { name: 'renamed', description: null },
      })
    })
  })

  describe('deleteFolder', () => {
    it('DELETEs /files/folders/:id', async () => {
      await deleteFolder('f-2')
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-2', { method: 'DELETE' })
    })
  })

  describe('uploadFiles', () => {
    it('sends FormData with all files via apiUpload', async () => {
      const f1 = new File(['a'], 'a.txt', { type: 'text/plain' })
      const f2 = new File(['b'], 'b.png', { type: 'image/png' })
      await uploadFiles('f-3', [f1, f2])
      expect(apiUploadMock).toHaveBeenCalledTimes(1)
      const [path, fd, method] = apiUploadMock.mock.calls[0]
      expect(path).toBe('/files/folders/f-3/upload')
      expect(method).toBe('POST')
      expect(fd).toBeInstanceOf(FormData)
      const entries = (fd as FormData).getAll('files')
      expect(entries).toHaveLength(2)
    })
  })

  describe('downloadFile', () => {
    it('returns encoded download URL', () => {
      const url = downloadFile('f-1', 'my file.pdf')
      expect(url).toBe('/api/v1/files/download?folder_id=f-1&filename=my%20file.pdf')
    })
  })

  describe('previewFile', () => {
    it('returns encoded preview URL', () => {
      const url = previewFile('f-2', 'image & more.png')
      expect(url).toBe('/api/v1/files/preview?folder_id=f-2&filename=image%20%26%20more.png')
    })
  })

  describe('deleteFile', () => {
    it('DELETEs /files/file with query params', async () => {
      await deleteFile('f-5', 'report.xlsx')
      expect(apiMock).toHaveBeenCalledWith('/files/file', {
        method: 'DELETE',
        params: { folder_id: 'f-5', filename: 'report.xlsx' },
      })
    })
  })

  describe('openInCollabora', () => {
    it('POSTs to /files/open with params', async () => {
      await openInCollabora('f-6', 'doc.docx')
      expect(apiMock).toHaveBeenCalledWith('/files/open', {
        method: 'POST',
        params: { folder_id: 'f-6', filename: 'doc.docx' },
      })
    })
  })

  describe('fetchPermissions', () => {
    it('GETs /files/folders/:id/permissions', async () => {
      await fetchPermissions('f-7')
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-7/permissions')
    })
  })

  describe('grantPermission', () => {
    it('POSTs permission body', async () => {
      await grantPermission('f-8', {
        subject_type: 'user',
        subject_id: 'u-1',
        subject_name: 'Alice',
        permission: 'editor',
      })
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-8/permissions', {
        method: 'POST',
        body: { subject_type: 'user', subject_id: 'u-1', subject_name: 'Alice', permission: 'editor' },
      })
    })
  })

  describe('revokePermission', () => {
    it('DELETEs nested permission URL', async () => {
      await revokePermission('f-9', 'perm-1')
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-9/permissions/perm-1', { method: 'DELETE' })
    })
  })

  describe('setFolderInheritance', () => {
    it('PATCHes inheritance flag', async () => {
      await setFolderInheritance('f-10', true)
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-10/inheritance', {
        method: 'PATCH',
        body: { inherit_permissions: true },
      })
    })

    it('can set inheritance to false', async () => {
      await setFolderInheritance('f-11', false)
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-11/inheritance', {
        method: 'PATCH',
        body: { inherit_permissions: false },
      })
    })
  })

  describe('syncFromNextcloud', () => {
    it('POSTs to /files/sync', async () => {
      await syncFromNextcloud()
      expect(apiMock).toHaveBeenCalledWith('/files/sync', { method: 'POST' })
    })
  })

  describe('bulkDeleteFiles', () => {
    it('POSTs filenames list', async () => {
      await bulkDeleteFiles('f-12', ['a.txt', 'b.pdf'])
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-12/bulk-delete', {
        method: 'POST',
        body: { filenames: ['a.txt', 'b.pdf'] },
      })
    })
  })

  describe('bulkMoveFiles', () => {
    it('POSTs filenames and target folder', async () => {
      await bulkMoveFiles('f-13', ['c.txt'], 'f-dest')
      expect(apiMock).toHaveBeenCalledWith('/files/folders/f-13/bulk-move', {
        method: 'POST',
        body: { filenames: ['c.txt'], target_folder_id: 'f-dest' },
      })
    })
  })

  describe('formatFileSize', () => {
    it('formats bytes', () => {
      expect(formatFileSize(500)).toBe('500 B')
    })

    it('formats kilobytes', () => {
      expect(formatFileSize(2048)).toBe('2.0 KB')
    })

    it('formats megabytes', () => {
      expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MB')
    })

    it('formats gigabytes', () => {
      expect(formatFileSize(2 * 1024 * 1024 * 1024)).toBe('2.00 GB')
    })

    it('formats exactly 1023 bytes as B', () => {
      expect(formatFileSize(1023)).toBe('1023 B')
    })
  })

  describe('isPreviewableImage', () => {
    it('returns false for directories', () => {
      expect(isPreviewableImage(makeItem({ is_dir: true, name: 'folder' }))).toBe(false)
    })

    it('detects by extension', () => {
      expect(isPreviewableImage(makeItem({ name: 'photo.jpg', mime_type: null }))).toBe(true)
      expect(isPreviewableImage(makeItem({ name: 'photo.PNG', mime_type: null }))).toBe(true)
      expect(isPreviewableImage(makeItem({ name: 'anim.gif', mime_type: null }))).toBe(true)
      expect(isPreviewableImage(makeItem({ name: 'pic.webp', mime_type: null }))).toBe(true)
    })

    it('detects by mime type', () => {
      expect(isPreviewableImage(makeItem({ name: 'unknown', mime_type: 'image/svg+xml' }))).toBe(true)
    })

    it('returns false for non-image file', () => {
      expect(isPreviewableImage(makeItem({ name: 'doc.pdf', mime_type: 'application/pdf' }))).toBe(false)
    })
  })

  describe('isPreviewablePdf', () => {
    it('returns false for directories', () => {
      expect(isPreviewablePdf(makeItem({ is_dir: true, name: 'dir' }))).toBe(false)
    })

    it('detects pdf by extension', () => {
      expect(isPreviewablePdf(makeItem({ name: 'report.pdf', mime_type: null }))).toBe(true)
    })

    it('detects pdf by mime type', () => {
      expect(isPreviewablePdf(makeItem({ name: 'report', mime_type: 'application/pdf' }))).toBe(true)
    })

    it('returns false for non-pdf', () => {
      expect(isPreviewablePdf(makeItem({ name: 'image.png', mime_type: 'image/png' }))).toBe(false)
    })
  })

  describe('isCollaboraFile', () => {
    it('returns false for directories', () => {
      expect(isCollaboraFile(makeItem({ is_dir: true, name: 'dir' }))).toBe(false)
    })

    it.each(['odt', 'odp', 'ods', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'csv'])(
      'detects %s as Collabora file',
      (ext) => {
        expect(isCollaboraFile(makeItem({ name: `file.${ext}` }))).toBe(true)
      },
    )

    it('returns false for non-collabora extension', () => {
      expect(isCollaboraFile(makeItem({ name: 'archive.zip' }))).toBe(false)
    })
  })

  describe('fileIcon', () => {
    it('returns folder icon for directories', () => {
      expect(fileIcon(makeItem({ is_dir: true, name: 'dir' }))).toBe('📁')
    })

    it('returns image icon for image files', () => {
      expect(fileIcon(makeItem({ name: 'pic.jpg', mime_type: 'image/jpeg' }))).toBe('🖼️')
    })

    it('returns video icon for video files', () => {
      expect(fileIcon(makeItem({ name: 'vid.mp4', mime_type: 'video/mp4' }))).toBe('🎬')
    })

    it('returns audio icon for audio files', () => {
      expect(fileIcon(makeItem({ name: 'song.mp3', mime_type: 'audio/mpeg' }))).toBe('🎵')
    })

    it('returns pdf icon for pdf files', () => {
      expect(fileIcon(makeItem({ name: 'doc.pdf', mime_type: 'application/pdf' }))).toBe('📄')
    })

    it('returns word icon for docx files', () => {
      expect(fileIcon(makeItem({ name: 'report.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))).toBe('📝')
    })

    it('returns spreadsheet icon for xlsx', () => {
      expect(fileIcon(makeItem({ name: 'sheet.xlsx', mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))).toBe('📊')
    })

    it('returns archive icon for zip', () => {
      expect(fileIcon(makeItem({ name: 'arch.zip', mime_type: null }))).toBe('🗜️')
    })

    it('returns text icon for txt', () => {
      expect(fileIcon(makeItem({ name: 'notes.txt', mime_type: 'text/plain' }))).toBe('📃')
    })

    it('returns code icon for js files', () => {
      expect(fileIcon(makeItem({ name: 'app.js', mime_type: null }))).toBe('💻')
    })

    it('returns generic icon for unknown extension', () => {
      expect(fileIcon(makeItem({ name: 'mystery.xyz', mime_type: null }))).toBe('📎')
    })
  })

  describe('constants', () => {
    it('BULK_DOWNLOAD_LIMIT is 20', () => {
      expect(BULK_DOWNLOAD_LIMIT).toBe(20)
    })

    it('BULK_MAX_FILES is 100', () => {
      expect(BULK_MAX_FILES).toBe(100)
    })
  })

  describe('error propagation', () => {
    it('propagates api errors', async () => {
      apiMock.mockRejectedValueOnce(Object.assign(new Error('forbidden'), { status: 403 }))
      await expect(fetchFolderTree()).rejects.toMatchObject({ status: 403 })
    })

    it('propagates apiUpload errors', async () => {
      apiUploadMock.mockRejectedValueOnce(Object.assign(new Error('too large'), { status: 413 }))
      await expect(uploadFiles('f-1', [new File(['x'], 'x.txt')])).rejects.toMatchObject({ status: 413 })
    })
  })
})
