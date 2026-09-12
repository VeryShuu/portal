import { api, apiUpload } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json
//
// Gen-схемы отдают permission/subject_type как string (backend не аннотирован
// Literal) и часть nullable-полей — опциональной. Consumers сравнивают эти поля
// с литералами / передают в helpers `(p: string) => ...`, поэтому прямых
// сужений не требуется; исключения отмечены ниже.

export type FileFolderPublic = components['schemas']['FileFolderPublic']

// children в gen-схеме optional, backend всегда отдаёт массив; рекурсивные
// обходы (useFilesData, useFilesBulkOps, EntryEditDrawer) требуют обязательности.
export type FileFolderTreeNode = components['schemas']['FileFolderTreeNode'] & {
  children: FileFolderTreeNode[]
}

export type FileFolderTree = Omit<components['schemas']['FileFolderTree'], 'items'> & {
  items: FileFolderTreeNode[]
}

export type UploadedByPublic = components['schemas']['UploadedByPublic']
export type NCItem = components['schemas']['NCItem']
export type FolderDetailResponse = components['schemas']['FolderDetailResponse']
export type FilePermission = components['schemas']['app__schemas__files__PermissionPublic']
export type PermissionList = components['schemas']['app__schemas__files__PermissionList']
export type UploadResultItem = components['schemas']['app__schemas__files__UploadResultItem']
export type UploadResult = components['schemas']['app__schemas__files__UploadResult']
export type FileOpenResponse = components['schemas']['FileOpenResponse']
export type NcSyncReport = components['schemas']['NcSyncReport']
export type BulkDeleteResultItem = components['schemas']['BulkDeleteResultItem']
export type BulkDeleteResult = components['schemas']['BulkDeleteResult']
export type BulkMoveResultItem = components['schemas']['BulkMoveResultItem']
export type BulkMoveResult = components['schemas']['BulkMoveResult']
export type FileSharePublic = components['schemas']['FileSharePublic']
export type FileShareList = components['schemas']['FileShareList']
export type MyFileShare = components['schemas']['MyFileShare']
export type MyFileShareList = components['schemas']['MyFileShareList']
export type SharedFile = components['schemas']['SharedFile']
export type SharedFileList = components['schemas']['SharedFileList']
export type AdminFileShare = components['schemas']['AdminFileShare']
export type AdminFileShareList = components['schemas']['AdminFileShareList']

// subject_type в gen-схеме string; FilesShareModal::onSubjectSelect присваивает
// его в grantForm с union 'user' | 'group' — сужаем.
export type FilesSubjectSearchResult = Omit<components['schemas']['SubjectSearchResult'], 'subject_type'> & {
  subject_type: 'user' | 'group'
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

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────

// нет в OpenAPI — фронтовый тип: UI-представление иконки файла
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

function fileExt(item: NCItem): string {
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

export function syncFromNextcloud(): Promise<NcSyncReport> {
  return api<NcSyncReport>('/files/sync', { method: 'POST' })
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

export function searchFilesSubjects(q: string): Promise<FilesSubjectSearchResult[]> {
  return api<FilesSubjectSearchResult[]>('/files/users/search', { params: { q } })
}
