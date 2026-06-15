import { beforeEach, describe, expect, it, vi } from 'vitest'

const rawApiImpl = vi.fn()
const ofetchCall = vi.fn()
const ofetchCreate = vi.fn((config: any) => {
  const client = vi.fn((path: string, options: any = {}) => {
    const nextOptions = { ...options }
    config.onRequest?.({ options: nextOptions })
    return rawApiImpl(path, nextOptions)
  })
  return client
})

vi.mock('ofetch', () => ({
  ofetch: Object.assign(ofetchCall, { create: ofetchCreate }),
}))

async function loadApiModule() {
  vi.resetModules()
  return import('../../src/api/index')
}

function setLocation(pathname: string, search = '', hash = '') {
  const orig = window.location
  delete (window as any).location
  ;(window as any).location = { pathname, search, hash, href: '' }
  return () => {
    ;(window as any).location = orig
  }
}

describe('src/api/index', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.cookie = ''
    window.localStorage.clear()
  })

  it('refreshAuth reuses one in-flight refresh promise and resets after tick', async () => {
    rawApiImpl.mockResolvedValue({ ok: true })
    const { refreshAuth } = await loadApiModule()

    const p1 = refreshAuth()
    const p2 = refreshAuth()
    expect(p1).toBe(p2)
    await expect(p1).resolves.toBe(true)
    expect(rawApiImpl).toHaveBeenCalledTimes(1)
    expect(rawApiImpl).toHaveBeenCalledWith('/auth/refresh', expect.objectContaining({ method: 'POST' }))

    await new Promise((resolve) => setTimeout(resolve, 0))
    await refreshAuth()
    expect(rawApiImpl).toHaveBeenCalledTimes(2)
  })

  it('api sends responseType=json and injects CSRF header for unsafe methods', async () => {
    rawApiImpl.mockResolvedValueOnce({ ok: 1 })
    document.cookie = 'XSRF-TOKEN=a%20b'
    const { api } = await loadApiModule()

    const res = await api('/news', { method: 'POST', headers: { 'X-Test': '1' } })
    expect(res).toEqual({ ok: 1 })

    const [, options] = rawApiImpl.mock.calls[0]
    expect(options.responseType).toBe('json')
    expect(options.headers).toBeInstanceOf(Headers)
    expect((options.headers as Headers).get('X-XSRF-TOKEN')).toBe('a b')
    expect((options.headers as Headers).get('X-Test')).toBe('1')
  })

  it('api keeps headers unchanged for safe methods', async () => {
    rawApiImpl.mockResolvedValueOnce({ ok: 1 })
    document.cookie = 'XSRF-TOKEN=token'
    const { api } = await loadApiModule()

    await api('/news', { method: 'GET', headers: { 'X-Test': '1' } })

    const [, options] = rawApiImpl.mock.calls[0]
    expect(options.headers).toEqual({ 'X-Test': '1' })
  })

  it('api throws non-401 errors without refresh', async () => {
    const err = Object.assign(new Error('boom'), { status: 500 })
    rawApiImpl.mockRejectedValueOnce(err)
    const { api } = await loadApiModule()

    await expect(api('/x')).rejects.toBe(err)
    expect(rawApiImpl).toHaveBeenCalledTimes(1)
  })

  it('api does not refresh for refresh endpoint itself', async () => {
    const err = Object.assign(new Error('unauth'), { status: 401 })
    rawApiImpl.mockRejectedValueOnce(err)
    const { api } = await loadApiModule()

    await expect(api('/auth/refresh')).rejects.toBe(err)
    expect(rawApiImpl).toHaveBeenCalledTimes(1)
  })

  it('api retries once after successful refresh', async () => {
    rawApiImpl
      .mockRejectedValueOnce(Object.assign(new Error('unauth'), { status: 401 }))
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({ result: 42 })
    const { api } = await loadApiModule()

    await expect(api('/protected')).resolves.toEqual({ result: 42 })
    expect(rawApiImpl).toHaveBeenNthCalledWith(2, '/auth/refresh', expect.objectContaining({ method: 'POST' }))
    expect(rawApiImpl).toHaveBeenNthCalledWith(3, '/protected', expect.objectContaining({ responseType: 'json' }))
  })

  it('api triggers auth-expired redirect when refresh fails', async () => {
    const restoreLocation = setLocation('/news', '?q=1', '#part')
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    const err = Object.assign(new Error('unauth'), { status: 401 })

    rawApiImpl
      .mockRejectedValueOnce(err)
      .mockRejectedValueOnce(Object.assign(new Error('refresh failed'), { status: 401 }))

    const { api } = await loadApiModule()
    await expect(api('/private')).rejects.toBe(err)

    expect(dispatchSpy).toHaveBeenCalled()
    expect((window as any).location.href).toContain('/api/v1/auth/login?redirect=')
    expect((window as any).location.href).toContain(encodeURIComponent('/news?q=1#part'))

    restoreLocation()
  })

  it('local session 401 redirects to /auth/local, not Keycloak SSO', async () => {
    const restoreLocation = setLocation('/files')
    const err = Object.assign(new Error('unauth'), { status: 401 })

    rawApiImpl
      .mockRejectedValueOnce(err)
      .mockRejectedValueOnce(Object.assign(new Error('refresh failed'), { status: 401 }))

    const { api, setSessionAuthSource } = await loadApiModule()
    setSessionAuthSource('local')
    await expect(api('/private')).rejects.toBe(err)

    expect((window as any).location.href).toContain('/auth/local?redirect=')
    expect((window as any).location.href).not.toContain('/api/v1/auth/login')
    expect((window as any).location.href).toContain(encodeURIComponent('/files'))

    restoreLocation()
  })

  it('keycloak is the default session source for the redirect target', async () => {
    const restoreLocation = setLocation('/news')
    const err = Object.assign(new Error('unauth'), { status: 401 })

    rawApiImpl
      .mockRejectedValueOnce(err)
      .mockRejectedValueOnce(Object.assign(new Error('refresh failed'), { status: 401 }))

    const { api, setSessionAuthSource } = await loadApiModule()
    // Любое не-local значение трактуется как keycloak (в т.ч. null/undefined).
    setSessionAuthSource(null)
    await expect(api('/private')).rejects.toBe(err)

    expect((window as any).location.href).toContain('/api/v1/auth/login?redirect=')

    restoreLocation()
  })

  it('api triggers auth-expired redirect when retry is still 401', async () => {
    const restoreLocation = setLocation('/kb/articles/1')
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    const retryErr = Object.assign(new Error('still unauthorized'), { status: 401 })

    rawApiImpl
      .mockRejectedValueOnce(Object.assign(new Error('unauth'), { status: 401 }))
      .mockResolvedValueOnce({ ok: true })
      .mockRejectedValueOnce(retryErr)

    const { api } = await loadApiModule()
    await expect(api('/private')).rejects.toBe(retryErr)
    expect(dispatchSpy).toHaveBeenCalled()

    restoreLocation()
  })

  it('api does not redirect on auth SPA routes', async () => {
    const restoreLocation = setLocation('/auth/local')
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')

    rawApiImpl
      .mockRejectedValueOnce(Object.assign(new Error('unauth'), { status: 401 }))
      .mockRejectedValueOnce(Object.assign(new Error('refresh failed'), { status: 401 }))

    const { api } = await loadApiModule()
    await expect(api('/private')).rejects.toBeTruthy()
    expect(dispatchSpy).not.toHaveBeenCalled()
    expect((window as any).location.href).toBe('')

    restoreLocation()
  })

  it('api does not redirect on public photo routes', async () => {
    const restoreLocation = setLocation('/p/token123')
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')

    rawApiImpl
      .mockRejectedValueOnce(Object.assign(new Error('unauth'), { status: 401 }))
      .mockRejectedValueOnce(Object.assign(new Error('refresh failed'), { status: 401 }))

    const { api } = await loadApiModule()
    await expect(api('/private')).rejects.toBeTruthy()
    expect(dispatchSpy).not.toHaveBeenCalled()

    restoreLocation()
  })

  it('apiUpload sends multipart request with credentials and csrf header', async () => {
    document.cookie = 'XSRF-TOKEN=csrf123'
    const form = new FormData()
    form.append('f', new Blob(['x']), 'x.txt')
    const signal = new AbortController().signal
    ofetchCall.mockResolvedValueOnce({ uploaded: 1 })
    const { apiUpload, BASE_URL } = await loadApiModule()

    await expect(apiUpload('/upload', form, 'PUT', signal)).resolves.toEqual({ uploaded: 1 })

    expect(ofetchCall).toHaveBeenCalledWith('/upload', expect.objectContaining({
      baseURL: BASE_URL,
      credentials: 'include',
      method: 'PUT',
      body: form,
      signal,
      headers: expect.any(Headers),
    }))
    const [, opts] = ofetchCall.mock.calls[0]
    expect((opts.headers as Headers).get('X-XSRF-TOKEN')).toBe('csrf123')
  })

  it('apiUpload retries after refresh and succeeds', async () => {
    const form = new FormData()
    const firstErr = Object.assign(new Error('unauth'), { status: 401 })
    ofetchCall.mockRejectedValueOnce(firstErr).mockResolvedValueOnce({ ok: true })
    rawApiImpl.mockResolvedValueOnce({ ok: true })
    const { apiUpload } = await loadApiModule()

    await expect(apiUpload('/upload', form)).resolves.toEqual({ ok: true })
    expect(rawApiImpl).toHaveBeenCalledWith('/auth/refresh', expect.objectContaining({ method: 'POST' }))
    expect(ofetchCall).toHaveBeenCalledTimes(2)
  })

  it('apiUpload throws non-401 without refresh', async () => {
    const form = new FormData()
    const err = Object.assign(new Error('bad'), { statusCode: 400 })
    ofetchCall.mockRejectedValueOnce(err)
    const { apiUpload } = await loadApiModule()

    await expect(apiUpload('/upload', form)).rejects.toBe(err)
    expect(rawApiImpl).not.toHaveBeenCalled()
  })

  it('apiUpload redirects when refresh fails', async () => {
    const restoreLocation = setLocation('/files')
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    const form = new FormData()
    const err = Object.assign(new Error('unauth'), { response: { status: 401 } })

    ofetchCall.mockRejectedValueOnce(err)
    rawApiImpl.mockRejectedValueOnce(Object.assign(new Error('refresh failed'), { status: 401 }))

    const { apiUpload } = await loadApiModule()
    await expect(apiUpload('/upload', form)).rejects.toBe(err)

    expect(dispatchSpy).toHaveBeenCalled()
    expect((window as any).location.href).toContain('/api/v1/auth/login?redirect=')

    restoreLocation()
  })

  it('does not redirect when another tab already claimed the SSO redirect', async () => {
    const restoreLocation = setLocation('/news')
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    // Свежая метка от вкладки-лидера в окне → текущая вкладка лишь чистит
    // локальное состояние (auth:expired), но сама не редиректит.
    window.localStorage.setItem('auth_redirect_at', String(Date.now()))

    rawApiImpl
      .mockRejectedValueOnce(Object.assign(new Error('unauth'), { status: 401 }))
      .mockRejectedValueOnce(Object.assign(new Error('refresh failed'), { status: 401 }))

    const { api } = await loadApiModule()
    await expect(api('/private')).rejects.toBeTruthy()

    expect(dispatchSpy).toHaveBeenCalled()
    expect((window as any).location.href).toBe('')

    restoreLocation()
  })

  it('follower self-heals: a later 401 past the window still redirects this tab', async () => {
    const restoreLocation = setLocation('/news')
    // 1) Лок держит другая вкладка → текущая остаётся «ждуном», не редиректит
    //    и (важно!) не залипает навсегда.
    window.localStorage.setItem('auth_redirect_at', String(Date.now()))

    rawApiImpl
      .mockRejectedValueOnce(Object.assign(new Error('unauth'), { status: 401 }))
      .mockRejectedValueOnce(Object.assign(new Error('refresh failed'), { status: 401 }))

    const { api } = await loadApiModule()
    await expect(api('/p1')).rejects.toBeTruthy()
    expect((window as any).location.href).toBe('')

    // 2) Лидер так и не восстановил cookie, окно прошло → следующий 401 даёт
    //    этой вкладке стать лидером и уйти на логин.
    window.localStorage.removeItem('auth_redirect_at')
    await new Promise((resolve) => setTimeout(resolve, 0)) // дать сброситься singleton-промису refresh

    rawApiImpl
      .mockRejectedValueOnce(Object.assign(new Error('unauth'), { status: 401 }))
      .mockRejectedValueOnce(Object.assign(new Error('refresh failed'), { status: 401 }))

    await expect(api('/p2')).rejects.toBeTruthy()
    expect((window as any).location.href).toContain('/api/v1/auth/login?redirect=')

    restoreLocation()
  })
})
