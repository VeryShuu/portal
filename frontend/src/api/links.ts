import { api, apiUpload, type PaginatedResponse } from './index'

export interface ServiceLink {
  id: string
  title: string
  url: string
  icon_url: string | null
  description: string | null
  category: string | null
  sort_order: number
  supports_sso: boolean
  is_active: boolean
  show_on_home: boolean
  kb_url: string | null
  created_at: string
  updated_at: string
}

export interface Bookmark {
  id: string
  user_id: string
  title: string
  url: string
  resource_type: string | null
  resource_id: string | null
  group_name: string | null
  sort_order: number
  created_at: string
}

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

export interface CreateLinkDto {
  title: string
  url: string
  description?: string | null
  category?: string | null
  sort_order?: number
  supports_sso?: boolean
  is_active?: boolean
  show_on_home?: boolean
  kb_url?: string | null
}

export interface CreateBookmarkDto {
  title: string
  url: string
  resource_type?: string | null
  resource_id?: string | null
  group_name?: string | null
}

export interface BookmarkReorderItem {
  id: string
  sort_order: number
}

export interface LinkReorderItem {
  id: string
  sort_order: number
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
