import { api } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json
// Внимание: gen-схема FeedbackStats — это про «полезность» KB-статьи
// (helpful_count/not_helpful_count); статистика обращений — FeedbackStatsOut.

export type DashboardOut = components['schemas']['DashboardOut']
export type TopArticle = components['schemas']['TopArticleOut']
export type TopNews = components['schemas']['TopNewsOut']
export type TopFile = components['schemas']['TopFileOut']
export type TopLink = components['schemas']['TopLinkOut']
export type DepartmentRow = components['schemas']['DepartmentOut']
export type StaleContentItem = components['schemas']['StaleContentItem']
export type FeedbackStats = components['schemas']['FeedbackStatsOut']
export type DailyPoint = components['schemas']['DailyPoint']

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────

// нет в OpenAPI — фронтовый тип: query-param union для /analytics/export
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
