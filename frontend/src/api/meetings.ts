import { api } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type RoomKind = components['schemas']['RoomOut']['kind']
export type AbsenceCategory = components['schemas']['AbsenceInfo']['category']

export type MeetingRoom = components['schemas']['RoomOut']

/**
 * Отсутствие участника: категория + диапазон ISO-дат.
 * (4-я coarse-категория `working` сюда не попадает; для absence на дату встречи —
 * реальный диапазон, для live-поиска `start_date == end_date == current_status_until`.)
 */
export type InvitedAbsence = components['schemas']['AbsenceInfo']

/**
 * Участник встречи. Информационная подпись отсутствия (`absence`) заполняется
 * только в выдаче (booking_to_out / participants search / resolve) — на лету,
 * не персистится в JSONB. `null`/`undefined` = сотрудник работает.
 */
export type InvitedUser = components['schemas']['InvitedUser']

export type BookingOut = components['schemas']['BookingOut']
export type RecurrenceRule = components['schemas']['RecurrenceRule']

export type CreateRoomDto = components['schemas']['RoomCreate']
export type UpdateRoomDto = components['schemas']['RoomUpdate']
export type CreateBookingDto = components['schemas']['BookingCreate']
export type UpdateBookingDto = components['schemas']['BookingUpdate']
export type DeleteBookingDto = components['schemas']['BookingDelete']
export type UpdateSeriesDto = components['schemas']['SeriesUpdate']
export type SeriesCountOut = components['schemas']['SeriesCountOut']

export type ResolveAmbiguousCandidate = components['schemas']['ResolveAmbiguousCandidate']
export type ResolveAmbiguousItem = components['schemas']['ResolveAmbiguousItem']
export type ResolveParticipantsResponse = components['schemas']['ResolveParticipantsResponse']

/** Ответ `POST /meetings/participants/absences` — ключ = lower(email). */
export type ParticipantAbsences = Record<string, components['schemas']['AbsenceInfo']>

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────

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

export async function deleteBooking(id: string, dto: DeleteBookingDto = { apply_to: 'this' }): Promise<void> {
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

/**
 * Действующие отсутствия участников на дату встречи (ключ ответа — lower(email)).
 *
 * Search/resolve обогащают absence «на сегодня» (даты встречи в момент поиска
 * ещё нет); сводка и письма считают на дату встречи. Форма бронирования
 * вызывает этот метод при открытии, смене даты и изменении списка участников,
 * чтобы бейджи совпадали с финальной сводкой.
 */
export async function fetchParticipantAbsences(
  emails: string[],
  onDate: string,
): Promise<ParticipantAbsences> {
  return api<ParticipantAbsences>('/meetings/participants/absences', {
    method: 'POST',
    body: { emails, on_date: onDate },
  })
}
