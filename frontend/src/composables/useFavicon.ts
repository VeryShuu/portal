import { BASE_URL } from '../api'

export function useFavicon() {
  function faviconFor(url: string): string | null {
    try {
      const u = new URL(url)
      if (!['http:', 'https:'].includes(u.protocol)) return null
      return `${BASE_URL}/bookmarks/favicon?url=${encodeURIComponent(u.origin)}`
    } catch {
      return null
    }
  }

  function shortUrl(url: string): string {
    try {
      const u = new URL(url)
      return u.hostname.replace(/^www\./, '')
    } catch {
      return url
    }
  }

  const palette = [
    '#e0eafc', '#ffe4e1', '#ede4ff', '#dcfce7', '#fef3c7', '#e0f2fe', '#fce7f3',
  ]

  function colorFor(url: string): string {
    let hash = 0
    for (let i = 0; i < url.length; i++) hash = (hash * 31 + url.charCodeAt(i)) >>> 0
    return palette[hash % palette.length]
  }

  function onIconError(e: Event) {
    const img = e.target as HTMLImageElement
    img.style.display = 'none'
  }

  return { faviconFor, shortUrl, colorFor, onIconError }
}
