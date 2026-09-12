const MAX_URL_LENGTH = 2048

export function isSafeHttpUrl(url: string): boolean {
  if (!url || url.length > MAX_URL_LENGTH) return false
  try {
    const u = new URL(url)
    return (u.protocol === 'http:' || u.protocol === 'https:') && u.hostname.length > 0
  } catch {
    return false
  }
}

export function isInternalLinkUrl(url: string): boolean {
  if (!url || url.length > MAX_URL_LENGTH) return false
  return url.startsWith('/') && !url.startsWith('//')
}

export function isServiceLinkUrl(url: string): boolean {
  return isInternalLinkUrl(url) || isSafeHttpUrl(url)
}
