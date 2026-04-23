import { api } from './index'

export interface KbUserRef {
  id: string
  full_name: string
  avatar_url: string | null
}

export interface KbTag {
  id: string
  name: string
  slug: string
}

export interface KbBreadcrumb {
  id: string
  title: string
  slug: string
}

export interface KbSection {
  id: string
  parent_id: string | null
  title: string
  slug: string
  description: string | null
  sort_order: number
  created_at: string
  children: KbSection[]
}

export interface KbArticleListItem {
  id: string
  title: string
  section_id: string | null
  status: 'draft' | 'published' | 'archived'
  version: number
  view_count: number
  published_at: string | null
  created_at: string
  updated_at: string
  tags: KbTag[]
  created_by: KbUserRef | null
}

export interface KbArticle {
  id: string
  title: string
  body: string
  section_id: string | null
  status: 'draft' | 'published' | 'archived'
  version: number
  view_count: number
  published_at: string | null
  created_at: string
  updated_at: string
  tags: KbTag[]
  breadcrumbs: KbBreadcrumb[]
  created_by: KbUserRef | null
  updated_by: KbUserRef | null
  helpful_count: number
  not_helpful_count: number
  user_feedback: boolean | null
  inherit_permissions: boolean
}

export interface KbArticleList {
  items: KbArticleListItem[]
  total: number
  limit: number
  offset: number
}

export interface KbVersion {
  id: string
  article_id: string
  version: number
  title: string | null
  body: string | null
  change_comment: string | null
  changed_by: KbUserRef | null
  created_at: string
}

export interface KbComment {
  id: string
  article_id: string
  body: string | null
  is_deleted: boolean
  created_at: string
  updated_at: string
  author: KbUserRef | null
}

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

export interface SearchResultItem {
  type: 'article' | 'news' | 'link' | 'user'
  id: string
  title: string
  snippet: string | null
  url: string
  created_at: string | null
  author: string | null
}

export interface SearchResponse {
  items: SearchResultItem[]
  total: number
  query: string
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
  await api(`/kb/sections/${id}`, { method: 'DELETE', params: { force } })
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
  await api(`/kb/articles/${id}`, { method: 'DELETE' })
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
  await api(`/kb/articles/${articleId}/comments/${commentId}`, { method: 'DELETE' })
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
): Promise<{ helpful_count: number; not_helpful_count: number; user_feedback: boolean | null }> {
  return api(`/kb/articles/${articleId}/feedback`, { method: 'POST', body: { is_helpful } })
}

// ── Экспорт ───────────────────────────────────────────────────────────────────

export async function exportArticlePdf(articleId: string): Promise<void> {
  const a = document.createElement('a')
  a.href = `/api/v1/kb/articles/${articleId}/export/pdf`
  a.target = '_blank'
  a.click()
}

export async function exportArticleDocx(articleId: string): Promise<void> {
  const a = document.createElement('a')
  a.href = `/api/v1/kb/articles/${articleId}/export/docx`
  a.target = '_blank'
  a.click()
}

// ── Импорт ────────────────────────────────────────────────────────────────────

export interface ImportResult {
  created: number
  updated: number
  skipped: number
  errors: string[]
}

export async function importMarkdownFile(file: File): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch('/api/v1/kb/articles/import', {
    method: 'POST',
    body: form,
    credentials: 'include',
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err.detail ?? `HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function importVaultZip(
  file: File,
  strategy: 'skip' | 'overwrite' | 'create_new' = 'skip',
): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(`/api/v1/kb/import/vault?strategy=${strategy}`, {
    method: 'POST',
    body: form,
    credentials: 'include',
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err.detail ?? `HTTP ${resp.status}`)
  }
  return resp.json()
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
