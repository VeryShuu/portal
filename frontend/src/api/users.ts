import { api, type PaginatedResponse } from './index'
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
}

export interface PatchProfileDto {
  presence_status?: 'office' | 'remote' | 'vacation'
  lang?: 'ru' | 'en'
  notify_email?: boolean
  notify_inapp?: boolean
}

export interface PatchPreferencesDto {
  hidden_link_ids?: string[]
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
  return api<UserMe>('/users/me/avatar', {
    method: 'POST',
    body: form,
    headers: {},
  })
}

export async function changeUserRole(userId: string, role: string): Promise<UserPublic> {
  return api<UserPublic>(`/users/admin/${userId}/role`, { method: 'PATCH', body: { role } })
}

export async function syncUsersFromKeycloak(): Promise<{ job_id: string | null; status: string }> {
  return api('/users/admin/sync', { method: 'POST' })
}
