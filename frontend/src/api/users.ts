import { api, apiUpload, BASE_URL, type PaginatedResponse } from './index'
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
  staff_sort_order?: number | null
  staff_hidden?: boolean
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

export async function fetchUsers(
  params?: {
    q?: string
    department?: string
    office?: string
    sort?: 'full_name' | 'department' | 'staff_custom'
    page?: number
    page_size?: number
    include_hidden?: boolean
  },
  options?: { signal?: AbortSignal },
): Promise<PaginatedResponse<UserPublic>> {
  return api<PaginatedResponse<UserPublic>>('/users', { params, signal: options?.signal })
}

export async function fetchUserDepartments(
  params?: { ordered?: boolean },
): Promise<{ items: string[] }> {
  return api<{ items: string[] }>('/users/departments', { params })
}

export async function fetchUserOffices(): Promise<{ items: string[] }> {
  return api<{ items: string[] }>('/users/offices')
}

export function buildUsersExportUrl(params?: {
  q?: string
  department?: string
  office?: string
  sort?: 'full_name' | 'department' | 'staff_custom'
  format?: 'csv' | 'xlsx'
}): string {
  const search = new URLSearchParams()
  if (params?.q) search.set('q', params.q)
  if (params?.department) search.set('department', params.department)
  if (params?.office) search.set('office', params.office)
  if (params?.sort) search.set('sort', params.sort)
  search.set('format', params?.format ?? 'csv')
  const qs = search.toString()
  const base = BASE_URL.endsWith('/') ? BASE_URL.slice(0, -1) : BASE_URL
  return `${base}/users/export${qs ? `?${qs}` : ''}`
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

export interface StaffOrderState {
  departments: string[]
  hidden_user_ids: string[]
}

export interface StaffOrderUpdate {
  departments: string[]
  users: { id: string; sort_order: number }[]
  hidden_user_ids: string[]
}

export async function fetchStaffOrder(): Promise<StaffOrderState> {
  return api<StaffOrderState>('/users/admin/staff-order')
}

export async function saveStaffOrder(body: StaffOrderUpdate): Promise<StaffOrderState> {
  return api<StaffOrderState>('/users/admin/staff-order', { method: 'PUT', body })
}
