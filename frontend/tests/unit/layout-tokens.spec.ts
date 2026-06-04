import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const tokensCss = readFileSync(
  resolve(process.cwd(), 'src/styles/tokens.css'),
  'utf-8',
)

const utilitiesCss = readFileSync(
  resolve(process.cwd(), 'src/styles/utilities.css'),
  'utf-8',
)

function tokenValue(name: string): string | null {
  const m = tokensCss.match(new RegExp(`${name}\\s*:\\s*([^;]+);`))
  return m ? m[1].trim() : null
}

function ruleBody(selector: string): string | null {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const m = utilitiesCss.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))
  return m ? m[1].trim() : null
}

describe('layout tokens — единая шкала брейкпоинтов и ширин', () => {
  it('брейкпоинты соответствуют индустриальной шкале (Tailwind)', () => {
    expect(tokenValue('--bp-sm')).toBe('640px')
    expect(tokenValue('--bp-md')).toBe('768px')
    expect(tokenValue('--bp-lg')).toBe('1024px')
    expect(tokenValue('--bp-xl')).toBe('1280px')
    expect(tokenValue('--bp-2xl')).toBe('1536px')
  })

  it('три осознанных класса ширины контента', () => {
    expect(tokenValue('--content-reading')).toBe('768px')
    expect(tokenValue('--content-standard')).toBe('1280px')
    expect(tokenValue('--content-wide')).toBe('1600px')
  })

  it('fluid-gutter задан через clamp()', () => {
    const gutter = tokenValue('--page-gutter')
    expect(gutter).not.toBeNull()
    expect(gutter).toMatch(/^clamp\(\s*16px\s*,\s*4vw\s*,\s*48px\s*\)$/)
  })

  it('--layout-content-max сохранён как алиас на --content-standard (обратная совместимость)', () => {
    expect(tokenValue('--layout-content-max')).toBe('var(--content-standard)')
  })
})

describe('.u-page-wrap — fluid-контейнер', () => {
  it('базовый wrapper использует fluid min() + margin-inline и standard-ширину', () => {
    const body = ruleBody('.u-page-wrap')
    expect(body).not.toBeNull()
    expect(body).toMatch(/width:\s*min\(/)
    expect(body).toMatch(/var\(--page-gutter\)/)
    expect(body).toMatch(/var\(--content-standard\)/)
    expect(body).toMatch(/margin-inline:\s*auto/)
  })

  it('модификатор --reading сужает до reading-ширины', () => {
    const body = ruleBody('.u-page-wrap--reading')
    expect(body).not.toBeNull()
    expect(body).toMatch(/var\(--content-reading\)/)
  })

  it('модификатор --wide расширяет до wide-ширины', () => {
    const body = ruleBody('.u-page-wrap--wide')
    expect(body).not.toBeNull()
    expect(body).toMatch(/var\(--content-wide\)/)
  })
})
