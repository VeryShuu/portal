export function triggerDownload(url: string, options?: { target?: string; rel?: string }): void {
  const a = document.createElement('a')
  a.href = url
  if (options?.target) a.target = options.target
  if (options?.rel) a.rel = options.rel
  a.click()
}
