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
    wau_7d: number
    mau_30d: number
  }
  series: {
    daily_logins_14d: { day: string | null; count: number }[]
    daily_publications_14d: { day: string | null; count: number }[]
    daily_active_users: { day: string | null; count: number }[]
    daily_uploads: { day: string | null; count: number }[]
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

export interface StaleContentItem {
  kind: string
  id: string
  title: string
  view_count: number
  updated_at: string | null
}

export interface FeedbackStats {
  total: number
  open: number
  in_progress: number
  closed: number
  avg_first_response_seconds: number | null
}

export interface DailyPoint {
  day: string | null
  count: number
}

export type ExportDataset =
  | 'top-articles'
  | 'top-news'
  | 'top-files'
  | 'top-links'
  | 'departments'
  | 'stale-content'

export function fetchDashboard(days = 14, opts?: { signal?: AbortSignal }) {
  return api<DashboardOut>('/analytics/dashboard', { query: { days }, signal: opts?.signal })
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

export function fetchStaleContent(days = 90, limit = 20, opts?: { signal?: AbortSignal }) {
  return api<StaleContentItem[]>('/analytics/stale-content', { query: { days, limit }, signal: opts?.signal })
}

export function fetchFeedbackStats(days = 30, opts?: { signal?: AbortSignal }) {
  return api<FeedbackStats>('/analytics/feedback', { query: { days }, signal: opts?.signal })
}

export function fetchResourceTrend(
  resourceId: string,
  kind: 'link' | 'file' = 'link',
  days = 30,
  opts?: { signal?: AbortSignal },
) {
  return api<DailyPoint[]>('/analytics/resource-trend', {
    query: { resource_id: resourceId, kind, days },
    signal: opts?.signal,
  })
}

export function analyticsExportUrl(
  dataset: ExportDataset,
  format: 'csv' | 'xlsx' = 'csv',
  days = 30,
  limit = 100,
): string {
  const params = new URLSearchParams({
    dataset,
    format,
    days: String(days),
    limit: String(limit),
  })
  return `/api/v1/analytics/export?${params.toString()}`
}
