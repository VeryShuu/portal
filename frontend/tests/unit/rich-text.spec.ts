import { describe, it, expect } from 'vitest'
import { richToPlainText } from '../../src/utils/richText'

/**
 * richToPlainText — чистый текст из rich-описания для превью-отрывков
 * (прод-кейс 2026-09-03: карточка курса показывала сырые `&nbsp;` и `**`).
 */

describe('richToPlainText', () => {
  it('разворачивает HTML-сущности и снимает markdown-разметку', () => {
    const raw = 'Цель вводного инструктажа — &nbsp;**важно** сформировать [правила](https://x)'
    expect(richToPlainText(raw)).toBe('Цель вводного инструктажа — важно сформировать правила')
  })

  it('удаляет картинки и код-блоки', () => {
    const raw = 'Текст ![картинка](https://x/i.png) продолжение\n\n```js\ncode()\n```'
    const out = richToPlainText(raw)
    expect(out).toContain('Текст')
    expect(out).toContain('продолжение')
    expect(out).not.toContain('code()')
    expect(out).not.toContain('картинка')
  })

  it('схлопывает пробелы, включая &nbsp;', () => {
    expect(richToPlainText('a&nbsp;&nbsp;&nbsp;b')).toBe('a b')
  })

  it('обрезает длинный текст до лимита с многоточием', () => {
    const out = richToPlainText('слово '.repeat(60))
    expect(out.length).toBeLessThanOrEqual(161)
    expect(out.endsWith('…')).toBe(true)
  })
})
