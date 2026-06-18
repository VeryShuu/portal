export type NewsStatus = 'draft' | 'published'

export const NEWS_STATUSES: readonly NewsStatus[] = ['draft', 'published']

export const AUTOSAVE_INTERVAL_MS = 30_000

export function toNewsStatus(value: unknown, fallback: NewsStatus = 'draft'): NewsStatus {
  return typeof value === 'string' && (NEWS_STATUSES as readonly string[]).includes(value)
    ? (value as NewsStatus)
    : fallback
}

export function isoToMs(iso: string | null): number | null {
  return iso ? new Date(iso).getTime() : null
}

export function msToIso(ms: number | null): string | null {
  return ms ? new Date(ms).toISOString() : null
}

export function formatSavedTime(date: Date, locale: string): string {
  const lang = locale === 'ru' ? 'ru-RU' : 'en-US'
  return date.toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' })
}

export function isBodyEmpty(html: string): boolean {
  const stripped = html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
  return stripped.length === 0
}
