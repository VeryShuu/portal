import DOMPurify from 'dompurify'

const FORBID_TAGS = ['style', 'svg', 'script', 'iframe', 'object', 'embed', 'form', 'meta', 'link']
const FORBID_ATTR = [
  'onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'onblur',
  'onchange', 'onsubmit', 'srcset', 'formaction',
]

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

const _purify = DOMPurify(window)

_purify.addHook('uponSanitizeAttribute', (_node, data) => {
  if (data.attrName !== 'style') return
  const cleaned = sanitizeStyleAttr(data.attrValue)
  if (cleaned) {
    data.attrValue = cleaned
    data.keepAttr = true
  } else {
    data.keepAttr = false
  }
})

function createIframePurifier(allowedOrigins: string[]) {
  const purifier = DOMPurify(window)

  purifier.addHook('uponSanitizeAttribute', (_node, data) => {
    if (data.attrName !== 'style') return
    const cleaned = sanitizeStyleAttr(data.attrValue)
    if (cleaned) {
      data.attrValue = cleaned
      data.keepAttr = true
    } else {
      data.keepAttr = false
    }
  })

  purifier.addHook('uponSanitizeElement', (node, data) => {
    if (data.tagName !== 'iframe') return
    const src = (node as Element).getAttribute('src') ?? ''
    let allowed = false
    if (src && allowedOrigins.length) {
      try {
        const parsedSrc = new URL(src)
        if (['http:', 'https:'].includes(parsedSrc.protocol)) {
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
  })

  return purifier
}

export function sanitizeHtml(html: string): string {
  if (!html) return ''
  return _purify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS,
    FORBID_ATTR,
    ALLOW_DATA_ATTR: false,
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
  })
}

export function sanitizeHtmlAllowIframe(html: string, allowedOrigins: string[]): string {
  if (!html) return ''
  const purifier = createIframePurifier(allowedOrigins)
  return purifier.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: FORBID_TAGS.filter((t) => t !== 'iframe'),
    FORBID_ATTR,
    ALLOW_DATA_ATTR: false,
    ADD_TAGS: ['iframe'],
    ADD_ATTR: ['allowfullscreen', 'sandbox', 'loading'],
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.:-]|$))/i,
  })
}

const KB_ALLOWED_DOMAINS = [
  'youtube.com',
  'youtu.be',
  'youtube-nocookie.com',
  'rutube.ru',
  'vimeo.com',
  'vk.com',
  'vk.video',
]

function isKbIframeAllowed(src: string): boolean {
  try {
    const url = new URL(src)
    if (!['http:', 'https:'].includes(url.protocol)) return false
    return KB_ALLOWED_DOMAINS.some(
      (domain) => url.hostname === domain || url.hostname.endsWith(`.${domain}`)
    )
  } catch {
    return false
  }
}

function createKbPurifier() {
  const purifier = DOMPurify(window)

  purifier.addHook('uponSanitizeAttribute', (_node, data) => {
    if (data.attrName !== 'style') return
    const cleaned = sanitizeStyleAttr(data.attrValue)
    if (cleaned) {
      data.attrValue = cleaned
      data.keepAttr = true
    } else {
      data.keepAttr = false
    }
  })

  purifier.addHook('uponSanitizeElement', (node, data) => {
    if (data.tagName !== 'iframe') return
    const src = (node as Element).getAttribute('src') ?? ''
    if (!src || !isKbIframeAllowed(src)) {
      (node as Element).remove()
    }
  })

  return purifier
}

const _kbPurifier = createKbPurifier()

export function sanitizeKbHtml(html: string): string {
  if (!html) return ''
  return _kbPurifier.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: FORBID_TAGS.filter((t) => t !== 'iframe'),
    FORBID_ATTR,
    ALLOW_DATA_ATTR: false,
    ADD_TAGS: ['iframe', 'details', 'summary', 'figure', 'figcaption'],
    ADD_ATTR: ['allowfullscreen', 'sandbox', 'loading', 'data-type'],
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.:-]|$))/i,
  })
}
