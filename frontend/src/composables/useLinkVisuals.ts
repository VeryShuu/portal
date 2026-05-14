const PALETTE = [
  '#e0eafc', '#ffe4e1', '#ede4ff', '#dcfce7', '#fef3c7', '#e0f2fe', '#fce7f3',
] as const

export function colorFor(url: string): string {
  let hash = 0
  for (let i = 0; i < url.length; i++) hash = (hash * 31 + url.charCodeAt(i)) >>> 0
  return PALETTE[hash % PALETTE.length]
}

export function faviconFor(url: string): string | null {
  try {
    return `${new URL(url).origin}/favicon.ico`
  } catch {
    return null
  }
}

export function shortUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export function onIconError(e: Event): void {
  const img = e.target
  if (img instanceof HTMLImageElement) img.style.display = 'none'
}
