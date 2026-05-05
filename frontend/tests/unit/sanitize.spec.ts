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
