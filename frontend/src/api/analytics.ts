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

export interface DepartmentRow {
  department: string | null
  total_users: number
  active_users: number
  events: number
}

export function fetchDashboard() {
  return api<DashboardOut>('/analytics/dashboard')
}

export function fetchTopArticles(days = 30, limit = 20) {
  return api<TopArticle[]>('/analytics/top-articles', { query: { days, limit } })
}

export function fetchTopNews(days = 30, limit = 20) {
  return api<TopNews[]>('/analytics/top-news', { query: { days, limit } })
}

export function fetchTopFiles(days = 30, limit = 20) {
  return api<TopFile[]>('/analytics/top-files', { query: { days, limit } })
}

export function fetchDepartments(days = 30) {
  return api<DepartmentRow[]>('/analytics/departments', { query: { days } })
}
