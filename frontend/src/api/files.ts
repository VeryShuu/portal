import { api, apiUpload } from './index'

export interface FileFolderPublic {
  id: string
  parent_id: string | null
  name: string
  nc_path: string
  description: string | null
  permission: 'viewer' | 'editor' | 'manager' | null
  inherit_permissions: boolean
  children_count: number
  created_at: string
  updated_at: string
}

export interface FileFolderTreeNode {
  id: string
  parent_id: string | null
  name: string
  nc_path: string
  permission: 'viewer' | 'editor' | 'manager' | null
  inherit_permissions: boolean
  children: FileFolderTreeNode[]
}

export interface FileFolderTree {
  items: FileFolderTreeNode[]
}

export interface UploadedByPublic {
  id: string
  full_name: string
  avatar_url: string | null
}

export interface NCItem {
  name: string
  nc_path: string
  is_dir: boolean
  size_bytes: number
  mime_type: string | null
  last_modified: string | null
  etag: string | null
  uploaded_at: string | null
  uploaded_by: UploadedByPublic | null
}

export interface FolderDetailResponse {
  folder: FileFolderPublic
  items: NCItem[]
  breadcrumbs: FileFolderPublic[]
}

export interface FilePermission {
  id: string | null
  folder_id: string
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  permission: 'viewer' | 'editor' | 'manager'
  granted_by?: string | null
  created_at?: string | null
  email?: string | null
  is_creator?: boolean
}

export interface PermissionList {
  items: FilePermission[]
}

export interface UploadResultItem {
  name: string
  nc_path: string
  size_bytes: number
  success: boolean
  error: string | null
}

export interface UploadResult {
  uploaded: UploadResultItem[]
  failed: UploadResultItem[]
}

export interface FileOpenResponse {
  type: string
  url: string
  display_name: string | null
  can_write: boolean
}

export function fetchFolderTree(parentId?: string | null): Promise<FileFolderTree> {
  const params: Record<string, string> = {}
  if (parentId) params.parent_id = parentId
  return api<FileFolderTree>('/files/tree', { params })
}

export function fetchFolderDetail(folderId: string): Promise<FolderDetailResponse> {
  return api<FolderDetailResponse>(`/files/folders/${folderId}`)
}

export function createFolder(body: {
  name: string
  parent_id?: string | null
  description?: string | null
}): Promise<FileFolderPublic> {
  return api<FileFolderPublic>('/files/folders', { method: 'POST', body })
}

export function updateFolder(
  folderId: string,
  body: { name?: string; description?: string | null }
): Promise<FileFolderPublic> {
  return api<FileFolderPublic>(`/files/folders/${folderId}`, { method: 'PATCH', body })
}

export function deleteFolder(folderId: string): Promise<void> {
  return api<void>(`/files/folders/${folderId}`, { method: 'DELETE' })
}

export function uploadFiles(folderId: string, files: File[]): Promise<UploadResult> {
  const fd = new FormData()
  for (const f of files) fd.append('files', f, f.name)
  return apiUpload<UploadResult>(`/files/folders/${folderId}/upload`, fd, 'POST')
}

export function downloadFile(folderId: string, filename: string): string {
  return `/api/v1/files/download?folder_id=${encodeURIComponent(folderId)}&filename=${encodeURIComponent(filename)}`
}

export function previewFile(folderId: string, filename: string): string {
  return `/api/v1/files/preview?folder_id=${encodeURIComponent(folderId)}&filename=${encodeURIComponent(filename)}`
}

const PREVIEW_IMAGE_EXTS = new Set(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'avif', 'svg'])

export function isPreviewableImage(item: NCItem): boolean {
  if (item.is_dir) return false
  const ext = item.name.split('.').pop()?.toLowerCase() ?? ''
  const mime = item.mime_type ?? ''
  return PREVIEW_IMAGE_EXTS.has(ext) || mime.startsWith('image/')
}

export function isPreviewablePdf(item: NCItem): boolean {
  if (item.is_dir) return false
  const ext = item.name.split('.').pop()?.toLowerCase() ?? ''
  const mime = item.mime_type ?? ''
  return ext === 'pdf' || mime === 'application/pdf'
}

export function deleteFile(folderId: string, filename: string): Promise<void> {
  return api<void>('/files/file', {
    method: 'DELETE',
    params: { folder_id: folderId, filename },
  })
}

export function openInCollabora(folderId: string, filename: string): Promise<FileOpenResponse> {
  return api<FileOpenResponse>('/files/open', {
    method: 'POST',
    params: { folder_id: folderId, filename },
  })
}

export function fetchPermissions(folderId: string): Promise<PermissionList> {
  return api<PermissionList>(`/files/folders/${folderId}/permissions`)
}

export function grantPermission(
  folderId: string,
  body: {
    subject_type: 'user' | 'group'
    subject_id: string
    subject_name: string
    permission: 'viewer' | 'editor' | 'manager'
  }
): Promise<FilePermission> {
  return api<FilePermission>(`/files/folders/${folderId}/permissions`, { method: 'POST', body })
}

export function revokePermission(folderId: string, permId: string): Promise<void> {
  return api<void>(`/files/folders/${folderId}/permissions/${permId}`, { method: 'DELETE' })
}

export function setFolderInheritance(
  folderId: string,
  inheritPermissions: boolean
): Promise<FileFolderPublic> {
  return api<FileFolderPublic>(`/files/folders/${folderId}/inheritance`, {
    method: 'PATCH',
    body: { inherit_permissions: inheritPermissions },
  })
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export type FileIcon =
  | { kind: 'svg'; url: string; alt: string }
  | { kind: 'emoji'; char: string }

export function fileIconEmoji(item: NCItem): string {
  if (item.is_dir) return '📁'
  const mime = item.mime_type ?? ''
  const ext = item.name.split('.').pop()?.toLowerCase() ?? ''
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'avif'].includes(ext) || mime.startsWith('image/')) return '🖼️'
  if (['mp4', 'avi', 'mov', 'mkv', 'webm'].includes(ext) || mime.startsWith('video/')) return '🎬'
  if (['mp3', 'wav', 'ogg', 'flac', 'aac'].includes(ext) || mime.startsWith('audio/')) return '🎵'
  if (ext === 'pdf' || mime === 'application/pdf') return '📄'
  if (['doc', 'docx', 'odt', 'rtf'].includes(ext) || mime.includes('word') || mime.includes('opendocument.text')) return '📝'
  if (['xls', 'xlsx', 'ods', 'csv'].includes(ext) || mime.includes('excel') || mime.includes('spreadsheet')) return '📊'
  if (['ppt', 'pptx', 'odp'].includes(ext) || mime.includes('presentation') || mime.includes('powerpoint')) return '📊'
  if (['zip', 'tar', 'gz', 'rar', '7z', 'bz2', 'xz'].includes(ext)) return '🗜️'
  if (['txt', 'md', 'log', 'json', 'xml', 'yaml', 'yml', 'toml', 'ini', 'cfg'].includes(ext) || mime.startsWith('text/')) return '📃'
  if (['js', 'ts', 'py', 'java', 'cs', 'cpp', 'c', 'h', 'go', 'rs', 'php', 'rb', 'swift', 'kt'].includes(ext)) return '💻'
  return '📎'
}

export function fileExt(item: NCItem): string {
  return item.name.split('.').pop()?.toLowerCase() ?? ''
}

export function fileIcon(item: NCItem, customUrlFor?: (ext: string) => string | null): FileIcon {
  if (!item.is_dir && customUrlFor) {
    const ext = fileExt(item)
    if (ext) {
      const url = customUrlFor(ext)
      if (url) return { kind: 'svg', url, alt: ext.toUpperCase() }
    }
  }
  return { kind: 'emoji', char: fileIconEmoji(item) }
}

const COLLABORA_EXTS = new Set([
  'odt', 'odp', 'ods', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'csv',
])

export function isCollaboraFile(item: NCItem): boolean {
  if (item.is_dir) return false
  const ext = item.name.split('.').pop()?.toLowerCase() ?? ''
  return COLLABORA_EXTS.has(ext)
}

export interface NcSyncReport {
  created: number
  skipped: number
  errors: string[]
}

export function syncFromNextcloud(): Promise<NcSyncReport> {
  return api<NcSyncReport>('/files/sync', { method: 'POST' })
}

export interface BulkDeleteResultItem {
  name: string
  success: boolean
  error: string | null
}

export interface BulkDeleteResult {
  deleted: BulkDeleteResultItem[]
  failed: BulkDeleteResultItem[]
}

export interface BulkMoveResultItem extends BulkDeleteResultItem {
  new_name: string | null
}

export interface BulkMoveResult {
  moved: BulkMoveResultItem[]
  failed: BulkMoveResultItem[]
}

export function bulkDeleteFiles(folderId: string, filenames: string[]): Promise<BulkDeleteResult> {
  return api<BulkDeleteResult>(`/files/folders/${folderId}/bulk-delete`, {
    method: 'POST',
    body: { filenames },
  })
}

export function bulkMoveFiles(
  folderId: string,
  filenames: string[],
  targetFolderId: string
): Promise<BulkMoveResult> {
  return api<BulkMoveResult>(`/files/folders/${folderId}/bulk-move`, {
    method: 'POST',
    body: { filenames, target_folder_id: targetFolderId },
  })
}

export const BULK_DOWNLOAD_LIMIT = 20
export const BULK_MAX_FILES = 100

// ── Per-file sharing (sharing.md) ───────────────────────────────────────────

export interface FileSharePublic {
  id: string
  folder_id: string
  filename: string
  nc_path: string
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  permission: 'viewer' | 'editor'
  shared_by: string | null
  created_at: string
  expires_at: string | null
}

export interface FileShareList {
  items: FileSharePublic[]
}

export interface MyFileShare {
  id: string
  folder_id: string
  filename: string
  nc_path: string
  folder_name: string
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  permission: 'viewer' | 'editor'
  created_at: string
  expires_at: string | null
}

export interface MyFileShareList {
  items: MyFileShare[]
}

export interface SharedFile {
  id: string
  folder_id: string
  filename: string
  nc_path: string
  folder_name: string
  permission: 'viewer' | 'editor'
  shared_by_name: string | null
  created_at: string
  expires_at: string | null
}

export interface SharedFileList {
  items: SharedFile[]
}

export interface AdminFileShare {
  id: string
  folder_id: string
  filename: string
  nc_path: string
  folder_name: string | null
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  permission: 'viewer' | 'editor'
  shared_by: string | null
  shared_by_name: string | null
  created_at: string
  expires_at: string | null
  revoked_at: string | null
}

export interface AdminFileShareList {
  items: AdminFileShare[]
  total: number
  limit: number
  offset: number
}

export function createFileShare(
  folderId: string,
  filename: string,
  body: {
    subject_type: 'user' | 'group'
    subject_id: string
    subject_name: string
    permission: 'viewer' | 'editor'
    expires_in_days?: number | null
  }
): Promise<FileSharePublic> {
  return api<FileSharePublic>(
    `/files/folders/${folderId}/files/${encodeURIComponent(filename)}/shares`,
    { method: 'POST', body }
  )
}

export function fetchFileShares(folderId: string, filename: string): Promise<FileShareList> {
  return api<FileShareList>(
    `/files/folders/${folderId}/files/${encodeURIComponent(filename)}/shares`
  )
}

export function revokeFileShare(
  folderId: string,
  filename: string,
  shareId: string
): Promise<void> {
  return api<void>(
    `/files/folders/${folderId}/files/${encodeURIComponent(filename)}/shares/${shareId}`,
    { method: 'DELETE' }
  )
}

export function fetchMyShares(): Promise<MyFileShareList> {
  return api<MyFileShareList>('/files/shares/my')
}

export function fetchSharedWithMe(): Promise<SharedFileList> {
  return api<SharedFileList>('/files/shares/shared-with-me')
}

export function fetchAdminShares(params: {
  subject_id?: string
  folder_id?: string
  active_only?: boolean
  limit?: number
  offset?: number
}): Promise<AdminFileShareList> {
  const query: Record<string, string> = {}
  if (params.subject_id) query.subject_id = params.subject_id
  if (params.folder_id) query.folder_id = params.folder_id
  if (params.active_only) query.active_only = 'true'
  if (params.limit != null) query.limit = String(params.limit)
  if (params.offset != null) query.offset = String(params.offset)
  return api<AdminFileShareList>('/files/admin/shares', { params: query })
}

export interface FilesSubjectSearchResult {
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  email?: string | null
}

export function searchFilesSubjects(q: string): Promise<FilesSubjectSearchResult[]> {
  return api<FilesSubjectSearchResult[]>('/files/users/search', { params: { q } })
}
