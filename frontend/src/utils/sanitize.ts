import DOMPurify from 'dompurify'

const FORBID_TAGS = ['style', 'script', 'iframe', 'object', 'embed', 'form', 'meta', 'link']
const FORBID_ATTR = ['onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'onblur', 'onchange', 'onsubmit', 'style']

export function sanitizeHtml(html: string): string {
  if (!html) return ''
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS,
    FORBID_ATTR,
    ALLOW_DATA_ATTR: false,
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|ftp):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
  })
}

export function sanitizeHtmlWithIframe(html: string): string {
  if (!html) return ''
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: FORBID_TAGS.filter((t) => t !== 'iframe'),
    FORBID_ATTR,
    ALLOW_DATA_ATTR: false,
    ADD_TAGS: ['iframe'],
    ADD_ATTR: ['allowfullscreen', 'sandbox', 'loading', 'title'],
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|ftp):|[^a-z]|[a-z+.-]+(?:[^a-z+.:-]|$))/i,
  })
}

export function sanitizeHtmlAllowIframe(html: string, allowedOrigins: string[]): string {
  if (!html) return ''

  const purify = DOMPurify(window)

  purify.addHook('uponSanitizeElement', (node, data) => {
    if (data.tagName === 'iframe') {
      const src = (node as Element).getAttribute('src') ?? ''
      let allowed = false
      if (src && allowedOrigins.length) {
        try {
          const parsedSrc = new URL(src)
          if (!['http:', 'https:'].includes(parsedSrc.protocol)) {
            allowed = false
          } else {
            allowed = allowedOrigins.some((o) => {
              try { return new URL(o).origin === parsedSrc.origin } catch { return false }
            })
          }
        } catch {
          allowed = false
        }
      }
      if (!allowed) {
        (node as Element).remove()
      }
    }
  })

  const result = purify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: FORBID_TAGS.filter((t) => t !== 'iframe'),
    FORBID_ATTR,
    ALLOW_DATA_ATTR: false,
    ADD_TAGS: ['iframe'],
    ADD_ATTR: ['allowfullscreen', 'sandbox', 'loading'],
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|ftp):|[^a-z]|[a-z+.-]+(?:[^a-z+.:-]|$))/i,
  })

  purify.removeHook('uponSanitizeElement')
  return result
}
