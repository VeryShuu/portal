import { describe, it, expect, vi } from 'vitest'
import { colorFor, faviconFor, shortUrl, onIconError } from '../../src/composables/useLinkVisuals'

describe('colorFor', () => {
  it('returns a color from the palette', () => {
    const color = colorFor('https://example.com')
    expect(color).toMatch(/^#[0-9a-f]{6}$/i)
  })

  it('returns different colors for different urls', () => {
    const c1 = colorFor('https://a.com')
    const c2 = colorFor('https://b.com')
    expect(typeof c1).toBe('string')
    expect(typeof c2).toBe('string')
  })

  it('returns same color for same url', () => {
    expect(colorFor('https://same.com')).toBe(colorFor('https://same.com'))
  })

  it('handles empty string', () => {
    const color = colorFor('')
    expect(color).toMatch(/^#[0-9a-f]{6}$/i)
  })
})

describe('faviconFor', () => {
  it('returns favicon url for valid url', () => {
    expect(faviconFor('https://example.com/page')).toBe('https://example.com/favicon.ico')
  })

  it('returns null for invalid url', () => {
    expect(faviconFor('not-a-url')).toBeNull()
  })

  it('preserves port in origin', () => {
    expect(faviconFor('http://localhost:3000/path')).toBe('http://localhost:3000/favicon.ico')
  })
})

describe('shortUrl', () => {
  it('returns hostname without www', () => {
    expect(shortUrl('https://www.example.com/path')).toBe('example.com')
  })

  it('returns hostname for non-www url', () => {
    expect(shortUrl('https://example.com/path')).toBe('example.com')
  })

  it('returns raw string for invalid url', () => {
    expect(shortUrl('not-a-url')).toBe('not-a-url')
  })
})

describe('onIconError', () => {
  it('hides image on error', () => {
    const img = document.createElement('img')
    img.style.display = 'block'
    const event = { target: img } as unknown as Event
    onIconError(event)
    expect(img.style.display).toBe('none')
  })

  it('does nothing if target is not an image', () => {
    const event = { target: document.createElement('div') } as unknown as Event
    expect(() => onIconError(event)).not.toThrow()
  })
})
