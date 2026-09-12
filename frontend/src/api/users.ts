import { api, apiUpload, BASE_URL, type PaginatedResponse } from './index'
import type { UserMe } from './auth'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json
//
// Gen-схема UserPublic отдаёт role/lang/auth_source/current_status/gender как
// string (backend не аннотирован Literal), а часть nullable-полей — опциональной
// (поля с default в response-модели). Ниже — сужение к фактическим значениям
// и восстановление обязательности: consumers (auth-сторе, UserAvatar) полагаются
// на union-типы; new-поля из схемы при этом подхватываются автоматически.

/**
 * Категория статуса присутствия — синхронизирована с CHECK
 * ck_users_current_status (миграция 093) и ABSENCE_CATEGORY_VALUES в backend.
 * Источник — только ERP (erp_absences); ручной выбор убран.
 */
// нет в OpenAPI — union синхронизирован с backend вручную
export type UserStatusCategory = 'working' | 'vacation' | 'sick' | 'business_trip'

export type UserPublic = Omit<
  components['schemas']['UserPublic'],
  | 'role' | 'lang' | 'auth_source' | 'current_status' | 'current_status_until'
  | 'gender' | 'attributes' | 'birth_date' | 'last_login_at'
  | 'avatar_focal_x' | 'avatar_focal_y' | 'avatar_focal_zoom'
> & {
  role: 'reader' | 'editor' | 'admin'
  lang: 'ru' | 'en'
  auth_source: 'local' | 'keycloak'
  current_status: UserStatusCategory
  current_status_until: string | null
  gender: 'male' | 'female' | null
  attributes?: Record<string, string | string[]>
  birth_date: string | null
  last_login_at: string | null
  avatar_focal_x: number | null
  avatar_focal_y: number | null
  avatar_focal_zoom: number | null
}

export type PatchProfileDto = Omit<components['schemas']['PatchProfileRequest'], 'lang'> & {
  lang?: 'ru' | 'en' | null
}

export type PatchPreferencesDto = components['schemas']['PatchPreferencesRequest']

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

export async function deleteAvatar(): Promise<UserMe> {
  return api<UserMe>('/users/me/avatar', { method: 'DELETE' })
}

export async function adminUploadUserAvatar(userId: string, file: File): Promise<UserPublic> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<UserPublic>(`/users/admin/${userId}/avatar`, form)
}

export async function adminDeleteUserAvatar(userId: string): Promise<UserPublic> {
  return api<UserPublic>(`/users/admin/${userId}/avatar`, { method: 'DELETE' })
}

export async function changeUserRole(userId: string, role: string): Promise<UserPublic> {
  return api<UserPublic>(`/users/admin/${userId}/role`, { method: 'PATCH', body: { role } })
}

export async function syncUsersFromKeycloak(): Promise<{ job_id: string | null; status: string }> {
  return api('/users/admin/sync', { method: 'POST' })
}

export type AdminCreateLocalUserDto = Omit<components['schemas']['LocalUserCreateRequest'], 'role'> & {
  role: 'reader' | 'editor' | 'admin'
}

export async function adminCreateLocalUser(dto: AdminCreateLocalUserDto): Promise<UserPublic> {
  return api<UserPublic>('/users/admin/local', { method: 'POST', body: dto })
}

// Фокал аватара в AdminPatchProfileRequest — доступен для любых auth_source
// (настройка портала); gen-схема шире ручной: включает birth_date/gender.
export type AdminPatchProfileDto = components['schemas']['AdminPatchProfileRequest']

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

export type StaffOrderState = components['schemas']['StaffOrderState']

export type StaffOrderUpdate = components['schemas']['StaffOrderUpdate']

export async function fetchStaffOrder(): Promise<StaffOrderState> {
  return api<StaffOrderState>('/users/admin/staff-order')
}

export async function saveStaffOrder(body: StaffOrderUpdate): Promise<StaffOrderState> {
  return api<StaffOrderState>('/users/admin/staff-order', { method: 'PUT', body })
}

// Виджет «Дни рождения на неделе» на главной. GET /users/birthdays.
// current_status/avatar_url/current_status_until сужены к ручному контракту
// (gen: string и optional-поля) — виджет передаёт их в UserAvatar с union-типом.
export type Birthday = Omit<
  components['schemas']['BirthdayOut'],
  'current_status' | 'current_status_until' | 'avatar_url'
> & {
  current_status: UserStatusCategory
  current_status_until: string | null
  avatar_url: string | null
}

export type BirthdayListResponse = Omit<components['schemas']['BirthdayList'], 'items'> & {
  items: Birthday[]
}

export async function fetchBirthdays(): Promise<BirthdayListResponse> {
  return api<BirthdayListResponse>('/users/birthdays')
}

// ── Отсутствия сотрудника (ERP-sync: отпуска/отгулы/болезни/командировки) ────

/** Canonical kind отсутствия — синхронизирован с ABSENCE_KIND_VALUES в backend. */
// нет в OpenAPI — union синхронизирован с backend вручную
export type UserAbsenceKind =
  | 'vacation_main'
  | 'vacation_extra'
  | 'unpaid_leave'
  | 'sick'
  | 'business_trip'
  | 'day_off_paid'
  | 'day_off_unpaid'

// GET /users/{id}/absences возвращает ErpAbsenceList; kind сужен к union,
// position/department восстановлены как обязательные nullable (ген-схема
// помечает их optional).
export type UserAbsence = Omit<
  components['schemas']['ErpAbsenceOut'],
  'kind' | 'position' | 'department'
> & {
  kind: UserAbsenceKind
  position: string | null
  department: string | null
}

export type UserAbsenceListResponse = Omit<components['schemas']['ErpAbsenceList'], 'items'> & {
  items: UserAbsence[]
}

export async function fetchUserAbsences(userId: string): Promise<UserAbsenceListResponse> {
  return api<UserAbsenceListResponse>(`/users/${userId}/absences`)
}

/** Персональные уведомления в корпоративный чат (Matrix) — opt-in, дефолт выключен. */
export type AdminNotificationPreferences = components['schemas']['UserNotificationPreferencesOut']

export function fetchAdminNotificationPreferences(userId: string): Promise<AdminNotificationPreferences> {
  return api<AdminNotificationPreferences>(`/users/admin/${userId}/notification-preferences`)
}

export function patchAdminNotificationPreferences(
  userId: string,
  dto: Partial<AdminNotificationPreferences>,
): Promise<AdminNotificationPreferences> {
  return api<AdminNotificationPreferences>(`/users/admin/${userId}/notification-preferences`, {
    method: 'PATCH',
    body: dto,
  })
}
