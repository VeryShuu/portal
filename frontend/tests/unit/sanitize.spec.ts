/**
 * DOMPurify usage on the frontend (defense-in-depth for v-html).
 */
import { describe, it, expect } from 'vitest'
import DOMPurify from 'dompurify'

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
