import { describe, it, expect } from 'vitest'
import { buildUsersExportUrl } from '../../src/api/users'

describe('buildUsersExportUrl', () => {
  it('builds base URL with format=csv when no params provided', () => {
    const url = buildUsersExportUrl()
    expect(url).toMatch(/\/users\/export\?format=csv$/)
  })

  it('omits empty / undefined optional params', () => {
    const url = buildUsersExportUrl({ q: '', department: undefined, office: '' })
    expect(url).toMatch(/\/users\/export\?format=csv$/)
    expect(url).not.toContain('q=')
    expect(url).not.toContain('department=')
    expect(url).not.toContain('office=')
  })

  it('includes provided params and sets format=csv', () => {
    const url = buildUsersExportUrl({
      q: 'иван',
      department: 'ИТ',
      office: 'Москва',
      sort: 'department',
    })
    expect(url).toContain('q=')
    expect(url).toContain('department=')
    expect(url).toContain('office=')
    expect(url).toContain('sort=department')
    expect(url).toContain('format=csv')
  })

  it('URL-encodes parameter values (Cyrillic and special chars)', () => {
    const url = buildUsersExportUrl({ q: 'иван&петров' })
    // URLSearchParams encodes Cyrillic as %XX
    expect(url).toContain('q=%D0%B8%D0%B2%D0%B0%D0%BD%26%D0%BF%D0%B5%D1%82%D1%80%D0%BE%D0%B2')
    // raw '&' must not leak as separator
    const queryStr = url.split('?')[1] ?? ''
    const params = new URLSearchParams(queryStr)
    expect(params.get('q')).toBe('иван&петров')
    expect(params.get('format')).toBe('csv')
  })

  it('points at /users/export endpoint', () => {
    const url = buildUsersExportUrl({ sort: 'full_name' })
    expect(url.endsWith('/users/export?sort=full_name&format=csv')).toBe(true)
  })
})
