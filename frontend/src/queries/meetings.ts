import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchRooms, fetchRoom, createRoom, updateRoom, deleteRoom,
  fetchBookings, fetchMyBookings, fetchBooking, createBooking, updateBooking, deleteBooking,
  updateSeries, deleteSeries, getSeriesCount,
  type BookingListParams, type CreateRoomDto, type UpdateRoomDto,
  type CreateBookingDto, type UpdateBookingDto, type DeleteBookingDto, type UpdateSeriesDto,
} from '../api/meetings'
import { queryKeys } from './keys'

export function useMeetingRoomsQuery(
  includeInactive: MaybeRefOrGetter<boolean> = false,
  options: { enabled?: MaybeRefOrGetter<boolean> } = {},
) {
  return useQuery({
    queryKey: computed(() => queryKeys.meetings.rooms({ include_inactive: toValue(includeInactive) })),
    queryFn: () => fetchRooms(toValue(includeInactive)),
    staleTime: 60_000,
    enabled: computed(() => (options.enabled === undefined ? true : !!toValue(options.enabled))),
  })
}

export function useMeetingRoomQuery(id: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.meetings.room(toValue(id))),
    queryFn: () => fetchRoom(toValue(id)),
    staleTime: 60_000,
    enabled: computed(() => !!toValue(id)),
  })
}

export function useMeetingBookingsQuery(
  params: MaybeRefOrGetter<BookingListParams> = {},
  options: { enabled?: MaybeRefOrGetter<boolean> } = {},
) {
  return useQuery({
    queryKey: computed(() => queryKeys.meetings.bookings(toValue(params) as Record<string, unknown>)),
    queryFn: () => fetchBookings(toValue(params)),
    staleTime: 30_000,
    refetchOnReconnect: true,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    enabled: computed(() => (options.enabled === undefined ? true : !!toValue(options.enabled))),
  })
}

export function useMyMeetingBookingsQuery(
  params: MaybeRefOrGetter<{ start_date?: string; limit?: number }> = {},
  options: { enabled?: MaybeRefOrGetter<boolean> } = {},
) {
  return useQuery({
    queryKey: computed(() => queryKeys.meetings.myBookings(toValue(params) as Record<string, unknown>)),
    queryFn: () => fetchMyBookings(toValue(params)),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    enabled: computed(() => (options.enabled === undefined ? true : !!toValue(options.enabled))),
  })
}

export function useMeetingBookingQuery(id: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.meetings.booking(toValue(id))),
    queryFn: () => fetchBooking(toValue(id)),
    staleTime: 30_000,
    enabled: computed(() => !!toValue(id)),
  })
}

export function useSeriesCountQuery(seriesId: MaybeRefOrGetter<string | null>) {
  return useQuery({
    queryKey: computed(() => queryKeys.meetings.seriesCount(toValue(seriesId) ?? '')),
    queryFn: () => getSeriesCount(toValue(seriesId) ?? ''),
    staleTime: 30_000,
    enabled: computed(() => !!toValue(seriesId)),
  })
}

export function useCreateRoomMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: CreateRoomDto) => createRoom(dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.meetings.all })
    },
  })
}

export function useUpdateRoomMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dto }: { id: string; dto: UpdateRoomDto }) => updateRoom(id, dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.meetings.all })
    },
  })
}

export function useDeleteRoomMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteRoom(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.meetings.all })
    },
  })
}

export function useCreateBookingMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: CreateBookingDto) => createBooking(dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.meetings.all })
    },
  })
}

export function useUpdateBookingMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dto }: { id: string; dto: UpdateBookingDto }) => updateBooking(id, dto),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.meetings.all })
      qc.invalidateQueries({ queryKey: queryKeys.meetings.booking(id) })
    },
  })
}

export function useDeleteBookingMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dto }: { id: string; dto?: DeleteBookingDto }) => deleteBooking(id, dto),
    onSuccess: (_, { id }) => {
      qc.removeQueries({ queryKey: queryKeys.meetings.booking(id) })
      qc.invalidateQueries({ queryKey: queryKeys.meetings.all })
    },
  })
}

export function useUpdateSeriesMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ seriesId, dto }: { seriesId: string; dto: UpdateSeriesDto }) =>
      updateSeries(seriesId, dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.meetings.all })
    },
  })
}

export function useDeleteSeriesMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (seriesId: string) => deleteSeries(seriesId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.meetings.all })
    },
  })
}
