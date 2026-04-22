/**
 * P0-6: URL validator that rejects dangerous protocols (javascript:, data:, vbscript:, file:).
 * Only http: and https: are accepted for outbound service links.
 */
const ALLOWED_PROTOCOLS = new Set(['http:', 'https:'])

export function isSafeHttpUrl(value: string | null | undefined): boolean {
  if (!value) return false
  try {
    const u = new URL(value)
    return ALLOWED_PROTOCOLS.has(u.protocol)
  } catch {
    return false
  }
}
