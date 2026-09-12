import { api, apiUpload, BASE_URL } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type PhotoFolderTreeNode = components['schemas']['FolderTreeNode'] & {
  children: PhotoFolderTreeNode[]
}
export type PhotoFolderTree = Omit<components['schemas']['FolderTree'], 'items'> & {
  items: PhotoFolderTreeNode[]
}
export type PhotoFolder = components['schemas']['FolderPublic']
export type Photo = components['schemas']['PhotoPublic']
export type PhotoList = components['schemas']['PhotoList']
export type PhotoPermission = components['schemas']['app__schemas__photos__PermissionPublic']
export type UploadResultItem = components['schemas']['app__schemas__photos__UploadResultItem']
export type UploadResult = components['schemas']['app__schemas__photos__UploadResult']
export type PhotosModuleConfig = components['schemas']['PhotosModuleOut']
export type ShareLink = components['schemas']['ShareLinkPublic']
export type PhotoShareToken = components['schemas']['PhotoSharePublicForList']
export type FolderShareToken = components['schemas']['FolderSharePublicForList']
export type MySharesResponse = components['schemas']['MySharesResponse']
export type BulkActionResponse = components['schemas']['BulkActionResponse']
export type ZipJob = components['schemas']['ZipJobPublic']
export type PhotoTag = components['schemas']['TagPublic']
export type FolderShareLink = components['schemas']['FolderShareLinkPublic']
export type DeletedPhotoList = PhotoList

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────

export interface ImportScanResult {
  folders_created: number
  photos_imported: number
  skipped: number
  errors: string[]
}

export interface ImportScanJob {
  job_id: string
  status: string
}

export interface ImportScanStatus {
  job_id: string
  status: string
  result: ImportScanResult | null
}

export interface PublicFolderInfo {
  folder_name: string
  photos_count: number
  created_at: string
}

export interface FolderPhotosParams {
  page?: number
  per_page?: number
  sort?: 'created_at' | 'taken_at' | 'original_name'
  min_date?: string
  max_date?: string
  min_size?: number
  max_size?: number
  mime_type?: string
  tag_id?: string
  [key: string]: unknown
}

// ── API functions ──────────────────────────────────────────────────────────────

export function fetchFolderTree(): Promise<PhotoFolderTree> {
  return api<PhotoFolderTree>('/photos/folders/tree')
}

export function fetchFolder(folderId: string): Promise<PhotoFolder> {
  return api<PhotoFolder>(`/photos/folders/${folderId}`)
}

export function createFolder(body: { parent_id: string | null; name: string; description?: string | null }): Promise<PhotoFolder> {
  return api<PhotoFolder>('/photos/folders', { method: 'POST', body })
}

export function updateFolder(folderId: string, body: { name?: string; description?: string | null; cover_photo_id?: string | null }): Promise<PhotoFolder> {
  return api<PhotoFolder>(`/photos/folders/${folderId}`, { method: 'PATCH', body })
}

export function deleteFolder(folderId: string): Promise<void> {
  return api<void>(`/photos/folders/${folderId}`, { method: 'DELETE' })
}

export function fetchFolderPhotos(folderId: string, params?: { page?: number; per_page?: number; sort?: 'created_at' | 'taken_at' | 'original_name' }): Promise<PhotoList> {
  return api<PhotoList>(`/photos/folders/${folderId}/photos`, { params })
}

export function fetchRecentPhotos(limit = 8): Promise<Photo[]> {
  return api<Photo[]>('/photos/recent', { params: { limit } })
}

export function getPhoto(photoId: string): Promise<Photo> {
  return api<Photo>(`/photos/${photoId}`)
}

export function deletePhoto(photoId: string): Promise<void> {
  return api<void>(`/photos/${photoId}`, { method: 'DELETE' })
}

export function uploadPhotos(folderId: string, files: File[], signal?: AbortSignal): Promise<UploadResult> {
  const fd = new FormData()
  for (const f of files) fd.append('files', f, f.name)
  return apiUpload<UploadResult>(`/photos/folders/${folderId}/upload`, fd, 'POST', signal)
}

export function uploadPhotoXhr(
  folderId: string,
  file: File,
  onProgress: (pct: number) => void,
  signal?: AbortSignal,
): Promise<UploadResult> {
  return uploadPhotosBatchXhr(folderId, [file], onProgress, signal)
}

export function uploadPhotosBatchXhr(
  folderId: string,
  files: File[],
  onProgress: (pct: number) => void,
  signal?: AbortSignal,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const fd = new FormData()
    for (const f of files) fd.append('files', f, f.name)

    xhr.open('POST', `${BASE_URL}/photos/folders/${folderId}/upload`)
    xhr.withCredentials = true

    const csrfRaw = document.cookie
      .split(';')
      .map(c => c.trim())
      .find(c => c.startsWith('XSRF-TOKEN='))
    if (csrfRaw) {
      xhr.setRequestHeader('X-XSRF-TOKEN', decodeURIComponent(csrfRaw.slice('XSRF-TOKEN='.length)))
    }

    xhr.upload.onprogress = (e: ProgressEvent) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResult)
        } catch {
          reject(new Error('Invalid JSON response'))
        }
      } else {
        reject(Object.assign(new Error(`Upload failed: ${xhr.status}`), { status: xhr.status }))
      }
    }

    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.onabort = () => reject(Object.assign(new Error('AbortError'), { name: 'AbortError' }))

    if (signal) {
      if (signal.aborted) {
        xhr.abort()
        return
      }
      signal.addEventListener('abort', () => xhr.abort(), { once: true })
    }

    xhr.send(fd)
  })
}

export interface PhotoSubjectSearchResult {
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  email?: string | null
}

export function searchSubjects(q: string): Promise<PhotoSubjectSearchResult[]> {
  return api<PhotoSubjectSearchResult[]>(`/photos/users/search?q=${encodeURIComponent(q)}`)
}

export function fetchPermissions(folderId: string): Promise<{ items: PhotoPermission[] }> {
  return api<{ items: PhotoPermission[] }>(`/photos/folders/${folderId}/permissions`)
}

export function grantPermission(folderId: string, body: { subject_type: 'user' | 'group'; subject_id: string; subject_name: string; permission: 'viewer' | 'uploader' | 'manager' }): Promise<PhotoPermission> {
  return api<PhotoPermission>(`/photos/folders/${folderId}/permissions`, { method: 'POST', body })
}

export function revokePermission(folderId: string, subjectId: string): Promise<void> {
  return api<void>(`/photos/folders/${folderId}/permissions/${encodeURIComponent(subjectId)}`, { method: 'DELETE' })
}

export function thumbUrl(photoId: string, size: 200 | 400 | 600 | 1000 | 1600): string {
  return `/api/v1/photos/thumbnail/${photoId}/${size}`
}

export function thumbAvifUrl(photoId: string, size: 200 | 400 | 600 | 1000 | 1600): string {
  return `/api/v1/photos/thumbnail/${photoId}/${size}?format=avif`
}

export function originalUrl(photoId: string, download = false): string {
  return `/api/v1/photos/original/${photoId}${download ? '?download=1' : ''}`
}

export function createShareLink(photoId: string, expiresInDays: number | null = 7): Promise<ShareLink> {
  return api<ShareLink>(`/photos/${photoId}/share`, {
    method: 'POST',
    body: { expires_in_days: expiresInDays },
  })
}

export function publicPhotoInfoUrl(token: string): string {
  return `/api/v1/photos/public/${encodeURIComponent(token)}/info`
}

export function publicPhotoThumbUrl(token: string, size: 200 | 600 | 1600): string {
  return `/api/v1/photos/public/${encodeURIComponent(token)}/thumbnail/${size}`
}

export function publicPhotoAvifUrl(token: string, size: 200 | 600 | 1600): string {
  return `/api/v1/photos/public/${encodeURIComponent(token)}/thumbnail/${size}?format=avif`
}

export function publicPhotoFileUrl(token: string, download = false): string {
  return `/api/v1/photos/public/${encodeURIComponent(token)}/file${download ? '?download=1' : ''}`
}

// ── Trash & Restore ────────────────────────────────────────────────────────────

export function fetchDeletedPhotos(params?: { page?: number; per_page?: number }): Promise<DeletedPhotoList> {
  return api<DeletedPhotoList>('/photos/deleted', { params })
}

export function restorePhoto(photoId: string): Promise<Photo> {
  return api<Photo>(`/photos/${photoId}/restore`, { method: 'POST' })
}

export function purgePhoto(photoId: string): Promise<void> {
  return api<void>(`/photos/${photoId}/purge`, { method: 'DELETE' })
}

export function emptyTrash(): Promise<{ status: string }> {
  return api<{ status: string }>('/photos/trash/empty', { method: 'POST' })
}

export function fetchDeletedFolders(): Promise<PhotoFolder[]> {
  return api<PhotoFolder[]>('/photos/folders/deleted')
}

export function restoreFolder(folderId: string): Promise<PhotoFolder> {
  return api<PhotoFolder>(`/photos/folders/${folderId}/restore`, { method: 'POST' })
}

export function purgeFolder(folderId: string): Promise<void> {
  return api<void>(`/photos/folders/${folderId}/purge`, { method: 'DELETE' })
}

// ── Bulk actions ───────────────────────────────────────────────────────────────

export function bulkAction(body: { action: 'move' | 'delete'; photo_ids: string[]; target_folder_id?: string | null }): Promise<BulkActionResponse> {
  return api<BulkActionResponse>('/photos/bulk', { method: 'POST', body })
}

// ── ZIP download ───────────────────────────────────────────────────────────────

export function startFolderZip(folderId: string): Promise<ZipJob> {
  return api<ZipJob>(`/photos/folders/${folderId}/zip`, { method: 'POST' })
}

export function getZipJob(jobId: string): Promise<ZipJob> {
  return api<ZipJob>(`/photos/zip-jobs/${jobId}`)
}

export function zipJobDownloadUrl(jobId: string): string {
  return `/api/v1/photos/zip-jobs/${jobId}/download`
}

// ── Import from disk ──────────────────────────────────────────────────────────

export function importScan(): Promise<ImportScanJob> {
  return api<ImportScanJob>('/photos/import/scan', { method: 'POST' })
}

export function getImportScanStatus(jobId: string): Promise<ImportScanStatus> {
  return api<ImportScanStatus>(`/photos/import/scan/status/${jobId}`)
}

// ── Folder move ───────────────────────────────────────────────────────────────

export function moveFolder(folderId: string, newParentId: string | null): Promise<PhotoFolder> {
  return api<PhotoFolder>(`/photos/folders/${folderId}`, { method: 'PATCH', body: { parent_id: newParentId } })
}

// ── Filters ───────────────────────────────────────────────────────────────────

export function fetchFolderPhotosFiltered(folderId: string, params: FolderPhotosParams): Promise<PhotoList> {
  return api<PhotoList>(`/photos/folders/${folderId}/photos`, { params })
}

// ── Tags ──────────────────────────────────────────────────────────────────────

export function fetchTags(q?: string): Promise<{ items: PhotoTag[] }> {
  return api<{ items: PhotoTag[] }>('/photos/tags', { params: q ? { q } : undefined })
}

export function createTag(name: string): Promise<PhotoTag> {
  return api<PhotoTag>('/photos/tags', { method: 'POST', body: { name } })
}

export function deleteTag(tagId: string): Promise<void> {
  return api<void>(`/photos/tags/${tagId}`, { method: 'DELETE' })
}

export function fetchPhotoTags(photoId: string): Promise<PhotoTag[]> {
  return api<PhotoTag[]>(`/photos/${photoId}/tags`)
}

export function setPhotoTags(photoId: string, tagIds: string[]): Promise<PhotoTag[]> {
  return api<PhotoTag[]>(`/photos/${photoId}/tags`, { method: 'PATCH', body: { tag_ids: tagIds } })
}

// ── My Shares ─────────────────────────────────────────────────────────────────

export function fetchMyShares(): Promise<MySharesResponse> {
  return api<MySharesResponse>('/photos/my-shares')
}

export function revokePhotoShare(tokenId: string): Promise<void> {
  return api<void>(`/photos/my-shares/photo/${tokenId}`, { method: 'DELETE' })
}

export function revokeFolderShare(tokenId: string): Promise<void> {
  return api<void>(`/photos/my-shares/folder/${tokenId}`, { method: 'DELETE' })
}

// ── Folder Share ──────────────────────────────────────────────────────────────

export function createFolderShareLink(folderId: string, expiresInDays: number | null): Promise<FolderShareLink> {
  return api<FolderShareLink>(`/photos/folders/${folderId}/share`, {
    method: 'POST',
    body: { expires_in_days: expiresInDays },
  })
}

// ── Public folder ─────────────────────────────────────────────────────────────

export function publicFolderInfoUrl(token: string): string {
  return `/api/v1/photos/public-folder/${encodeURIComponent(token)}/info`
}

export function publicFolderPhotosUrl(token: string, page: number, perPage: number): string {
  return `/api/v1/photos/public-folder/${encodeURIComponent(token)}/photos?page=${page}&per_page=${perPage}`
}

export function publicFolderThumbUrl(token: string, photoId: string, size: 200 | 400 | 600 | 1000 | 1600): string {
  return `/api/v1/photos/public-folder/${encodeURIComponent(token)}/thumbnail/${photoId}/${size}`
}

export function publicFolderAvifUrl(token: string, photoId: string, size: 200 | 400 | 600 | 1000 | 1600): string {
  return `/api/v1/photos/public-folder/${encodeURIComponent(token)}/thumbnail/${photoId}/${size}?format=avif`
}
