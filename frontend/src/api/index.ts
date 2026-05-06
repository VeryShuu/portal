import { ofetch, type FetchOptions } from 'ofetch'

export const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

const CSRF_COOKIE = 'XSRF-TOKEN'
const CSRF_HEADER = 'X-XSRF-TOKEN'
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
const REFRESH_PATH = '/auth/refresh'

function readCookie(name: string): string | null {
  const prefix = name + '='
  for (const part of document.cookie.split(';')) {
    const c = part.trim()
    if (c.startsWith(prefix)) return decodeURIComponent(c.slice(prefix.length))
  }
  return null
}

let _redirectingOnExpiry = false

function _handle401(): void {
  if (_redirectingOnExpiry) return
  const pathname = window.location.pathname
  // Не редиректим: SPA-страницы аутентификации, публичные share-ссылки.
  if (pathname.startsWith('/auth/') || pathname.startsWith('/p/')) return
  _redirectingOnExpiry = true
  window.dispatchEvent(new CustomEvent('auth:expired'))
  const redirectTarget = pathname + window.location.search + window.location.hash
  window.location.href = '/api/v1/auth/login?redirect=' + encodeURIComponent(redirectTarget)
}

const _rawApi = ofetch.create({
  baseURL: BASE_URL,
  credentials: 'include',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
  onRequest({ options }) {
    const method = (options.method ?? 'GET').toUpperCase()
    if (UNSAFE_METHODS.has(method)) {
      const token = readCookie(CSRF_COOKIE)
      if (token) {
        const headers = new Headers(options.headers as HeadersInit | undefined)
        headers.set(CSRF_HEADER, token)
        options.headers = headers
      }
    }
  },
})

let _refreshPromise: Promise<boolean> | null = null

/**
 * Silently refresh the Keycloak access token via /auth/refresh.
 * Concurrent callers share a single in-flight request (singleton promise),
 * so a burst of parallel 401s triggers only one refresh.
 */
export function refreshAuth(): Promise<boolean> {
  if (_refreshPromise) return _refreshPromise
  _refreshPromise = (async () => {
    try {
      await _rawApi(REFRESH_PATH, { method: 'POST' })
      return true
    } catch {
      return false
    } finally {
      // Release the singleton on next tick so close-followup callers
      // still piggy-back on this attempt.
      setTimeout(() => {
        _refreshPromise = null
      }, 0)
    }
  })()
  return _refreshPromise
}

function _isRefreshPath(path: unknown): boolean {
  return typeof path === 'string' && path.endsWith(REFRESH_PATH)
}

function _statusOf(err: unknown): number | undefined {
  const e = err as { response?: { status?: number }; status?: number; statusCode?: number }
  return e?.response?.status ?? e?.status ?? e?.statusCode
}

/**
 * Public API client. On 401 it transparently attempts one silent refresh
 * and retries the original request. If refresh fails, falls back to the
 * legacy redirect-to-login behaviour.
 */
export async function api<T = unknown>(
  path: string,
  options: FetchOptions = {},
): Promise<T> {
  try {
    return (await _rawApi<T>(path, options as FetchOptions<'json'>)) as T
  } catch (err) {
    if (_statusOf(err) !== 401 || _isRefreshPath(path)) {
      throw err
    }
    const ok = await refreshAuth()
    if (!ok) {
      _handle401()
      throw err
    }
    try {
      return (await _rawApi<T>(path, options as FetchOptions<'json'>)) as T
    } catch (err2) {
      if (_statusOf(err2) === 401) {
        _handle401()
      }
      throw err2
    }
  }
}

/**
 * Upload helper for multipart/form-data: same auth/CSRF semantics as `api`,
 * but lets the browser pick the correct ``Content-Type`` boundary header.
 */
export async function apiUpload<T = unknown>(
  path: string,
  form: FormData,
  method: 'POST' | 'PUT' = 'POST',
  signal?: AbortSignal,
): Promise<T> {
  const doRequest = (): Promise<T> => {
    const headers = new Headers()
    const token = readCookie(CSRF_COOKIE)
    if (token) headers.set(CSRF_HEADER, token)
    return ofetch<T>(path, {
      baseURL: BASE_URL,
      credentials: 'include',
      method,
      body: form,
      headers,
      signal,
    })
  }
  try {
    return await doRequest()
  } catch (err) {
    if (_statusOf(err) !== 401) throw err
    const ok = await refreshAuth()
    if (!ok) {
      _handle401()
      throw err
    }
    try {
      return await doRequest()
    } catch (err2) {
      if (_statusOf(err2) === 401) _handle401()
      throw err2
    }
  }
}

export type PaginatedResponse<T> = {
  items: T[]
  total: number
}
