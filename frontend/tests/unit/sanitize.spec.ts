/**
 * DOMPurify usage on the frontend (defense-in-depth for v-html).
 */
import { describe, it, expect } from 'vitest'
import DOMPurify from 'dompurify'
import { sanitizeHtml, sanitizeHtmlAllowIframe } from '../../src/utils/sanitize'

describe('DOMPurify (frontend XSS shield)', () => {
  it('strips <script>', () => {
    expect(DOMPurify.sanitize('<p>x</p><script>alert(1)</script>')).not.toContain('<script>')
  })

  it('strips inline event handlers', () => {
    const out = DOMPurify.sanitize('<a href="x" onclick="alert(1)">x</a>')
    expect(out.toLowerCase()).not.toContain('onclick')
  })

  it('rejects javascript: URLs', () => {
    const out = DOMPurify.sanitize('<a href="javascript:alert(1)">x</a>')
    expect(out.toLowerCase()).not.toContain('javascript:')
  })

  it('strips <iframe>', () => {
    expect(DOMPurify.sanitize('<iframe src="x"></iframe><p>ok</p>')).not.toContain('<iframe')
  })

  it('keeps safe formatting', () => {
    const out = DOMPurify.sanitize('<p><strong>bold</strong> <em>italic</em></p>')
    expect(out).toContain('<strong>')
    expect(out).toContain('<em>')
  })
})

describe('sanitizeHtml', () => {
  it('strips <script> tags', () => {
    const out = sanitizeHtml('<p>hello</p><script>alert(1)</script>')
    expect(out).not.toContain('<script>')
    expect(out).toContain('hello')
  })

  it('strips inline event handlers', () => {
    const out = sanitizeHtml('<p onclick="alert(1)">click</p>')
    expect(out.toLowerCase()).not.toContain('onclick')
  })

  it('rejects javascript: href', () => {
    const out = sanitizeHtml('<a href="javascript:alert(1)">link</a>')
    expect(out.toLowerCase()).not.toContain('javascript:')
  })

  it('allows safe http: href', () => {
    const out = sanitizeHtml('<a href="https://example.com">link</a>')
    expect(out).toContain('href="https://example.com"')
  })

  it('strips <iframe> even with https src', () => {
    const out = sanitizeHtml('<iframe src="https://evil.example.com"></iframe>')
    expect(out).not.toContain('<iframe')
  })

  it('strips <style> blocks', () => {
    const out = sanitizeHtml('<style>body{display:none}</style><p>ok</p>')
    expect(out).not.toContain('<style>')
    expect(out).toContain('ok')
  })

  it('strips <svg> with embedded script', () => {
    const out = sanitizeHtml('<svg><script>alert(1)</script></svg><p>ok</p>')
    expect(out).not.toContain('<svg')
    expect(out).not.toContain('<script')
  })

  it('allows text-align style, strips other styles', () => {
    const out = sanitizeHtml('<p style="text-align: center; color: red;">text</p>')
    expect(out).toContain('text-align: center')
    expect(out).not.toContain('color')
  })

  it('strips data-* attributes', () => {
    const out = sanitizeHtml('<p data-secret="yes">text</p>')
    expect(out).not.toContain('data-secret')
  })

  it('strips srcset attribute', () => {
    const out = sanitizeHtml('<img srcset="evil.jpg" src="ok.jpg" />')
    expect(out).not.toContain('srcset')
  })

  it('returns empty string for empty input', () => {
    expect(sanitizeHtml('')).toBe('')
  })

  it('blocks <iframe srcdoc=> XSS vector', () => {
    const out = sanitizeHtml('<iframe srcdoc="<script>alert(1)</script>"></iframe>')
    expect(out).not.toContain('<iframe')
    expect(out).not.toContain('<script')
  })
})

describe('sanitizeHtmlAllowIframe', () => {
  it('allows <iframe> from an allowed origin', () => {
    const out = sanitizeHtmlAllowIframe(
      '<iframe src="https://video.company.local/embed/1"></iframe>',
      ['https://video.company.local'],
    )
    expect(out).toContain('<iframe')
  })

  it('removes <iframe> from a disallowed origin', () => {
    const out = sanitizeHtmlAllowIframe(
      '<iframe src="https://evil.example.com/embed/1"></iframe>',
      ['https://video.company.local'],
    )
    expect(out).not.toContain('<iframe')
  })

  it('removes <iframe> when allowed list is empty', () => {
    const out = sanitizeHtmlAllowIframe(
      '<iframe src="https://anything.example.com"></iframe>',
      [],
    )
    expect(out).not.toContain('<iframe')
  })

  it('strips javascript: src even when origin list is provided', () => {
    const out = sanitizeHtmlAllowIframe(
      '<iframe src="javascript:alert(1)"></iframe>',
      ['javascript:alert(1)'],
    )
    expect(out).not.toContain('javascript:')
  })

  it('still strips <script> even with iframe allowed', () => {
    const out = sanitizeHtmlAllowIframe(
      '<iframe src="https://video.company.local/1"></iframe><script>alert(1)</script>',
      ['https://video.company.local'],
    )
    expect(out).toContain('<iframe')
    expect(out).not.toContain('<script')
  })

  it('allows allowfullscreen and sandbox attributes on iframe', () => {
    const out = sanitizeHtmlAllowIframe(
      '<iframe src="https://video.company.local/1" allowfullscreen sandbox="allow-scripts"></iframe>',
      ['https://video.company.local'],
    )
    expect(out).toContain('allowfullscreen')
    expect(out).toContain('sandbox')
  })

  it('returns empty string for empty input', () => {
    expect(sanitizeHtmlAllowIframe('', ['https://example.com'])).toBe('')
  })
})

describe('sanitizeHelpdeskHtml', () => {
  // Профиль для rich-сообщений helpdesk (TipTap FigureImage):
  // разрешает <figure>/<figcaption> и data-type, но НЕ <iframe>.

  it('returns empty string for empty input', async () => {
    const { sanitizeHelpdeskHtml } = await import('../../src/utils/sanitize')
    expect(sanitizeHelpdeskHtml('')).toBe('')
  })

  it('allows <figure> and <figcaption> (TipTap FigureImage caption)', async () => {
    const { sanitizeHelpdeskHtml } = await import('../../src/utils/sanitize')
    const html = '<figure data-type="figure-image"><img src="https://x/y.png" alt="d"/><figcaption>подпись</figcaption></figure>'
    const out = sanitizeHelpdeskHtml(html)
    expect(out).toContain('<figure')
    expect(out).toContain('<figcaption')
    expect(out).toContain('подпись')
  })

  it('keeps data-type attribute on figure (TipTap marker)', async () => {
    const { sanitizeHelpdeskHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeHelpdeskHtml('<figure data-type="figure-image"><p>x</p></figure>')
    expect(out).toContain('data-type="figure-image"')
  })

  it('allows relative /api/v1/helpdesk/.../inline-media URLs in <img>', async () => {
    const { sanitizeHelpdeskHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeHelpdeskHtml('<img src="/api/v1/helpdesk/tickets/1/inline-media/abc.jpg" />')
    expect(out).toContain('/api/v1/helpdesk/')
  })

  it('strips <iframe> (no video in helpdesk replies)', async () => {
    const { sanitizeHelpdeskHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeHelpdeskHtml('<iframe src="https://youtube.com/x"></iframe><p>ok</p>')
    expect(out).not.toContain('<iframe')
    expect(out).toContain('ok')
  })

  it('strips <script> and inline event handlers', async () => {
    const { sanitizeHelpdeskHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeHelpdeskHtml('<p onclick="alert(1)">x</p><script>alert(1)</script>')
    expect(out.toLowerCase()).not.toContain('onclick')
    expect(out).not.toContain('<script')
  })

  it('keeps only text-align in style attr (same hook as base profile)', async () => {
    const { sanitizeHelpdeskHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeHelpdeskHtml('<p style="text-align: right; background: red;">x</p>')
    expect(out).toContain('text-align: right')
    expect(out).not.toContain('background')
  })
})

describe('sanitizeKbHtml', () => {
  // Профиль для KB-статей: разрешает <iframe> только с доменов из KB_ALLOWED_DOMAINS
  // (youtube/rutube/vimeo/vk), а также <details>/<summary>/<figure>/<figcaption>.

  it('returns empty string for empty input', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    expect(sanitizeKbHtml('')).toBe('')
  })

  it('allows <iframe> from youtube.com', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="https://www.youtube.com/embed/abc"></iframe>')
    expect(out).toContain('<iframe')
    expect(out).toContain('youtube.com')
  })

  it('allows <iframe> from youtu.be', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="https://youtu.be/abc"></iframe>')
    expect(out).toContain('<iframe')
  })

  it('allows <iframe> from rutube.ru', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="https://rutube.ru/play/abc"></iframe>')
    expect(out).toContain('<iframe')
  })

  it('allows <iframe> from vk.com', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="https://vk.com/video_ext.php?oid=1"></iframe>')
    expect(out).toContain('<iframe')
  })

  it('removes <iframe> from foreign domain (evil.example.com)', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="https://evil.example.com/embed/x"></iframe>')
    expect(out).not.toContain('<iframe')
  })

  it('removes <iframe> with javascript: src', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="javascript:alert(1)"></iframe>')
    expect(out).not.toContain('<iframe')
    expect(out.toLowerCase()).not.toContain('javascript:')
  })

  it('removes <iframe> with empty src', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src=""></iframe>')
    expect(out).not.toContain('<iframe')
  })

  it('removes <iframe> with malformed URL (catch → not allowed)', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="not-a-url"></iframe>')
    expect(out).not.toContain('<iframe')
  })

  it('removes <iframe> with non-http protocol (data:)', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="data:text/html,<script>alert(1)</script>"></iframe>')
    expect(out).not.toContain('<iframe')
  })

  it('allows subdomain of allowed domain (www.youtube.com)', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="https://www.youtube.com/embed/x"></iframe>')
    expect(out).toContain('<iframe')
  })

  it('allows <details>/<summary>', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<details><summary>spoiler</summary><p>hidden</p></details>')
    expect(out).toContain('<details')
    expect(out).toContain('<summary')
  })

  it('allows <figure>/<figcaption> with data-type', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<figure data-type="figure-image"><img src="https://x/y.png"/><figcaption>c</figcaption></figure>')
    expect(out).toContain('<figure')
    expect(out).toContain('<figcaption')
  })

  it('keeps allowfullscreen/sandbox/loading on iframe', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<iframe src="https://www.youtube.com/embed/x" allowfullscreen sandbox="allow-scripts" loading="lazy"></iframe>')
    expect(out).toContain('allowfullscreen')
    expect(out).toContain('sandbox')
    expect(out).toContain('loading')
  })

  it('keeps only text-align in style attr', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<p style="text-align: justify; opacity: 0.5;">x</p>')
    expect(out).toContain('text-align: justify')
    expect(out).not.toContain('opacity')
  })

  it('strips <script> tags', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<p>ok</p><script>alert(1)</script>')
    expect(out).not.toContain('<script')
    expect(out).toContain('ok')
  })
})

// ── Edge-cases для style-sanitize hook в каждом purifier ────────────────────
// Покрывают ветки 31/40-45/62/155 в src/utils/sanitize.ts:
// - style attr без text-align → drop (keepAttr=false ветка)
// - malformed iframe URL в sanitizeHtmlAllowIframe → catch → iframe removed
// - style-sanitize hook в KB/iframe purifier'ах

describe('style-attr sanitize hook — covers keepAttr=false branches', () => {
  it('sanitizeHtml drops style attr with no text-align (base purifier)', async () => {
    const { sanitizeHtml } = await import('../../src/utils/sanitize')
    // color: red не проходит TEXT_ALIGN_RE → весь style удаляется → keepAttr=false.
    const out = sanitizeHtml('<p style="color: red; font-size: 20px;">x</p>')
    expect(out).not.toContain('color')
    expect(out).not.toContain('font-size')
    expect(out).toContain('x')
  })

  it('sanitizeHtmlAllowIframe: style hook drops non-text-align in iframe content', async () => {
    const { sanitizeHtmlAllowIframe } = await import('../../src/utils/sanitize')
    const out = sanitizeHtmlAllowIframe(
      '<p style="text-align: center">ok</p><span style="opacity: 0.5">o</span>',
      ['https://example.com'],
    )
    expect(out).toContain('text-align: center')
    expect(out).not.toContain('opacity')
  })

  it('sanitizeKbHtml: style hook drops non-text-align', async () => {
    const { sanitizeKbHtml } = await import('../../src/utils/sanitize')
    const out = sanitizeKbHtml('<p style="margin: 10px;">x</p>')
    expect(out).not.toContain('margin')
    expect(out).toContain('x')
  })

  it('sanitizeHtmlAllowIframe: malformed allowed-origin URL → catch → iframe removed', async () => {
    const { sanitizeHtmlAllowIframe } = await import('../../src/utils/sanitize')
    // allowedOrigins содержит синтаксически невалидный URL → new URL(o) бросает →
    // catch-branch в .some((o) => { try { return new URL(o)... } catch {...} })
    // возвращает false → origin не матчит → iframe удаляется.
    // Регрессия на устойчивость парсинга списка при битой настройке.
    const out = sanitizeHtmlAllowIframe(
      '<iframe src="https://example.com/x"></iframe>',
      ['http://[broken'],
    )
    expect(out).not.toContain('<iframe')
  })

  it('sanitizeHtmlAllowIframe: non-http protocol in src (file:) → not allowed', async () => {
    const { sanitizeHtmlAllowIframe } = await import('../../src/utils/sanitize')
    const out = sanitizeHtmlAllowIframe(
      '<iframe src="file:///etc/passwd"></iframe>',
      ['file:///etc/passwd'],
    )
    expect(out).not.toContain('<iframe')
  })

  it('sanitizeHtmlAllowIframe: malformed src URL → outer catch → iframe removed', async () => {
    const { sanitizeHtmlAllowIframe } = await import('../../src/utils/sanitize')
    // src='http://[broken' — new URL(src) бросает → внешний catch (строка 61-62)
    // выставляет allowed=false → iframe удаляется. Регрессия на устойчивость
    // при битом src (DOMPurify мог пропустить дальше при др. конфигурации).
    const out = sanitizeHtmlAllowIframe(
      '<iframe src="http://[broken"></iframe>',
      ['https://example.com'],
    )
    expect(out).not.toContain('<iframe')
  })
})
