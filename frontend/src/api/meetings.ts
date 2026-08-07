import { api } from './index'

export type RoomKind = 'physical' | 'virtual'

export interface MeetingRoom {
  id: string
  name: string
  kind: RoomKind
  email: string | null
  link: string | null
  timezone: string
  is_active: boolean
  sort_order: number
}

export type AbsenceCategory = 'vacation' | 'sick' | 'business_trip'

export interface InvitedAbsence {
  /** Категория отсутствия (4-я coarse-категория `working` сюда не попадает). */
  category: AbsenceCategory
  /** ISO-дата. Для absence на дату встречи — реальный диапазон; для live-поиска
   *  `start_date == end_date == current_status_until`. */
  start_date: string
  end_date: string
}

export interface InvitedUser {
  user_id: string
  full_name: string
  email: string
  source?: 'keycloak' | 'external'
  /** Информационная подпись отсутствия (отпуск/болезнь/командировка). Заполняется
   *  только в выдаче (booking_to_out / participants search / resolve) — на лету,
   *  не персистится в JSONB. `null`/`undefined` = сотрудник работает. */
  absence?: InvitedAbsence | null
}

export interface BookingOut {
  id: string
  title: string
  organizer_name: string
  creator_id: string | null
  description: string | null
  start_time: string
  end_time: string
  rooms: MeetingRoom[]
  invited_users: InvitedUser[]
  series_id: string | null
  recurrence_rule: string | null
  update_count: number
  created_at: string
  updated_at: string
}

export interface RecurrenceRule {
  freq: 'DAILY' | 'WEEKDAYS' | 'WEEKLY' | 'BIWEEKLY' | 'MONTHLY'
  until_date: string
}

export interface CreateRoomDto {
  name: string
  kind?: RoomKind
  email?: string | null
  link?: string | null
  timezone?: string
  sort_order?: number
}

export interface UpdateRoomDto {
  name?: string | null
  kind?: RoomKind | null
  email?: string | null
  link?: string | null
  timezone?: string | null
  sort_order?: number | null
  is_active?: boolean | null
}

export interface CreateBookingDto {
  title: string
  description?: string | null
  start_time: string
  end_time: string
  room_ids: string[]
  invited_users?: InvitedUser[]
  recurrence?: RecurrenceRule | null
}

export interface UpdateBookingDto {
  apply_to?: 'this' | 'series'
  title?: string | null
  description?: string | null
  start_time?: string | null
  end_time?: string | null
  room_ids?: string[] | null
  invited_users?: InvitedUser[] | null
}

export interface DeleteBookingDto {
  apply_to?: 'this' | 'series'
}

export interface UpdateSeriesDto {
  title?: string | null
  description?: string | null
  invited_users?: InvitedUser[] | null
}

export interface SeriesCountOut {
  count: number
}

export interface BookingListParams {
  date?: string
  start_date?: string
  end_date?: string
  room_id?: string
  creator_id?: string
  limit?: number
  offset?: number
}

export async function fetchRooms(includeInactive = false): Promise<MeetingRoom[]> {
  return api<MeetingRoom[]>('/meetings/rooms', {
    params: includeInactive ? { include_inactive: 'true' } : undefined,
  })
}

export async function fetchRoom(id: string): Promise<MeetingRoom> {
  return api<MeetingRoom>(`/meetings/rooms/${id}`)
}

export async function createRoom(dto: CreateRoomDto): Promise<MeetingRoom> {
  return api<MeetingRoom>('/meetings/rooms', { method: 'POST', body: dto })
}

export async function updateRoom(id: string, dto: UpdateRoomDto): Promise<MeetingRoom> {
  return api<MeetingRoom>(`/meetings/rooms/${id}`, { method: 'PUT', body: dto })
}

export async function deleteRoom(id: string): Promise<void> {
  await api(`/meetings/rooms/${id}`, { method: 'DELETE' })
}

export async function fetchBookings(params: BookingListParams = {}): Promise<BookingOut[]> {
  return api<BookingOut[]>('/meetings/bookings', { params: params as Record<string, unknown> })
}

export async function fetchMyBookings(params: {
  start_date?: string
  limit?: number
} = {}): Promise<BookingOut[]> {
  return api<BookingOut[]>('/meetings/bookings/my', { params: params as Record<string, unknown> })
}

export async function fetchBooking(id: string): Promise<BookingOut> {
  return api<BookingOut>(`/meetings/bookings/${id}`)
}

export async function createBooking(dto: CreateBookingDto): Promise<BookingOut> {
  return api<BookingOut>('/meetings/bookings', { method: 'POST', body: dto })
}

export async function updateBooking(id: string, dto: UpdateBookingDto): Promise<BookingOut> {
  return api<BookingOut>(`/meetings/bookings/${id}`, { method: 'PUT', body: dto })
}

export async function deleteBooking(id: string, dto: DeleteBookingDto = {}): Promise<void> {
  await api(`/meetings/bookings/${id}`, { method: 'DELETE', body: dto })
}

export async function getSeriesCount(seriesId: string): Promise<SeriesCountOut> {
  return api<SeriesCountOut>(`/meetings/series/${seriesId}/count`)
}

export async function updateSeries(seriesId: string, dto: UpdateSeriesDto): Promise<BookingOut[]> {
  return api<BookingOut[]>(`/meetings/series/${seriesId}`, { method: 'PUT', body: dto })
}

export async function deleteSeries(seriesId: string): Promise<void> {
  await api(`/meetings/series/${seriesId}`, { method: 'DELETE' })
}

export async function searchParticipants(q: string): Promise<InvitedUser[]> {
  return api<InvitedUser[]>('/meetings/participants/search', { params: { q } })
}

export interface ResolveAmbiguousCandidate {
  user_id: string
  full_name: string
  email: string
  department?: string | null
  position?: string | null
}

export interface ResolveAmbiguousItem {
  query: string
  candidates: ResolveAmbiguousCandidate[]
}

export interface ResolveParticipantsResponse {
  resolved: InvitedUser[]
  unresolved: string[]
  ambiguous: ResolveAmbiguousItem[]
}

/**
 * Массовый резолв списка ФИО/email в участников встречи.
 *
 * Элементы ``queries`` могут содержать несколько записей, разделённых
 * запятыми/переносами/табами — токенизация на бэке. Возвращает найденных
 * сотрудников + внешних участников (неразрешённые email), а также списки
 * нераспознанных и неоднозначных ФИО (для ручного выбора).
 */
export async function resolveParticipants(
  queries: string[],
): Promise<ResolveParticipantsResponse> {
  return api<ResolveParticipantsResponse>('/meetings/participants/resolve', {
    method: 'POST',
    body: { queries },
  })
}
