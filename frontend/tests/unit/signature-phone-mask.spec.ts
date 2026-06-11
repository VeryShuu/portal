import { describe, expect, it } from 'vitest'
import { formatRuPhone } from '../../src/pages/composables/useSignatureForm'

describe('formatRuPhone', () => {
  it('returns empty string for empty input', () => {
    expect(formatRuPhone('')).toBe('')
    expect(formatRuPhone('abc')).toBe('')
  })

  it('formats a full 11-digit number', () => {
    expect(formatRuPhone('79001234567')).toBe('+7 (900) 123 4567')
  })

  it('normalises leading 8 to 7', () => {
    expect(formatRuPhone('89001234567')).toBe('+7 (900) 123 4567')
  })

  it('prefixes 7 when missing', () => {
    expect(formatRuPhone('9001234567')).toBe('+7 (900) 123 4567')
  })

  it('formats partial input progressively', () => {
    expect(formatRuPhone('790')).toBe('+7 (90')
    expect(formatRuPhone('7900')).toBe('+7 (900)')
    expect(formatRuPhone('7900123')).toBe('+7 (900) 123')
  })

  it('ignores non-digits and caps at 11 digits', () => {
    expect(formatRuPhone('+7 (900) 123-45-67 89')).toBe('+7 (900) 123 4567')
  })
})
