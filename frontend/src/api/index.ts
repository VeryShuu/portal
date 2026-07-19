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

// Тип последней известной сессии (`keycloak` | `local`). Локальные сессии не
// проходят через Keycloak SSO: при их истечении слать пользователя на
// `/api/v1/auth/login` (Kerberos/Keycloak) бессмысленно — он должен вернуться
// на форму `/auth/local`. Стор обновляет это значение при каждой загрузке
// пользователя; на клир НЕ сбрасываем, чтобы на момент 401 знать тип сессии.
//
// Холодный старт (ADR-036 п.7): до того, как стор успеет загрузить пользователя,
// `_sessionAuthSource` инициализируется из бэкенд-управляемой cookie
// `portal_auth_method`, которую бэкенд ставит при login/callback (см.
// `_helpers._build_session_cookie_response` и `local.local_login`). Без этого
// дефолт `'keycloak'` заставил бы локального юзера уйти на SSO при истечении
// Redis-сессии на новой вкладке. Cookie — только маркер, без PII.
const LAST_AUTH_METHOD_COOKIE = 'portal_auth_method'

function _readAuthSourceFromCookie(): 'keycloak' | 'local' {
  return readCookie(LAST_AUTH_METHOD_COOKIE) === 'local' ? 'local' : 'keycloak'
}

let _sessionAuthSource: 'keycloak' | 'local' = _readAuthSourceFromCookie()

export function setSessionAuthSource(source: string | null | undefined): void {
  _sessionAuthSource = source === 'local' ? 'local' : 'keycloak'
}

// Геттер нужен стору (`redirectToSSO`, `logout`) — переменная модуля приватная.
// Не экспортируем саму переменную, чтобы случайно не мутировать её снаружи.
export function getSessionAuthSource(): 'keycloak' | 'local' {
  return _sessionAuthSource
}

// Cross-tab redirect-guard: при массовом 401 (рестарт Redis, сбой Keycloak)
// несколько вкладок не должны одновременно уходить на /auth/login. Лидером
// становится первая вкладка, застолбившая метку в localStorage; остальные в
// пределах окна только чистят локальное состояние (auth:expired) и ждут —
// после логина лидера общая cookie восстановится и их запросы пройдут.
const REDIRECT_LOCK_KEY = 'auth_redirect_at'
const REDIRECT_LOCK_WINDOW_MS = 8_000

function _claimRedirectLock(): boolean {
  if (typeof window === 'undefined' || !window.localStorage) return true
  try {
    const now = Date.now()
    const raw = window.localStorage.getItem(REDIRECT_LOCK_KEY)
    const prev = raw ? Number(raw) : 0
    if (prev && now - prev < REDIRECT_LOCK_WINDOW_MS) return false
    window.localStorage.setItem(REDIRECT_LOCK_KEY, String(now))
    return true
  } catch {
    return true
  }
}

function _handle401(): void {
  if (_redirectingOnExpiry) return
  const pathname = window.location.pathname
  // Не редиректим: SPA-страницы аутентификации, публичные share-ссылки.
  if (pathname.startsWith('/auth/') || pathname.startsWith('/p/')) return
  window.dispatchEvent(new CustomEvent('auth:expired'))
  // Только одна вкладка инициирует SSO-редирект в пределах окна. «Ждуны» НЕ
  // ставят _redirectingOnExpiry — иначе они залипнут навсегда: если «лидер»
  // упал/закрылся и cookie не восстановилась, следующий 401 (уже за окном)
  // должен позволить им самим стать лидером и уйти на логин (self-heal).
  if (!_claimRedirectLock()) return
  _redirectingOnExpiry = true
  const redirectTarget = pathname + window.location.search + window.location.hash
  // Локальная сессия → обратно на форму /auth/local (она поддерживает ?redirect=),
  // а не на Keycloak SSO, который для local-пользователя только зациклит вход.
  const loginUrl = _sessionAuthSource === 'local' ? '/auth/local' : '/api/v1/auth/login'
  window.location.href = loginUrl + '?redirect=' + encodeURIComponent(redirectTarget)
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
  const fetchOptions: FetchOptions<'json'> = { ...options, responseType: 'json' }
  try {
    return await _rawApi<T>(path, fetchOptions)
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
      return await _rawApi<T>(path, fetchOptions)
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
