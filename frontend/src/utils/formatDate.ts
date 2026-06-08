export function formatDate(iso: string, locale: string): string {
  const lang = locale === 'ru' ? 'ru-RU' : 'en-US'
  return new Date(iso).toLocaleDateString(lang, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatDateShort(iso: string, locale: string): string {
  const lang = locale === 'ru' ? 'ru-RU' : 'en-US'
  return new Date(iso).toLocaleDateString(lang, { day: 'numeric', month: 'short' })
}

export function formatRelativeTime(iso: string, locale: string): string {
  const lang = locale === 'ru' ? 'ru-RU' : 'en-US'
  const then = new Date(iso).getTime()
  const diffSec = Math.round((then - Date.now()) / 1000)
  const abs = Math.abs(diffSec)
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' })

  if (abs < 45) return rtf.format(Math.round(diffSec / 1), 'second')
  if (abs < 2700) return rtf.format(Math.round(diffSec / 60), 'minute')
  if (abs < 79200) return rtf.format(Math.round(diffSec / 3600), 'hour')
  if (abs < 2592000) return rtf.format(Math.round(diffSec / 86400), 'day')
  return new Date(iso).toLocaleDateString(lang, { day: 'numeric', month: 'short', year: 'numeric' })
}
