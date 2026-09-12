/**
 * Characterization-тест русской плюрализации для колонки «Возраст заявки».
 *
 * ``ageDays`` — первый plural-ключ в проекте (``{n} день | {n} дня | {n} дней``).
 * Vue-i18n по умолчанию знает только English-логику (one/other), поэтому в
 * ``i18n/index.ts`` добавлено правило ``pluralRules.ru`` (CLDR one/few/many).
 * Без него «2 дня»/«5 дней» перепутались бы. Тест покрывает все три формы +
 * подростков (11–14 → many) — типичная ловушка русской морфологии.
 */
import { describe, it, expect } from 'vitest'
import { i18n } from '../../src/i18n/index'

const t = i18n.global.t

describe('helpdesk.ageDays — русская плюрализация', () => {
  it('one: 1, 21, 31 → «день»', () => {
    expect(t('helpdesk.ageDays', 1)).toBe('1 день')
    expect(t('helpdesk.ageDays', 21)).toBe('21 день')
    expect(t('helpdesk.ageDays', 31)).toBe('31 день')
  })

  it('few: 2–4, 22–24 → «дня»', () => {
    expect(t('helpdesk.ageDays', 2)).toBe('2 дня')
    expect(t('helpdesk.ageDays', 3)).toBe('3 дня')
    expect(t('helpdesk.ageDays', 4)).toBe('4 дня')
    expect(t('helpdesk.ageDays', 22)).toBe('22 дня')
    expect(t('helpdesk.ageDays', 24)).toBe('24 дня')
  })

  it('many: 0, 5–20, 25–30 → «дней»', () => {
    expect(t('helpdesk.ageDays', 0)).toBe('0 дней')
    expect(t('helpdesk.ageDays', 5)).toBe('5 дней')
    expect(t('helpdesk.ageDays', 12)).toBe('12 дней')
    expect(t('helpdesk.ageDays', 13)).toBe('13 дней')
    // подростки 11–14 — всегда many, даже если последняя цифра 1–4
    expect(t('helpdesk.ageDays', 11)).toBe('11 дней')
    expect(t('helpdesk.ageDays', 14)).toBe('14 дней')
    expect(t('helpdesk.ageDays', 25)).toBe('25 дней')
    expect(t('helpdesk.ageDays', 30)).toBe('30 дней')
  })
})
