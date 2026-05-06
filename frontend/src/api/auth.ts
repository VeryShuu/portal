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
  auth_source: 'keycloak' | 'local'
  last_login_at: string | null
}

export async function fetchMe(): Promise<UserMe> {
  return api<UserMe>('/auth/me')
}

export async function refreshSession(): Promise<void> {
  await api('/auth/refresh', { method: 'POST' })
}

export async function localLogin(email: string, password: string): Promise<void> {
  await api('/auth/local/login', {
    method: 'POST',
    body: { email, password },
  })
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await api<void>('/users/me/password', {
    method: 'PATCH',
    body: { current_password: currentPassword, new_password: newPassword },
  })
}

export function getSSOLoginUrl(redirectAfter = '/'): string {
  return `/api/v1/auth/login?redirect=${encodeURIComponent(redirectAfter)}`
}

export function getLoginUrl(redirectAfter = '/'): string {
  return `/login?redirect=${encodeURIComponent(redirectAfter)}`
}

export function getLogoutUrl(): string {
  return `/api/v1/auth/logout`
}
