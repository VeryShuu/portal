/**
 * Unit-тесты расчёта «возраста» заявки — дней от ``created_at``.
 *
 * Функция ``ticketAgeDays`` вынесена из компонента в утилиту именно для прямого
 * тестирования (по конвенции проекта — характеристика перед декомпозицией).
 * Граница дня — календарные сутки UTC (детерминированно в тестах, не зависит
 * от TZ машины CI).
 */
import { describe, it, expect } from 'vitest'
import { ticketAgeDays } from '../../src/utils/helpdeskTicketAge'

describe('ticketAgeDays', () => {
  it('возвращает 0 для тикета, созданного сейчас', () => {
    const now = new Date('2026-08-04T12:00:00Z')
    const created = new Date('2026-08-04T11:59:00Z').toISOString()
    expect(ticketAgeDays(created, now)).toBe(0)
  })

  it('возвращает 0 для будущего created_at (защита от отрицательных)', () => {
    const now = new Date('2026-08-04T12:00:00Z')
    const created = new Date('2026-08-05T12:00:00Z').toISOString()
    expect(ticketAgeDays(created, now)).toBe(0)
  })

  it('возвращает 1 ровно через 24 часа', () => {
    const now = new Date('2026-08-05T12:00:00Z')
    const created = new Date('2026-08-04T12:00:00Z').toISOString()
    expect(ticketAgeDays(created, now)).toBe(1)
  })

  it('считает полные дни (отбрасывая дробную часть)', () => {
    // 1.9 дня = 1 полный день
    const now = new Date('2026-08-06T10:24:00Z')
    const created = new Date('2026-08-04T12:00:00Z').toISOString()
    expect(ticketAgeDays(created, now)).toBe(1)
  })

  it('возвращает N дней для давней заявки', () => {
    const now = new Date('2026-08-04T00:00:00Z')
    const created = new Date('2026-07-01T00:00:00Z').toISOString()
    // июль имеет 31 день → 31 день до 1 августа + 3 дня = 34
    expect(ticketAgeDays(created, now)).toBe(34)
  })

  it('возвращает 0 для невалидной даты', () => {
    expect(ticketAgeDays('not-a-date')).toBe(0)
    expect(ticketAgeDays('')).toBe(0)
  })

  it('возвращает 0 для пустой строки (гостевые/edge)', () => {
    expect(ticketAgeDays('', new Date())).toBe(0)
  })
})
