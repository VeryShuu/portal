/**
 * formatAmount: группировка разрядов и запятая как десятичный
 * разделитель в ru-локали (суммы согласования, формат как в 1С/PHP).
 * Intl группирует неразрывными пробелами (U+00A0/U+202F) — нормализуем.
 */
import { describe, it, expect } from 'vitest'
import { formatAmount } from '../../src/utils/formatAmount'

const fmt = (n: number, locale = 'ru'): string =>
  formatAmount(n, locale).replace(/[\u00A0\u202F]/g, ' ')

describe('formatAmount', () => {
  it('целые — с разделителями разрядов', () => {
    expect(fmt(97899)).toBe('97 899')
  })

  it('дробные — запятая и два знака', () => {
    expect(fmt(97899.71)).toBe('97 899,71')
  })

  it('миллионы', () => {
    expect(fmt(1234567)).toBe('1 234 567')
  })

  it('не добавляет хвостовые нули', () => {
    expect(fmt(308.7)).toBe('308,7')
  })

  it('en-локаль — запятая-разделитель, точка-десятичная', () => {
    expect(fmt(1234567.89, 'en')).toBe('1,234,567.89')
  })
})
