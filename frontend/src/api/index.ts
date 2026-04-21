import { ofetch } from 'ofetch'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

export const api = ofetch.create({
  baseURL: BASE_URL,
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
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

export type PaginatedResponse<T> = {
  items: T[]
  total: number
}
