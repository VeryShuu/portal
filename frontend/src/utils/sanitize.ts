import DOMPurify from 'dompurify'

const FORBID_TAGS = ['style', 'script', 'iframe', 'object', 'embed', 'form', 'meta', 'link']
const FORBID_ATTR = ['onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'onblur', 'onchange', 'onsubmit']

const TEXT_ALIGN_RE = /^\s*text-align\s*:\s*(left|center|right|justify)\s*;?\s*$/i

function sanitizeStyleAttr(value: string): string {
  const declarations = value.split(';').map((d) => d.trim()).filter(Boolean)
  const kept: string[] = []
  for (const decl of declarations) {
    if (TEXT_ALIGN_RE.test(decl + ';')) {
      kept.push(decl)
    }
  }
  return kept.join('; ')
}

function styleAttrHook(_node: Element, data: { attrName: string; attrValue: string; keepAttr: boolean }) {
  if (data.attrName !== 'style') return
  const cleaned = sanitizeStyleAttr(data.attrValue)
  if (cleaned) {
    data.attrValue = cleaned
    data.keepAttr = true
  } else {
    data.keepAttr = false
  }
}

export function sanitizeHtml(html: string): string {
  if (!html) return ''
  const purify = DOMPurify(window)
  purify.addHook('uponSanitizeAttribute', styleAttrHook)
  const result = purify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS,
    FORBID_ATTR,
    ALLOW_DATA_ATTR: false,
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|ftp):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
  })
  purify.removeHook('uponSanitizeAttribute')
  return result
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

  purify.addHook('uponSanitizeAttribute', styleAttrHook)

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
  purify.removeHook('uponSanitizeAttribute')
  return result
}
