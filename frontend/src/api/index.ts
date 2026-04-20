import { ofetch, type FetchOptions } from 'ofetch'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

export const api = ofetch.create({
  baseURL: BASE_URL,
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
  },
  onResponseError({ response }) {
    if (response.status === 401) {
      window.location.href = '/api/v1/auth/login?redirect=' + encodeURIComponent(window.location.pathname)
    }
  },
})

export type PaginatedResponse<T> = {
  items: T[]
  total: number
}
