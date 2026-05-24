import { api, apiUpload } from './index'
import { triggerDownload } from '../utils/download'
import type { components } from './types.gen.d'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type KbUserRef = components['schemas']['KbUserRef']
export type KbTag = components['schemas']['KbTagPublic']
export type KbBreadcrumb = components['schemas']['KbBreadcrumb']
export type KbSection = components['schemas']['KbSectionPublic'] & {
  children: KbSection[]
}
export type KbArticleListItem = components['schemas']['KbArticleListItem'] & {
  tags: KbTag[]
  created_by: KbUserRef | null
}
export type KbArticle = components['schemas']['KbArticlePublic'] & {
  tags: KbTag[]
  breadcrumbs: KbBreadcrumb[]
  created_by: KbUserRef | null
  updated_by: KbUserRef | null
  status: 'draft' | 'published' | 'archived'
  user_permission: 'viewer' | 'editor' | 'manager' | null
}
export type KbArticleList = Omit<components['schemas']['KbArticleList'], 'items'> & {
  items: KbArticleListItem[]
}
export type KbVersion = components['schemas']['KbVersionPublic']
export type KbComment = components['schemas']['KbCommentPublic']
export type SearchResultItem = components['schemas']['SearchResultItem']
export type SearchResponse = components['schemas']['SearchResponse']
export type ImportResult = components['schemas']['ImportReport']
export type FeedbackStats = components['schemas']['FeedbackStats']

export type DraftSaveDto = components['schemas']['DraftSaveRequest']

// ── Request DTOs (generated from OpenAPI schema) ───────────────────────────

export type CreateSectionDto = components['schemas']['CreateSectionRequest']
export type UpdateSectionDto = components['schemas']['UpdateSectionRequest']
export type CreateArticleDto = components['schemas']['CreateArticleRequest']
export type UpdateArticleDto = components['schemas']['UpdateArticleRequest']

// ── Теги ─────────────────────────────────────────────────────────────────────

export async function fetchTags(): Promise<KbTag[]> {
  return api<KbTag[]>('/kb/tags')
}

// ── Разделы ───────────────────────────────────────────────────────────────────

export async function fetchSections(): Promise<{ items: KbSection[] }> {
  return api<{ items: KbSection[] }>('/kb/sections')
}

export async function createSection(dto: CreateSectionDto): Promise<KbSection> {
  return api<KbSection>('/kb/sections', { method: 'POST', body: dto })
}

export async function updateSection(id: string, dto: UpdateSectionDto): Promise<KbSection> {
  return api<KbSection>(`/kb/sections/${id}`, { method: 'PUT', body: dto })
}

export async function deleteSection(id: string, force = false): Promise<void> {
  await api<void>(`/kb/sections/${id}`, { method: 'DELETE', params: { force } })
}

// ── Статьи ────────────────────────────────────────────────────────────────────

export async function fetchArticles(params?: {
  section_id?: string
  tag?: string
  status?: string
  q?: string
  limit?: number
  offset?: number
}): Promise<KbArticleList> {
  return api<KbArticleList>('/kb/articles', { params })
}

export async function fetchArticle(id: string): Promise<KbArticle> {
  return api<KbArticle>(`/kb/articles/${id}`)
}

export async function createArticle(dto: CreateArticleDto): Promise<KbArticle> {
  return api<KbArticle>('/kb/articles', { method: 'POST', body: dto })
}

export async function updateArticle(id: string, dto: UpdateArticleDto): Promise<KbArticle> {
  return api<KbArticle>(`/kb/articles/${id}`, { method: 'PUT', body: dto })
}

export async function saveDraft(id: string, dto: DraftSaveDto): Promise<KbArticle> {
  return api<KbArticle>(`/kb/articles/${id}/draft`, { method: 'PUT', body: dto })
}

export async function deleteArticle(id: string): Promise<void> {
  await api<void>(`/kb/articles/${id}`, { method: 'DELETE' })
}

export async function restoreArticle(id: string): Promise<KbArticle> {
  return api<KbArticle>(`/kb/articles/${id}/restore`, { method: 'POST' })
}

// ── Версии ────────────────────────────────────────────────────────────────────

export async function fetchVersions(
  articleId: string,
  params?: { limit?: number; offset?: number },
): Promise<{ items: KbVersion[]; total: number }> {
  return api<{ items: KbVersion[]; total: number }>(`/kb/articles/${articleId}/versions`, { params })
}

export async function restoreVersion(articleId: string, versionNumber: number): Promise<KbArticle> {
  return api<KbArticle>(`/kb/articles/${articleId}/versions/${versionNumber}/restore`, {
    method: 'POST',
  })
}

// ── Комментарии ───────────────────────────────────────────────────────────────

export async function fetchComments(
  articleId: string,
  params?: { limit?: number; offset?: number },
): Promise<{ items: KbComment[]; total: number }> {
  return api<{ items: KbComment[]; total: number }>(`/kb/articles/${articleId}/comments`, { params })
}

export async function createComment(articleId: string, body: string): Promise<KbComment> {
  return api<KbComment>(`/kb/articles/${articleId}/comments`, { method: 'POST', body: { body } })
}

export async function deleteComment(articleId: string, commentId: string): Promise<void> {
  await api<void>(`/kb/articles/${articleId}/comments/${commentId}`, { method: 'DELETE' })
}

// ── Правки ────────────────────────────────────────────────────────────────────

export async function suggestEdit(
  articleId: string,
  dto: { body: string; comment?: string },
): Promise<{ suggestion_id: string; message: string }> {
  return api<{ suggestion_id: string; message: string }>(
    `/kb/articles/${articleId}/suggest`,
    { method: 'POST', body: dto },
  )
}

// ── Обратная связь ────────────────────────────────────────────────────────────

export async function submitFeedback(
  articleId: string,
  is_helpful: boolean,
): Promise<FeedbackStats> {
  return api<FeedbackStats>(`/kb/articles/${articleId}/feedback`, { method: 'POST', body: { is_helpful } })
}

// ── Экспорт ───────────────────────────────────────────────────────────────────

export async function exportArticlePdf(articleId: string): Promise<void> {
  triggerDownload(`/api/v1/kb/articles/${articleId}/export/pdf`, {
    target: '_blank',
    rel: 'noopener noreferrer',
  })
}

export async function exportArticleDocx(articleId: string): Promise<void> {
  triggerDownload(`/api/v1/kb/articles/${articleId}/export/docx`, {
    target: '_blank',
    rel: 'noopener noreferrer',
  })
}

export function exportSectionZip(sectionId: string): void {
  triggerDownload(`/api/v1/kb/sections/${sectionId}/export/zip`)
}

export function exportKbVault(): void {
  triggerDownload(`/api/v1/kb/export/vault.zip`)
}

// ── Импорт ────────────────────────────────────────────────────────────────────

export async function importMarkdownFile(file: File): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<ImportResult>('/kb/articles/import', form)
}

export async function importVaultZip(
  file: File,
  strategy: 'skip' | 'overwrite' | 'create_new' = 'skip',
): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<ImportResult>(`/kb/import/vault?strategy=${strategy}`, form)
}

// ── Поиск ─────────────────────────────────────────────────────────────────────

export async function globalSearch(
  q: string,
  params?: { type?: string; limit?: number; offset?: number },
  options?: { signal?: AbortSignal },
): Promise<SearchResponse> {
  return api<SearchResponse>('/search', { params: { q, ...params }, signal: options?.signal })
}

export async function searchSuggest(q: string): Promise<{ suggestions: string[] }> {
  return api<{ suggestions: string[] }>('/search/suggest', { params: { q } })
}

// ── Сравнение версий ──────────────────────────────────────────────────────────

export interface DiffHunk {
  header: string
  lines: string[]
}

export interface DiffData {
  hunks: DiffHunk[]
  stats: {
    added: number
    removed: number
  }
}

export async function fetchVersionDiff(
  articleId: string,
  v1: number,
  v2: number,
): Promise<DiffData> {
  return api<DiffData>(`/kb/articles/${articleId}/versions/${v1}/diff/${v2}`)
}

// ── Управление доступом ────────────────────────────────────────────────────────

export interface PermEntry {
  id: string
  subject_type: string
  subject_id: string
  subject_name: string
  email?: string
  permission: string
}

export interface UserSearchSubject {
  subject_type: string
  subject_id: string
  subject_name: string
  email?: string
}

export async function fetchPermissions(
  resourceType: 'section' | 'article',
  resourceId: string,
): Promise<{ items: PermEntry[] }> {
  const url = resourceType === 'section'
    ? `/kb/sections/${resourceId}/permissions`
    : `/kb/articles/${resourceId}/permissions`
  return api<{ items: PermEntry[] }>(url)
}

export async function savePermission(
  resourceType: 'section' | 'article',
  resourceId: string,
  dto: {
    subject_type: string
    subject_id: string
    subject_name: string
    permission: string
  },
): Promise<PermEntry> {
  const url = resourceType === 'section'
    ? `/kb/sections/${resourceId}/permissions`
    : `/kb/articles/${resourceId}/permissions`
  return api<PermEntry>(url, { method: 'POST', body: dto })
}

export async function deletePermission(
  resourceType: 'section' | 'article',
  resourceId: string,
  subjectId: string,
): Promise<void> {
  const url = resourceType === 'section'
    ? `/kb/sections/${resourceId}/permissions/${subjectId}`
    : `/kb/articles/${resourceId}/permissions/${subjectId}`
  await api<void>(url, { method: 'DELETE' })
}

export async function updateInheritance(
  resourceType: 'section' | 'article',
  resourceId: string,
  inherit: boolean,
): Promise<void> {
  const url = resourceType === 'section'
    ? `/kb/sections/${resourceId}/inherit`
    : `/kb/articles/${resourceId}/inherit`
  await api<void>(url, { method: 'PATCH', body: { inherit_permissions: inherit } })
}

export async function searchKbUsers(
  q: string,
  options?: { signal?: AbortSignal },
): Promise<UserSearchSubject[]> {
  return api<UserSearchSubject[]>(`/kb/users/search?q=${encodeURIComponent(q)}`, {
    signal: options?.signal,
  })
}

// ── Вложения ──────────────────────────────────────────────────────────────────

export interface KbFile {
  id: string
  article_id: string
  filename: string
  original_name: string
  size_bytes: number
  mime_type: string | null
  created_at: string
}

export async function fetchAttachments(articleId: string): Promise<{ items: KbFile[] }> {
  return api<{ items: KbFile[] }>(`/kb/articles/${articleId}/files`)
}

export async function uploadAttachment(articleId: string, formData: FormData): Promise<void> {
  await apiUpload<void>(`/kb/articles/${articleId}/files`, formData)
}

export async function deleteAttachment(articleId: string, fileId: string): Promise<void> {
  await api<void>(`/kb/articles/${articleId}/files/${fileId}`, { method: 'DELETE' })
}
