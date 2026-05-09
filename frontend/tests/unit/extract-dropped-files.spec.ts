import { describe, it, expect } from 'vitest'
import { extractDroppedFiles } from '../../src/utils/extractDroppedFiles'

function makeFile(name: string): File {
  return new File(['content'], name, { type: 'text/plain' })
}

function makeDataTransferWithItems(
  entries: Array<{ kind: string; file?: File; isDirectory?: boolean }>
): DataTransfer {
  const items = entries.map(({ kind, file, isDirectory }) => ({
    kind,
    getAsFile: () => file ?? null,
    webkitGetAsEntry: isDirectory !== undefined
      ? () => ({ isDirectory })
      : undefined,
  }))
  return {
    items: { length: items.length, [Symbol.iterator]: function* () { yield* items }, ...Object.fromEntries(items.map((item, i) => [i, item])) },
    files: { length: 0 } as unknown as FileList,
  } as unknown as DataTransfer
}

function makeDataTransferWithFiles(files: File[]): DataTransfer {
  const fileList = Object.assign(files, { item: (i: number) => files[i] })
  return {
    items: { length: 0 } as unknown as DataTransferItemList,
    files: fileList as unknown as FileList,
  } as unknown as DataTransfer
}

describe('extractDroppedFiles', () => {
  it('empty DataTransfer returns empty result', async () => {
    const dt = { items: { length: 0 } as unknown as DataTransferItemList, files: { length: 0 } as unknown as FileList } as DataTransfer
    const result = await extractDroppedFiles(dt)
    expect(result.files).toHaveLength(0)
    expect(result.hadFolders).toBe(false)
  })

  it('files via dt.items are returned correctly', async () => {
    const file1 = makeFile('a.txt')
    const file2 = makeFile('b.txt')
    const dt = makeDataTransferWithItems([
      { kind: 'file', file: file1, isDirectory: false },
      { kind: 'file', file: file2, isDirectory: false },
    ])
    const result = await extractDroppedFiles(dt)
    expect(result.files).toHaveLength(2)
    expect(result.files[0].name).toBe('a.txt')
    expect(result.hadFolders).toBe(false)
  })

  it('files via dt.files fallback are returned correctly', async () => {
    const file = makeFile('c.png')
    const dt = makeDataTransferWithFiles([file])
    const result = await extractDroppedFiles(dt)
    expect(result.files).toHaveLength(1)
    expect(result.files[0].name).toBe('c.png')
    expect(result.hadFolders).toBe(false)
  })

  it('directory via webkitGetAsEntry sets hadFolders=true and is skipped', async () => {
    const dt = makeDataTransferWithItems([
      { kind: 'file', isDirectory: true },
    ])
    const result = await extractDroppedFiles(dt)
    expect(result.files).toHaveLength(0)
    expect(result.hadFolders).toBe(true)
  })

  it('mixed files and folders: files returned, hadFolders=true', async () => {
    const file = makeFile('doc.pdf')
    const dt = makeDataTransferWithItems([
      { kind: 'file', file, isDirectory: false },
      { kind: 'file', isDirectory: true },
    ])
    const result = await extractDroppedFiles(dt)
    expect(result.files).toHaveLength(1)
    expect(result.files[0].name).toBe('doc.pdf')
    expect(result.hadFolders).toBe(true)
  })

  it('non-file items (kind !== file) are ignored', async () => {
    const dt = makeDataTransferWithItems([
      { kind: 'string' },
    ])
    const result = await extractDroppedFiles(dt)
    expect(result.files).toHaveLength(0)
    expect(result.hadFolders).toBe(false)
  })
})
