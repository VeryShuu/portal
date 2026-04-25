import { api, apiUpload } from './index'

export interface PhotoFolderTreeNode {
  id: string
  parent_id: string | null
  name: string
  slug: string
  path: string
  permission: string | null
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

export function thumbUrl(photoId: string, size: 200 | 600 | 1600): string {
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
