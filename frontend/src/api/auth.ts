import { api } from './index'
import type { components } from './types.gen'
import type { UserStatusCategory } from './users'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

/**
 * Ответ /auth/me. Базовые поля — из generated-схемы; пересечением сужаем
 * enum-поля (в OpenAPI они `string`) и удерживаем required-контракт полей,
 * которые generated пометил optional (avatar_focal_*, birth_date, *_until).
 */
export type UserMe = components['schemas']['UserMe'] & {
  role: 'reader' | 'editor' | 'admin'
  lang: 'ru' | 'en'
  auth_source: 'keycloak' | 'local'
  current_status: UserStatusCategory
  gender: 'male' | 'female' | null
  // Фокальная точка + зум аватара (миграция 096): null = центр, зум 100%.
  avatar_focal_x: number | null
  avatar_focal_y: number | null
  avatar_focal_zoom: number | null
  current_status_until: string | null
  // ERP-синхронизация (миграция 087)
  birth_date: string | null
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
