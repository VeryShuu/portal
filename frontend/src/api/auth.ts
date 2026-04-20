import { api } from './index'

export interface UserMe {
  id: string
  email: string
  full_name: string
  department: string | null
  position: string | null
  phone: string | null
  role: 'reader' | 'editor' | 'admin'
  avatar_url: string | null
  presence_status: 'office' | 'remote' | 'vacation'
  notify_email: boolean
  notify_inapp: boolean
  lang: 'ru' | 'en'
  preferences: Record<string, unknown>
}

export async function fetchMe(): Promise<UserMe> {
  return api<UserMe>('/auth/me')
}

export async function refreshSession(): Promise<void> {
  await api('/auth/refresh', { method: 'POST' })
}

export function getLoginUrl(redirectAfter = '/'): string {
  return `/api/v1/auth/login?redirect=${encodeURIComponent(redirectAfter)}`
}

export function getLogoutUrl(): string {
  return `/api/v1/auth/logout`
}
