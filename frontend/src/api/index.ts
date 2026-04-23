import { ofetch } from 'ofetch'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

const CSRF_COOKIE = 'XSRF-TOKEN'
const CSRF_HEADER = 'X-XSRF-TOKEN'
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function readCookie(name: string): string | null {
  const prefix = name + '='
  for (const part of document.cookie.split(';')) {
    const c = part.trim()
    if (c.startsWith(prefix)) return decodeURIComponent(c.slice(prefix.length))
  }
  return null
}

export const api = ofetch.create({
  baseURL: BASE_URL,
  credentials: 'include',
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
  onResponseError({ response }) {
    if (response.status === 401) {
      const path = window.location.pathname
      if (path !== '/login' && !path.startsWith('/auth/')) {
        window.location.href = '/login?redirect=' + encodeURIComponent(path)
      }
    }
  },
})

/**
 * Upload helper for multipart/form-data: same auth/CSRF semantics as `api`,
 * but lets the browser pick the correct ``Content-Type`` boundary header.
 */
export async function apiUpload<T = unknown>(path: string, form: FormData, method: 'POST' | 'PUT' = 'POST'): Promise<T> {
  return api<T>(path, {
    method,
    body: form,
    headers: {},
  })
}

export type PaginatedResponse<T> = {
  items: T[]
  total: number
}
