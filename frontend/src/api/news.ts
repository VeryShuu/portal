import { ofetch } from 'ofetch'
import { api, type PaginatedResponse } from './index'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

export interface News {
  id: string
  title: string
  body: string
  status: 'draft' | 'published' | 'archived'
  is_pinned: boolean
  category: string | null
  cover_image_url: string | null
  target_departments: string[] | null
  target_roles: string[] | null
  author_id: string | null
  publish_at: string | null
  archive_at: string | null
  published_at: string | null
  view_count: number
  current_version: number
  created_at: string
  updated_at: string
}

export interface NewsVersion {
  id: string
  news_id: string
  version: number
  title: string
  body: string
  editor_id: string | null
  created_at: string
}

export interface CreateNewsDto {
  title: string
  body?: string
  status?: 'draft' | 'published'
  is_pinned?: boolean
  category?: string | null
  target_departments?: string[] | null
  target_roles?: string[] | null
  publish_at?: string | null
  archive_at?: string | null
}

export interface UpdateNewsDto extends Partial<CreateNewsDto> {}

export async function fetchNewsList(params?: {
  page?: number
  page_size?: number
  status?: string
}): Promise<PaginatedResponse<News>> {
  return api<PaginatedResponse<News>>('/news', { params })
}

export async function fetchNewsById(id: string): Promise<News> {
  return api<News>(`/news/${id}`)
}

export async function createNews(dto: CreateNewsDto): Promise<News> {
  return api<News>('/news', { method: 'POST', body: dto })
}

export async function updateNews(id: string, dto: UpdateNewsDto): Promise<News> {
  return api<News>(`/news/${id}`, { method: 'PUT', body: dto })
}

export async function saveDraft(id: string, dto: UpdateNewsDto): Promise<News> {
  return api<News>(`/news/${id}/draft`, { method: 'PUT', body: dto })
}

export async function deleteNews(id: string): Promise<void> {
  await api(`/news/${id}`, { method: 'DELETE' })
}

export async function fetchNewsVersions(id: string): Promise<NewsVersion[]> {
  return api<NewsVersion[]>(`/news/${id}/versions`)
}

export async function uploadNewsCover(id: string, file: File): Promise<News> {
  const form = new FormData()
  form.append('file', file)
  return ofetch<News>(`${BASE_URL}/news/${id}/cover`, {
    method: 'POST',
    body: form,
    credentials: 'include',
  })
}

export async function deleteNewsCover(id: string): Promise<News> {
  return api<News>(`/news/${id}/cover`, { method: 'DELETE' })
}
