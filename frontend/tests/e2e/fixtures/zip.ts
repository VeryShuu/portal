import { inflateRawSync } from 'node:zlib'
/**
 * Минимальный builder ZIP-архивов (метод stored, без сжатия) для e2e-тестов.
 *
 * Заменяет динамический import JSZip с CDN: в CI тот импорт молча падал и
 * тест импорта Obsidian-vault тихо skip'ался (см. аудит тестового контура).
 * Формат — обычный ZIP: local file headers → данные → central directory → EOCD.
 */

export interface ZipEntry {
  path: string
  data: string | Uint8Array
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let i = 0; i < 256; i++) {
    let c = i
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    }
    table[i] = c >>> 0
  }
  return table
})()

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff
  for (let i = 0; i < bytes.length; i++) {
    crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

function toBytes(data: string | Uint8Array): Uint8Array {
  if (typeof data !== 'string') return data
  return new TextEncoder().encode(data)
}

function dosDateTime(): { time: number; date: number } {
  // Фиксированная дата (2024-01-01 00:00) — содержимое от неё не зависит.
  return { time: 0, date: ((2024 - 1980) << 9) | (1 << 5) | 1 }
}

/** Собрать ZIP с файлами без сжатия (method 0). Возвращает байты архива. */
export function makeStoredZip(entries: ZipEntry[]): Uint8Array {
  const { time, date } = dosDateTime()
  const locals: Uint8Array[] = []
  const centrals: Uint8Array[] = []
  let offset = 0

  for (const entry of entries) {
    const nameBytes = toBytes(entry.path)
    const dataBytes = toBytes(entry.data)
    const crc = crc32(dataBytes)

    const local = new Uint8Array(30 + nameBytes.length + dataBytes.length)
    const localView = new DataView(local.buffer)
    localView.setUint32(0, 0x04034b50, true) // PK\x03\x04
    localView.setUint16(4, 20, true) // version needed
    localView.setUint16(6, 0x0800, true) // flags: UTF-8 имён
    localView.setUint16(8, 0, true) // method: stored
    localView.setUint16(10, time, true)
    localView.setUint16(12, date, true)
    localView.setUint32(14, crc, true)
    localView.setUint32(18, dataBytes.length, true) // compressed size
    localView.setUint32(22, dataBytes.length, true) // uncompressed size
    localView.setUint16(26, nameBytes.length, true)
    localView.setUint16(28, 0, true) // extra length
    local.set(nameBytes, 30)
    local.set(dataBytes, 30 + nameBytes.length)
    locals.push(local)

    const central = new Uint8Array(46 + nameBytes.length)
    const centralView = new DataView(central.buffer)
    centralView.setUint32(0, 0x02014b50, true) // PK\x01\x02
    centralView.setUint16(4, 20, true) // version made by
    centralView.setUint16(6, 20, true) // version needed
    centralView.setUint16(8, 0x0800, true) // flags: UTF-8
    centralView.setUint16(10, 0, true) // method: stored
    centralView.setUint16(12, time, true)
    centralView.setUint16(14, date, true)
    centralView.setUint32(16, crc, true)
    centralView.setUint32(20, dataBytes.length, true)
    centralView.setUint32(24, dataBytes.length, true)
    centralView.setUint16(28, nameBytes.length, true)
    centralView.setUint16(30, 0, true) // extra length
    centralView.setUint16(32, 0, true) // comment length
    centralView.setUint16(34, 0, true) // disk number start
    centralView.setUint16(36, 0, true) // internal attributes
    centralView.setUint32(38, 0, true) // external attributes
    centralView.setUint32(42, offset, true) // local header offset
    central.set(nameBytes, 46)
    centrals.push(central)

    offset += local.length
  }

  const centralSize = centrals.reduce((sum, c) => sum + c.length, 0)
  const eocd = new Uint8Array(22)
  const eocdView = new DataView(eocd.buffer)
  eocdView.setUint32(0, 0x06054b50, true) // PK\x05\x06
  eocdView.setUint16(8, entries.length, true)
  eocdView.setUint16(10, entries.length, true)
  eocdView.setUint32(12, centralSize, true)
  eocdView.setUint32(16, offset, true)

  const total = offset + centralSize + eocd.length
  const out = new Uint8Array(total)
  let pos = 0
  for (const chunk of [...locals, ...centrals, eocd]) {
    out.set(chunk, pos)
    pos += chunk.length
  }
  return out
}

/**
 * Разбор реального ZIP: EOCD → central directory → local headers.
 * Поддерживает stored (method 0) и deflate (method 8, inflateRaw) —
 * audit-review follow-up, P1: сигнатуры и подстрок недостаточно, архив
 * обязан разбираться с проверкой имён и содержимого записей.
 */
export function readZipEntries(buf: Buffer): Array<{ path: string; data: Buffer }> {
  // EOCD: ищем с конца (комментарий архива возможен)
  let eocd = -1
  for (let i = buf.length - 22; i >= 0; i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new Error('ZIP: EOCD не найден — это не ZIP-архив')

  const entriesCount = buf.readUInt16LE(eocd + 10)
  let cdOffset = buf.readUInt32LE(eocd + 16)

  const out: Array<{ path: string; data: Buffer }> = []
  for (let n = 0; n < entriesCount; n++) {
    if (buf.readUInt32LE(cdOffset) !== 0x02014b50) throw new Error(`ZIP: битый central header #${n}`)
    const method = buf.readUInt16LE(cdOffset + 10)
    const compressedSize = buf.readUInt32LE(cdOffset + 20)
    const nameLen = buf.readUInt16LE(cdOffset + 28)
    const extraLen = buf.readUInt16LE(cdOffset + 30)
    const commentLen = buf.readUInt16LE(cdOffset + 32)
    const localOffset = buf.readUInt32LE(cdOffset + 42)
    const path = buf.subarray(cdOffset + 46, cdOffset + 46 + nameLen).toString('utf-8')

    // local header: фактические длины имени/extra могут отличаться от CD
    if (buf.readUInt32LE(localOffset) !== 0x04034b50) throw new Error(`ZIP: битый local header (${path})`)
    const lNameLen = buf.readUInt16LE(localOffset + 26)
    const lExtraLen = buf.readUInt16LE(localOffset + 28)
    const dataStart = localOffset + 30 + lNameLen + lExtraLen
    const raw = buf.subarray(dataStart, dataStart + compressedSize)

    let data: Buffer
    if (method === 0) {
      data = Buffer.from(raw)
    } else if (method === 8) {
      data = inflateRawSync(raw)
    } else {
      throw new Error(`ZIP: неподдерживаемый method=${method} (${path})`)
    }
    out.push({ path, data })
    cdOffset += 46 + nameLen + extraLen + commentLen
  }
  return out
}
