import { api, apiUpload, type PaginatedResponse } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type ServiceLink = components['schemas']['ServiceLinkPublic']
export type Bookmark = components['schemas']['BookmarkPublic']
export type CreateLinkDto = components['schemas']['CreateLinkRequest']
export type CreateBookmarkDto = components['schemas']['CreateBookmarkRequest']
export type BookmarkReorderItem = components['schemas']['BookmarkReorderItem']
export type LinkReorderItem = components['schemas']['LinkReorderItem']

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────

// нет в OpenAPI — фронтовый тип: нормализованная UI-модель (camelCase, kind)
export type NormalizedItem = {
  id: string
  title: string
  url: string
  description: string | null
  iconUrl: string | null
  supportsSso: boolean
  kbUrl?: string | null
  group: string
  kind: 'link' | 'bookmark'
  raw: ServiceLink | Bookmark
}

export async function fetchLinks(params?: {
  category?: string
  include_inactive?: boolean
}): Promise<PaginatedResponse<ServiceLink>> {
  return api<PaginatedResponse<ServiceLink>>('/links', { params })
}

export async function createLink(dto: CreateLinkDto): Promise<ServiceLink> {
  return api<ServiceLink>('/links', { method: 'POST', body: dto })
}

export async function updateLink(id: string, dto: Partial<CreateLinkDto>): Promise<ServiceLink> {
  return api<ServiceLink>(`/links/${id}`, { method: 'PUT', body: dto })
}

export async function deleteLink(id: string): Promise<void> {
  await api(`/links/${id}`, { method: 'DELETE' })
}

export async function uploadLinkIcon(id: string, file: File): Promise<ServiceLink> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<ServiceLink>(`/links/${id}/icon`, form)
}

export async function deleteLinkIcon(id: string): Promise<void> {
  await api(`/links/${id}/icon`, { method: 'DELETE' })
}

export async function fetchBookmarks(): Promise<PaginatedResponse<Bookmark>> {
  return api<PaginatedResponse<Bookmark>>('/bookmarks')
}

export async function createBookmark(dto: CreateBookmarkDto): Promise<Bookmark> {
  return api<Bookmark>('/bookmarks', { method: 'POST', body: dto })
}

export async function deleteBookmark(id: string): Promise<void> {
  await api(`/bookmarks/${id}`, { method: 'DELETE' })
}

export async function reorderBookmarks(items: BookmarkReorderItem[]): Promise<void> {
  await api('/bookmarks/reorder', { method: 'PATCH', body: { items } })
}

export async function reorderLinks(items: LinkReorderItem[]): Promise<void> {
  await api('/links/reorder', { method: 'PATCH', body: { items } })
}

export async function recordLinkClick(id: string): Promise<void> {
  try {
    await api(`/links/${id}/click`, { method: 'POST', keepalive: true })
  } catch {
    // Аналитика переходов — fire-and-forget: сбой трекинга не должен мешать
    // самому переходу пользователя по ярлыку.
  }
}
