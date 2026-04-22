import { describe, it, expect } from 'vitest'
import { isSafeHttpUrl } from '../../src/utils/url'

describe('isSafeHttpUrl', () => {
  it('accepts http and https', () => {
    expect(isSafeHttpUrl('http://example.com')).toBe(true)
    expect(isSafeHttpUrl('https://example.com/path?x=1')).toBe(true)
  })

  it.each([
    'javascript:alert(1)',
    'JavaScript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'vbscript:msgbox(1)',
    'file:///etc/passwd',
    'about:blank',
  ])('rejects dangerous protocol %s', (url) => {
    expect(isSafeHttpUrl(url)).toBe(false)
  })

  it('rejects empty / null / invalid', () => {
    expect(isSafeHttpUrl(null)).toBe(false)
    expect(isSafeHttpUrl(undefined)).toBe(false)
    expect(isSafeHttpUrl('')).toBe(false)
    expect(isSafeHttpUrl('not a url')).toBe(false)
  })
})
