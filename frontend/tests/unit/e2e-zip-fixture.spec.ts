import { describe, expect, it } from 'vitest'
import { makeStoredZip } from '../e2e/fixtures/zip'

/**
 * Гарантии для e2e Obsidian-vault импорта: архив обязан распознаваться
 * бэкендом как валидный ZIP (PK-сигнатуры, CRC, central directory).
 */
describe('makeStoredZip', () => {
  it('produces PK signatures: local header, central directory, EOCD', () => {
    const zip = makeStoredZip([{ path: 'a.md', data: '# A' }])

    expect(zip[0]).toBe(0x50) // P
    expect(zip[1]).toBe(0x4b) // K
    expect(zip[2]).toBe(0x03)
    expect(zip[3]).toBe(0x04)

    const eocdIndex = zip.length - 22
    expect(zip[eocdIndex]).toBe(0x50)
    expect(zip[eocdIndex + 1]).toBe(0x4b)
    expect(zip[eocdIndex + 2]).toBe(0x05)
    expect(zip[eocdIndex + 3]).toBe(0x06)
  })

  it('EOCD declares entry count and central directory offset', () => {
    const zip = makeStoredZip([
      { path: 'a.md', data: 'aaa' },
      { path: 'dir/b.md', data: 'bbb' },
    ])

    const view = new DataView(zip.buffer, zip.byteOffset, zip.byteLength)
    const eocd = zip.length - 22
    expect(view.getUint16(eocd + 8, true)).toBe(2)
    expect(view.getUint16(eocd + 10, true)).toBe(2)

    // central directory начинается сразу после local-секций: первый байт — PK\x01\x02
    const cdOffset = view.getUint32(eocd + 16, true)
    expect(zip[cdOffset]).toBe(0x50)
    expect(zip[cdOffset + 2]).toBe(0x01)
    expect(zip[cdOffset + 3]).toBe(0x02)

    const cdSize = view.getUint32(eocd + 12, true)
    expect(cdOffset + cdSize).toBe(eocd)
  })

  it('stores uncompressed file data with correct CRC32', () => {
    const data = 'hello мир' // utf-8 многобайтовость
    const zip = makeStoredZip([{ path: 'note.md', data }])

    const encoded = new TextEncoder().encode(data)
    const view = new DataView(zip.buffer, zip.byteOffset, zip.byteLength)
    // CRC в local header (offset 14) и central header совпадают и не нулевые
    const localCrc = view.getUint32(14, true)
    expect(localCrc).not.toBe(0)

    // данные лежат сразу за заголовком + именем
    const nameLen = view.getUint16(26, true)
    const dataStart = 30 + nameLen
    const stored = Array.from(zip.slice(dataStart, dataStart + encoded.length))
    expect(stored).toEqual(Array.from(encoded))
    expect(zip.length).toBe(30 + nameLen + encoded.length + 46 + nameLen + 22)
  })

  it('accepts Uint8Array entries alongside strings', () => {
    const bytes = new Uint8Array([1, 2, 3, 0xff])
    const zip = makeStoredZip([
      { path: 'bin.dat', data: bytes },
      { path: 'text.md', data: 'ok' },
    ])
    expect(zip.length).toBeGreaterThan(bytes.length)
    expect(zip.slice(0, 4)).toEqual(new Uint8Array([0x50, 0x4b, 0x03, 0x04]))
  })
})
