export function triggerDownload(url: string, options?: { target?: string; rel?: string }): void {
  const a = document.createElement('a')
  a.href = url
  if (options?.target) a.target = options.target
  if (options?.rel) a.rel = options.rel
  a.click()
}

/** Скачивание blob (xlsx/pdf): три модуля learning повторяли этот код вручную. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
