import { describe, it, expect } from 'vitest'
import { isSafeHttpUrl, isInternalLinkUrl, isServiceLinkUrl } from '../../src/utils/url'

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

describe('isInternalLinkUrl', () => {
  it('accepts root-relative paths', () => {
    expect(isInternalLinkUrl('/signature')).toBe(true)
    expect(isInternalLinkUrl('/staff?tab=fleet')).toBe(true)
  })

  it.each([
    '//evil.com',
    'https://example.com',
    'signature',
    '../x',
    '',
  ])('rejects non-internal %s', (url) => {
    expect(isInternalLinkUrl(url)).toBe(false)
  })
})

describe('isServiceLinkUrl', () => {
  it('accepts both external https and internal paths', () => {
    expect(isServiceLinkUrl('https://example.com')).toBe(true)
    expect(isServiceLinkUrl('/signature')).toBe(true)
  })

  it.each([
    '//evil.com',
    'javascript:alert(1)',
    'ftp://bad.com',
    'signature',
  ])('rejects unsafe / non-internal %s', (url) => {
    expect(isServiceLinkUrl(url)).toBe(false)
  })
})
