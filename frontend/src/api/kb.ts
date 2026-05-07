import { api, apiUpload } from './index'
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

// ── Request DTOs (kept as manual interfaces — not generated from schema) ──────

export interface CreateSectionDto {
  title: string
  parent_id?: string | null
  description?: string | null
  sort_order?: number
}

export interface UpdateSectionDto {
  title?: string
  parent_id?: string | null
  description?: string | null
  sort_order?: number
}

export interface CreateArticleDto {
  section_id?: string | null
  title: string
  body?: string
  status?: 'draft' | 'published'
  tags?: string[]
}

export interface UpdateArticleDto {
  title?: string
  body?: string
  section_id?: string | null
  status?: 'draft' | 'published' | 'archived'
  tags?: string[]
  version: number
  change_comment?: string
}

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

export async function saveDraft(id: string, dto: { title?: string; body?: string }): Promise<KbArticle> {
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
  const a = document.createElement('a')
  a.href = `/api/v1/kb/articles/${articleId}/export/pdf`
  a.target = '_blank'
  a.rel = 'noopener noreferrer'
  a.click()
}

export async function exportArticleDocx(articleId: string): Promise<void> {
  const a = document.createElement('a')
  a.href = `/api/v1/kb/articles/${articleId}/export/docx`
  a.target = '_blank'
  a.rel = 'noopener noreferrer'
  a.click()
}

export function exportSectionZip(sectionId: string): void {
  const a = document.createElement('a')
  a.href = `/api/v1/kb/sections/${sectionId}/export/zip`
  a.click()
}

export function exportKbVault(): void {
  const a = document.createElement('a')
  a.href = `/api/v1/kb/export/vault.zip`
  a.click()
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
): Promise<SearchResponse> {
  return api<SearchResponse>('/search', { params: { q, ...params } })
}

export async function searchSuggest(q: string): Promise<{ suggestions: string[] }> {
  return api<{ suggestions: string[] }>('/search/suggest', { params: { q } })
}
