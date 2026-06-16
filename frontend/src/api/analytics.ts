import { api } from './index'

export interface DashboardOut {
  generated_at: string
  users: {
    total: number
    active_30d: number
    active_1h: number
    new_30d: number
  }
  content: {
    news_published_30d: number
    kb_articles_published_30d: number
  }
  activity: {
    audit_events_24h: number
    logins_24h: number
  }
  series: {
    daily_logins_14d: { day: string | null; count: number }[]
    daily_publications_14d: { day: string | null; count: number }[]
  }
}

export interface TopArticle {
  id: string
  title: string
  section_title: string
  view_count: number
  published_at: string | null
  updated_at: string | null
}

export interface TopNews {
  id: string
  title: string
  view_count: number
  published_at: string | null
}

export interface TopFile {
  resource_id: string
  title: string
  downloads: number
  last_download: string | null
}

export interface TopLink {
  resource_id: string
  title: string
  clicks: number
  unique_users: number
  last_click: string | null
}

export interface DepartmentRow {
  department: string | null
  total_users: number
  active_users: number
  events: number
}

export function fetchDashboard(opts?: { signal?: AbortSignal }) {
  return api<DashboardOut>('/analytics/dashboard', { signal: opts?.signal })
}

export function fetchTopArticles(days = 30, limit = 20, opts?: { signal?: AbortSignal }) {
  return api<TopArticle[]>('/analytics/top-articles', { query: { days, limit }, signal: opts?.signal })
}

export function fetchTopNews(days = 30, limit = 20, opts?: { signal?: AbortSignal }) {
  return api<TopNews[]>('/analytics/top-news', { query: { days, limit }, signal: opts?.signal })
}

export function fetchTopFiles(days = 30, limit = 20, opts?: { signal?: AbortSignal }) {
  return api<TopFile[]>('/analytics/top-files', { query: { days, limit }, signal: opts?.signal })
}

export function fetchTopLinks(days = 30, limit = 20, opts?: { signal?: AbortSignal }) {
  return api<TopLink[]>('/analytics/top-links', { query: { days, limit }, signal: opts?.signal })
}

export function fetchDepartments(days = 30, opts?: { signal?: AbortSignal }) {
  return api<DepartmentRow[]>('/analytics/departments', { query: { days }, signal: opts?.signal })
}
