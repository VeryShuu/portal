import { api, apiUpload, type PaginatedResponse } from './index'
import type { UserMe } from './auth'

export interface UserPublic {
  id: string
  email: string
  full_name: string
  department: string | null
  position: string | null
  phone: string | null
  role: 'reader' | 'editor' | 'admin'
  avatar_url: string | null
  presence_status: 'office' | 'remote' | 'vacation'
  lang: 'ru' | 'en'
  created_at: string
  auth_source: 'local' | 'keycloak'
  attributes?: Record<string, string | string[]>
  last_login_at: string | null
}

export interface PatchProfileDto {
  presence_status?: 'office' | 'remote' | 'vacation'
  lang?: 'ru' | 'en'
  notify_email?: boolean
  notify_inapp?: boolean
}

export interface PatchPreferencesDto {
  hidden_link_ids?: string[]
  onboarding_completed?: boolean
}

export async function fetchUsers(params?: {
  q?: string
  department?: string
  page?: number
  page_size?: number
}): Promise<PaginatedResponse<UserPublic>> {
  return api<PaginatedResponse<UserPublic>>('/users', { params })
}

export async function fetchUserById(id: string): Promise<UserPublic> {
  return api<UserPublic>(`/users/${id}`)
}

export async function patchMyProfile(dto: PatchProfileDto): Promise<UserMe> {
  return api<UserMe>('/users/me/profile', { method: 'PATCH', body: dto })
}

export async function patchMyPreferences(dto: PatchPreferencesDto): Promise<UserMe> {
  return api<UserMe>('/users/me/preferences', { method: 'PATCH', body: dto })
}

export async function uploadAvatar(file: File): Promise<UserMe> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<UserMe>('/users/me/avatar', form)
}

export async function changeUserRole(userId: string, role: string): Promise<UserPublic> {
  return api<UserPublic>(`/users/admin/${userId}/role`, { method: 'PATCH', body: { role } })
}

export async function syncUsersFromKeycloak(): Promise<{ job_id: string | null; status: string }> {
  return api('/users/admin/sync', { method: 'POST' })
}

export interface AdminCreateLocalUserDto {
  email: string
  full_name: string
  password: string
  role: 'reader' | 'editor' | 'admin'
}

export async function adminCreateLocalUser(dto: AdminCreateLocalUserDto): Promise<UserPublic> {
  return api<UserPublic>('/users/admin/local', { method: 'POST', body: dto })
}

export interface AdminPatchProfileDto {
  full_name?: string
  department?: string | null
  position?: string | null
  phone?: string | null
}

export async function adminPatchUserProfile(userId: string, dto: AdminPatchProfileDto): Promise<UserPublic> {
  return api<UserPublic>(`/users/admin/${userId}/profile`, { method: 'PATCH', body: dto })
}

export async function adminResetUserPassword(userId: string, newPassword: string): Promise<void> {
  return api(`/users/admin/${userId}/password`, { method: 'PATCH', body: { new_password: newPassword } })
}

export async function adminDeleteUser(userId: string): Promise<void> {
  return api(`/users/admin/${userId}`, { method: 'DELETE' })
}

export async function adminFetchUserKeycloakGroups(userId: string): Promise<{ groups: string[] }> {
  return api<{ groups: string[] }>(`/users/admin/${userId}/groups`)
}
