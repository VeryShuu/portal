export function formatDate(iso: string, locale: string): string {
  const lang = locale === 'ru' ? 'ru-RU' : 'en-US'
  return new Date(iso).toLocaleDateString(lang, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatDateShort(iso: string, locale: string): string {
  const lang = locale === 'ru' ? 'ru-RU' : 'en-US'
  return new Date(iso).toLocaleDateString(lang, { day: 'numeric', month: 'short' })
}
