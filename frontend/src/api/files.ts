import { api, apiUpload } from './index'

export interface FileFolderPublic {
  id: string
  parent_id: string | null
  name: string
  nc_path: string
  description: string | null
  permission: 'viewer' | 'editor' | 'manager' | null
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
  children: FileFolderTreeNode[]
}

export interface FileFolderTree {
  items: FileFolderTreeNode[]
}

export interface NCItem {
  name: string
  nc_path: string
  is_dir: boolean
  size_bytes: number
  mime_type: string | null
  last_modified: string | null
  etag: string | null
}

export interface FolderDetailResponse {
  folder: FileFolderPublic
  items: NCItem[]
  breadcrumbs: FileFolderPublic[]
}

export interface FilePermission {
  id: string
  folder_id: string
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  permission: 'viewer' | 'editor' | 'manager'
  granted_by: string | null
  created_at: string
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

export function downloadFile(folderId: string, filePath: string): string {
  return `/api/v1/files/download?folder_id=${encodeURIComponent(folderId)}&file_path=${encodeURIComponent(filePath)}`
}

export function deleteFile(folderId: string, filePath: string): Promise<void> {
  return api<void>('/files/file', {
    method: 'DELETE',
    params: { folder_id: folderId, file_path: filePath },
  })
}

export function openInCollabora(folderId: string, filePath: string): Promise<FileOpenResponse> {
  return api<FileOpenResponse>('/files/open', {
    method: 'POST',
    params: { folder_id: folderId, file_path: filePath },
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

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function fileIcon(item: NCItem): string {
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

const COLLABORA_EXTS = new Set([
  'odt', 'odp', 'ods', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'csv',
])

export function isCollaboraFile(item: NCItem): boolean {
  if (item.is_dir) return false
  const ext = item.name.split('.').pop()?.toLowerCase() ?? ''
  return COLLABORA_EXTS.has(ext)
}
