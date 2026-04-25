import { api, apiUpload } from './index'

export interface PhotoFolderTreeNode {
  id: string
  parent_id: string | null
  name: string
  slug: string
  path: string
  permission: string | null
  cover_photo_id?: string | null
  children: PhotoFolderTreeNode[]
}

export interface PhotoFolderTree {
  items: PhotoFolderTreeNode[]
}

export interface PhotoFolder {
  id: string
  parent_id: string | null
  name: string
  slug: string
  path: string
  description: string | null
  cover_photo_id: string | null
  photos_count: number
  children_count: number
  permission: string | null
  created_at: string
  updated_at: string
}

export interface Photo {
  id: string
  folder_id: string
  folder_path: string | null
  filename: string
  original_name: string
  size_bytes: number
  mime_type: string | null
  width: number | null
  height: number | null
  taken_at: string | null
  description: string | null
  processed: boolean
  uploaded_by: string | null
  created_at: string
}

export interface PhotoList {
  items: Photo[]
  total: number
  page: number
  per_page: number
}

export interface PhotoPermission {
  id: string
  folder_id: string
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  permission: 'viewer' | 'uploader' | 'manager'
  granted_by: string | null
  created_at: string
}

export interface UploadResultItem {
  photo_id: string | null
  original_name: string
  ok: boolean
  error: string | null
}

export interface UploadResult {
  items: UploadResultItem[]
}

export interface PhotosModuleConfig {
  enabled: boolean
  widget_limit: number
  max_size_mb: number
  allowed_mime: string[]
  strip_gps: boolean
}

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

export function uploadPhotos(folderId: string, files: File[]): Promise<UploadResult> {
  const fd = new FormData()
  for (const f of files) fd.append('files', f, f.name)
  return apiUpload<UploadResult>(`/photos/folders/${folderId}/upload`, fd, 'POST')
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

export function originalUrl(photoId: string, download = false): string {
  return `/api/v1/photos/original/${photoId}${download ? '?download=1' : ''}`
}

export interface ShareLink {
  id: string
  photo_id: string
  token: string
  url: string
  created_at: string
  expires_at: string | null
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

export function publicPhotoFileUrl(token: string, download = false): string {
  return `/api/v1/photos/public/${encodeURIComponent(token)}/file${download ? '?download=1' : ''}`
}

// ── Trash & Restore ────────────────────────────────────────────────────────

export interface DeletedPhotoList extends PhotoList {}

export function fetchDeletedPhotos(params?: { page?: number; per_page?: number }): Promise<DeletedPhotoList> {
  return api<DeletedPhotoList>('/photos/deleted', { params })
}

export function restorePhoto(photoId: string): Promise<Photo> {
  return api<Photo>(`/photos/${photoId}/restore`, { method: 'POST' })
}

export function fetchDeletedFolders(): Promise<PhotoFolder[]> {
  return api<PhotoFolder[]>('/photos/folders/deleted')
}

export function restoreFolder(folderId: string): Promise<PhotoFolder> {
  return api<PhotoFolder>(`/photos/folders/${folderId}/restore`, { method: 'POST' })
}

// ── Bulk actions ───────────────────────────────────────────────────────────

export interface BulkActionResponse {
  processed: number
  errors: string[]
}

export function bulkAction(body: { action: 'move' | 'delete'; photo_ids: string[]; target_folder_id?: string | null }): Promise<BulkActionResponse> {
  return api<BulkActionResponse>('/photos/bulk', { method: 'POST', body })
}

// ── ZIP download ───────────────────────────────────────────────────────────

export interface ZipJob {
  id: string
  folder_id: string
  status: 'pending' | 'processing' | 'done' | 'error'
  created_at: string
  expires_at: string | null
  download_url: string | null
}

export function startFolderZip(folderId: string): Promise<ZipJob> {
  return api<ZipJob>(`/photos/folders/${folderId}/zip`, { method: 'POST' })
}

export function getZipJob(jobId: string): Promise<ZipJob> {
  return api<ZipJob>(`/photos/zip-jobs/${jobId}`)
}

export function zipJobDownloadUrl(jobId: string): string {
  return `/api/v1/photos/zip-jobs/${jobId}/download`
}

// ── Import from disk ──────────────────────────────────────────────────────

export interface ImportScanResult {
  folders_created: number
  photos_imported: number
  skipped: number
  errors: string[]
}

export function importScan(): Promise<ImportScanResult> {
  return api<ImportScanResult>('/photos/import/scan', { method: 'POST' })
}

// ── Folder move ───────────────────────────────────────────────────────────

export function moveFolder(folderId: string, newParentId: string | null): Promise<PhotoFolder> {
  return api<PhotoFolder>(`/photos/folders/${folderId}`, { method: 'PATCH', body: { parent_id: newParentId } })
}

// ── Filters ───────────────────────────────────────────────────────────────

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
}

export function fetchFolderPhotosFiltered(folderId: string, params: FolderPhotosParams): Promise<PhotoList> {
  return api<PhotoList>(`/photos/folders/${folderId}/photos`, { params })
}

// ── Tags ──────────────────────────────────────────────────────────────────

export interface PhotoTag {
  id: string
  name: string
  slug: string
  usage_count?: number
}

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

// ── My Shares ─────────────────────────────────────────────────────────────

export interface PhotoShareToken {
  id: string
  photo_id: string
  token: string
  url: string
  expires_at: string | null
}

export interface FolderShareToken {
  id: string
  folder_id: string
  token: string
  url: string
  expires_at: string | null
  folder_name?: string
}

export interface MySharesResponse {
  photo_tokens: PhotoShareToken[]
  folder_tokens: FolderShareToken[]
}

export function fetchMyShares(): Promise<MySharesResponse> {
  return api<MySharesResponse>('/photos/my-shares')
}

export function revokePhotoShare(tokenId: string): Promise<void> {
  return api<void>(`/photos/my-shares/photo/${tokenId}`, { method: 'DELETE' })
}

export function revokeFolderShare(tokenId: string): Promise<void> {
  return api<void>(`/photos/my-shares/folder/${tokenId}`, { method: 'DELETE' })
}

// ── Folder Share ──────────────────────────────────────────────────────────

export interface FolderShareLink {
  id: string
  folder_id: string
  token: string
  url: string
  expires_at: string | null
}

export function createFolderShareLink(folderId: string, expiresInDays: number | null): Promise<FolderShareLink> {
  return api<FolderShareLink>(`/photos/folders/${folderId}/share`, {
    method: 'POST',
    body: { expires_in_days: expiresInDays },
  })
}

// ── Public folder ─────────────────────────────────────────────────────────

export interface PublicFolderInfo {
  folder_name: string
  photos_count: number
  created_at: string
}

export function publicFolderInfoUrl(token: string): string {
  return `/api/v1/photos/public-folder/${encodeURIComponent(token)}/info`
}

export function publicFolderPhotosUrl(token: string, page: number, perPage: number): string {
  return `/api/v1/photos/public-folder/${encodeURIComponent(token)}/photos?page=${page}&per_page=${perPage}`
}

export function publicFolderThumbUrl(token: string, photoId: string, size: 200 | 400 | 600 | 1000 | 1600): string {
  return `/api/v1/photos/public-folder/${encodeURIComponent(token)}/thumbnail/${photoId}/${size}`
}
