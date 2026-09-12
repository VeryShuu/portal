/**
 * Unit-тесты ZIP-разборщика e2e (audit-review follow-up, P1).
 * Фикстуры-байты сгенерированы python-zipfile: stored (method 0) и
 * deflate (method 8) — как реальный экспорт портала.
 */
import { describe, it, expect } from 'vitest'
import { readZipEntries, makeStoredZip } from '../../tests/e2e/fixtures/zip'

const STORED_B64 =
  'UEsDBBQAAAAAAKmeFl11tkPIFAAAABQAAAAKAAAAYS9oZWxsby5tZCMg0J/RgNC40LLQtdGCIHdvcmxkUEsDBBQAAAgAAKmeFl1ZbH2XCwAAAAsAAAARAAAAYi/QstGC0L7RgNC+0LkubWRjb250ZW50IHR3b1BLAQIUAxQAAAAAAKmeFl11tkPIFAAAABQAAAAKAAAAAAAAAAAAAACAAQAAAABhL2hlbGxvLm1kUEsBAhQDFAAACAAAqZ4WXVlsfZcLAAAACwAAABEAAAAAAAAAAAAAAIABPAAAAGIv0LLRgtC+0YDQvtC5Lm1kUEsFBgAAAAACAAIAdwAAAHYAAAAAAA=='
const DEFLATE_B64 =
  'UEsDBBQAAAAIAKmeFl11tkPIFwAAABQAAAAKAAAAYS9oZWxsby5tZFNWuDD/YsOFHRc2Xdh6sUmhPL8oJwUAUEsDBBQAAAgIAKmeFl1ZbH2XDQAAAAsAAAARAAAAYi/QstGC0L7RgNC+0LkubWRLzs8rSc0rUSgpzwcAUEsBAhQDFAAAAAgAqZ4WXXW2Q8gXAAAAFAAAAAoAAAAAAAAAAAAAAIABAAAAAGEvaGVsbG8ubWRQSwECFAMUAAAICACpnhZdWWx9lw0AAAALAAAAEQAAAAAAAAAAAAAAgAE/AAAAYi/QstGC0L7RgNC+0LkubWRQSwUGAAAAAAIAAgB3AAAAewAAAAAA'

describe('readZipEntries (реальные python-zipfile архивы)', () => {
  it('stored (method 0): обе записи, содержимое без искажений', () => {
    const entries = readZipEntries(Buffer.from(STORED_B64, 'base64'))
    expect(entries.map((e) => e.path).sort()).toEqual(['a/hello.md', 'b/второй.md'])
    const hello = entries.find((e) => e.path === 'a/hello.md')!
    expect(hello.data.toString('utf-8')).toContain('# Привет world')
  })

  it('deflate (method 8): записи распаковываются inflateRaw', () => {
    const entries = readZipEntries(Buffer.from(DEFLATE_B64, 'base64'))
    expect(entries.length).toBeGreaterThan(0)
    const hello = entries.find((e) => e.path === 'a/hello.md')
    expect(hello).toBeTruthy()
    expect(hello!.data.toString('utf-8')).toContain('# Привет world')
  })

  it('roundtrip с собственным makeStoredZip', () => {
    const zip = makeStoredZip([{ path: 'x.md', data: '# Заголовок' }])
    const entries = readZipEntries(Buffer.from(zip))
    expect(entries[0].path).toBe('x.md')
    expect(entries[0].data.toString('utf-8')).toBe('# Заголовок')
  })

  it('не-ZIP байты → понятная ошибка', () => {
    expect(() => readZipEntries(Buffer.from('это не архив'))).toThrow(/EOCD/)
  })
})
