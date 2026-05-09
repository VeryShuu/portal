export interface ExtractDroppedResult {
  files: File[]
  hadFolders: boolean
}

export async function extractDroppedFiles(dt: DataTransfer): Promise<ExtractDroppedResult> {
  const files: File[] = []
  let hadFolders = false

  if (dt.items && dt.items.length) {
    for (const item of Array.from(dt.items)) {
      if (item.kind !== 'file') continue
      const entry = (item as DataTransferItem & { webkitGetAsEntry?: () => { isDirectory: boolean } | null }).webkitGetAsEntry?.()
      if (entry && entry.isDirectory) {
        hadFolders = true
        continue
      }
      const f = item.getAsFile()
      if (f) files.push(f)
    }
  } else if (dt.files) {
    for (const f of Array.from(dt.files)) files.push(f)
  }

  return { files, hadFolders }
}
