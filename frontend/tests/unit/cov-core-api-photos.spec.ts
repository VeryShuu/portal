import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()
const apiUploadMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: any[]) => apiMock(...args),
  apiUpload: (...args: any[]) => apiUploadMock(...args),
  BASE_URL: '/api/v1',
}))

class FakeXHR {
  static instances: FakeXHR[] = []
  upload: { onprogress?: (e: ProgressEvent) => void } = {}
  withCredentials = false
  status = 0
  responseText = ''
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null
  method = ''
  url = ''
  headers: Record<string, string> = {}
  sentBody: FormData | null = null
  aborted = false

  constructor() {
    FakeXHR.instances.push(this)
  }

  open(method: string, url: string) {
    this.method = method
    this.url = url
  }

  setRequestHeader(name: string, value: string) {
    this.headers[name] = value
  }

  send(body: FormData) {
    this.sentBody = body
  }

  abort() {
    this.aborted = true
    this.onabort?.()
  }
}

describe('src/api/photos', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    FakeXHR.instances.length = 0
    vi.stubGlobal('XMLHttpRequest', FakeXHR as any)
    ;(window as any).XMLHttpRequest = FakeXHR as any
    document.cookie = ''
  })

  it('basic wrappers call api/apiUpload with expected paths/options', async () => {
    const photos = await import('../../src/api/photos')

    await photos.fetchFolderTree()
    expect(apiMock).toHaveBeenCalledWith('/photos/folders/tree')

    await photos.fetchFolder('f1')
    expect(apiMock).toHaveBeenCalledWith('/photos/folders/f1')

    await photos.createFolder({ parent_id: null, name: 'N' })
    expect(apiMock).toHaveBeenCalledWith('/photos/folders', { method: 'POST', body: { parent_id: null, name: 'N' } })

    await photos.updateFolder('f1', { name: 'U' })
    expect(apiMock).toHaveBeenCalledWith('/photos/folders/f1', { method: 'PATCH', body: { name: 'U' } })

    await photos.deleteFolder('f1')
    expect(apiMock).toHaveBeenCalledWith('/photos/folders/f1', { method: 'DELETE' })

    await photos.fetchFolderPhotos('f1', { page: 1, per_page: 20 })
    expect(apiMock).toHaveBeenCalledWith('/photos/folders/f1/photos', { params: { page: 1, per_page: 20 } })

    await photos.fetchRecentPhotos()
    expect(apiMock).toHaveBeenCalledWith('/photos/recent', { params: { limit: 8 } })

    await photos.fetchRecentPhotos(12)
    expect(apiMock).toHaveBeenCalledWith('/photos/recent', { params: { limit: 12 } })

    const file = new File(['img'], 'a.jpg', { type: 'image/jpeg' })
    await photos.uploadPhotos('f1', [file])
    expect(apiUploadMock).toHaveBeenCalledWith('/photos/folders/f1/upload', expect.any(FormData), 'POST', undefined)

    await photos.fetchTags()
    expect(apiMock).toHaveBeenCalledWith('/photos/tags', { params: undefined })

    await photos.fetchTags('cat')
    expect(apiMock).toHaveBeenCalledWith('/photos/tags', { params: { q: 'cat' } })
  })

  it('url helpers encode inputs and toggle query strings', async () => {
    const photos = await import('../../src/api/photos')

    expect(photos.thumbUrl('p1', 200)).toBe('/api/v1/photos/thumbnail/p1/200')
    expect(photos.thumbAvifUrl('p1', 600)).toBe('/api/v1/photos/thumbnail/p1/600?format=avif')
    expect(photos.originalUrl('p1')).toBe('/api/v1/photos/original/p1')
    expect(photos.originalUrl('p1', true)).toBe('/api/v1/photos/original/p1?download=1')

    expect(photos.publicPhotoInfoUrl('tok/a b')).toBe('/api/v1/photos/public/tok%2Fa%20b/info')
    expect(photos.publicPhotoThumbUrl('tok/a b', 600)).toBe('/api/v1/photos/public/tok%2Fa%20b/thumbnail/600')
    expect(photos.publicPhotoAvifUrl('tok/a b', 1600)).toBe('/api/v1/photos/public/tok%2Fa%20b/thumbnail/1600?format=avif')
    expect(photos.publicPhotoFileUrl('tok/a b')).toBe('/api/v1/photos/public/tok%2Fa%20b/file')
    expect(photos.publicPhotoFileUrl('tok/a b', true)).toBe('/api/v1/photos/public/tok%2Fa%20b/file?download=1')

    expect(photos.zipJobDownloadUrl('j1')).toBe('/api/v1/photos/zip-jobs/j1/download')
    expect(photos.publicFolderInfoUrl('tok/a b')).toBe('/api/v1/photos/public-folder/tok%2Fa%20b/info')
    expect(photos.publicFolderPhotosUrl('tok', 2, 50)).toBe('/api/v1/photos/public-folder/tok/photos?page=2&per_page=50')
    expect(photos.publicFolderThumbUrl('tok', 'p1', 400)).toBe('/api/v1/photos/public-folder/tok/thumbnail/p1/400')
    expect(photos.publicFolderAvifUrl('tok', 'p1', 1000)).toBe('/api/v1/photos/public-folder/tok/thumbnail/p1/1000?format=avif')
  })

  it('search/revoke/create wrappers build encoded paths', async () => {
    const photos = await import('../../src/api/photos')

    await photos.searchSubjects('Иван & Co')
    expect(apiMock).toHaveBeenCalledWith('/photos/users/search?q=%D0%98%D0%B2%D0%B0%D0%BD%20%26%20Co')

    await photos.revokePermission('f1', 'g:1/a')
    expect(apiMock).toHaveBeenCalledWith('/photos/folders/f1/permissions/g%3A1%2Fa', { method: 'DELETE' })

    await photos.createShareLink('p1', null)
    expect(apiMock).toHaveBeenCalledWith('/photos/p1/share', { method: 'POST', body: { expires_in_days: null } })

    await photos.createFolderShareLink('f1', 10)
    expect(apiMock).toHaveBeenCalledWith('/photos/folders/f1/share', { method: 'POST', body: { expires_in_days: 10 } })
  })

  it('uploadPhotoXhr uploads a single file through xhr batch path', async () => {
    const photos = await import('../../src/api/photos')

    const onProgress = vi.fn()
    const p = photos.uploadPhotoXhr('f1', new File(['x'], 'x.txt'), onProgress)
    const xhr = FakeXHR.instances[0]

    expect(xhr.url).toBe('/api/v1/photos/folders/f1/upload')
    xhr.status = 200
    xhr.responseText = JSON.stringify({ uploaded: [], failed: [] })
    xhr.onload?.()

    await expect(p).resolves.toEqual({ uploaded: [], failed: [] })
  })

  it('uploadPhotosBatchXhr success path parses JSON and emits progress', async () => {
    const photos = await import('../../src/api/photos')
    document.cookie = 'XSRF-TOKEN=csrf%20token'

    const onProgress = vi.fn()
    const p = photos.uploadPhotosBatchXhr('folder-1', [new File(['x'], 'a.txt')], onProgress)
    const xhr = FakeXHR.instances[0]

    expect(xhr.method).toBe('POST')
    expect(xhr.url).toBe('/api/v1/photos/folders/folder-1/upload')
    expect(xhr.withCredentials).toBe(true)
    expect(xhr.headers['X-XSRF-TOKEN']).toBe('csrf token')

    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 } as ProgressEvent)
    expect(onProgress).toHaveBeenCalledWith(50)

    xhr.status = 200
    xhr.responseText = JSON.stringify({ uploaded: [{ name: 'a.txt' }], failed: [] })
    xhr.onload?.()

    await expect(p).resolves.toEqual({ uploaded: [{ name: 'a.txt' }], failed: [] })
  })

  it('uploadPhotosBatchXhr rejects invalid JSON, non-2xx, network and abort errors', async () => {
    const photos = await import('../../src/api/photos')

    const pInvalid = photos.uploadPhotosBatchXhr('f1', [new File(['x'], 'a.txt')], vi.fn())
    const x1 = FakeXHR.instances[0]
    x1.status = 200
    x1.responseText = 'not-json'
    x1.onload?.()
    await expect(pInvalid).rejects.toThrow('Invalid JSON response')

    const pHttp = photos.uploadPhotosBatchXhr('f1', [new File(['x'], 'a.txt')], vi.fn())
    const x2 = FakeXHR.instances[1]
    x2.status = 503
    x2.responseText = 'oops'
    x2.onload?.()
    await expect(pHttp).rejects.toMatchObject({ status: 503 })

    const pNetwork = photos.uploadPhotosBatchXhr('f1', [new File(['x'], 'a.txt')], vi.fn())
    const x3 = FakeXHR.instances[2]
    x3.onerror?.()
    await expect(pNetwork).rejects.toThrow('Network error during upload')

    const pAbort = photos.uploadPhotosBatchXhr('f1', [new File(['x'], 'a.txt')], vi.fn())
    const x4 = FakeXHR.instances[3]
    x4.onabort?.()
    await expect(pAbort).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('uploadPhotosBatchXhr handles already-aborted signal and runtime abort event', async () => {
    const photos = await import('../../src/api/photos')

    const c1 = new AbortController()
    c1.abort()
    const p1 = photos.uploadPhotosBatchXhr('f1', [new File(['x'], 'a.txt')], vi.fn(), c1.signal)
    const x1 = FakeXHR.instances[0]
    expect(x1.aborted).toBe(true)
    await expect(p1).rejects.toMatchObject({ name: 'AbortError' })

    const c2 = new AbortController()
    const p2 = photos.uploadPhotosBatchXhr('f1', [new File(['x'], 'a.txt')], vi.fn(), c2.signal)
    const x2 = FakeXHR.instances[1]
    c2.abort()
    expect(x2.aborted).toBe(true)
    await expect(p2).rejects.toMatchObject({ name: 'AbortError' })
  })
})
