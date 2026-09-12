import { isRef } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockFetchRooms = vi.fn()
const mockFetchRoom = vi.fn()
const mockCreateRoom = vi.fn()
const mockUpdateRoom = vi.fn()
const mockDeleteRoom = vi.fn()
const mockFetchBookings = vi.fn()
const mockFetchMyBookings = vi.fn()
const mockFetchBooking = vi.fn()
const mockCreateBooking = vi.fn()
const mockUpdateBooking = vi.fn()
const mockDeleteBooking = vi.fn()
const mockUpdateSeries = vi.fn()
const mockDeleteSeries = vi.fn()
const mockGetSeriesCount = vi.fn()

vi.mock('../../src/api/meetings', () => ({
  fetchRooms: mockFetchRooms,
  fetchRoom: mockFetchRoom,
  createRoom: mockCreateRoom,
  updateRoom: mockUpdateRoom,
  deleteRoom: mockDeleteRoom,
  fetchBookings: mockFetchBookings,
  fetchMyBookings: mockFetchMyBookings,
  fetchBooking: mockFetchBooking,
  createBooking: mockCreateBooking,
  updateBooking: mockUpdateBooking,
  deleteBooking: mockDeleteBooking,
  updateSeries: mockUpdateSeries,
  deleteSeries: mockDeleteSeries,
  getSeriesCount: mockGetSeriesCount,
}))

const _capturedQueries: any[] = []
const _capturedMutations: any[] = []
const mockInvalidate = vi.fn()
const mockRemove = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    _capturedQueries.push(opts)
    return { data: { value: undefined }, isLoading: { value: false } }
  }),
  useMutation: vi.fn((opts: any) => {
    _capturedMutations.push(opts)
    return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: { value: false } }
  }),
  useQueryClient: vi.fn(() => ({
    invalidateQueries: mockInvalidate,
    removeQueries: mockRemove,
  })),
}))

function resolveKey(k: unknown): unknown {
  if (isRef(k)) return resolveKey(k.value)
  return k
}

describe('src/queries/meetings', () => {
  beforeEach(() => {
    _capturedQueries.length = 0
    _capturedMutations.length = 0
    vi.clearAllMocks()
  })

  describe('queries', () => {
    it('useMeetingRoomsQuery uses meetings namespace and calls fetchRooms', async () => {
      const { useMeetingRoomsQuery } = await import('../../src/queries/meetings')
      useMeetingRoomsQuery()
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('meetings')
      expect(JSON.stringify(key)).toContain('rooms')
      mockFetchRooms.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchRooms).toHaveBeenCalledWith(false)
    })

    it('useMeetingRoomsQuery(true) forwards include_inactive flag', async () => {
      const { useMeetingRoomsQuery } = await import('../../src/queries/meetings')
      useMeetingRoomsQuery(true)
      await _capturedQueries[0].queryFn()
      expect(mockFetchRooms).toHaveBeenCalledWith(true)
    })

    it('useMeetingRoomQuery enabled only when id present', async () => {
      const { useMeetingRoomQuery } = await import('../../src/queries/meetings')
      useMeetingRoomQuery('')
      const opts = _capturedQueries[0]
      expect(resolveKey(opts.enabled)).toBe(false)
    })

    it('useMeetingRoomQuery calls fetchRoom with id', async () => {
      const { useMeetingRoomQuery } = await import('../../src/queries/meetings')
      useMeetingRoomQuery('rid')
      mockFetchRoom.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockFetchRoom).toHaveBeenCalledWith('rid')
    })

    it('useMeetingBookingsQuery forwards params', async () => {
      const { useMeetingBookingsQuery } = await import('../../src/queries/meetings')
      useMeetingBookingsQuery({ date: '2030-01-15' })
      mockFetchBookings.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchBookings).toHaveBeenCalledWith({ date: '2030-01-15' })
    })

    it('useMeetingBookingsQuery respects enabled=false option', async () => {
      const { useMeetingBookingsQuery } = await import('../../src/queries/meetings')
      useMeetingBookingsQuery({}, { enabled: false })
      expect(resolveKey(_capturedQueries[0].enabled)).toBe(false)
    })

    it('useMyMeetingBookingsQuery calls fetchMyBookings', async () => {
      const { useMyMeetingBookingsQuery } = await import('../../src/queries/meetings')
      useMyMeetingBookingsQuery({ limit: 5 })
      mockFetchMyBookings.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchMyBookings).toHaveBeenCalledWith({ limit: 5 })
    })

    it('useMeetingBookingQuery calls fetchBooking with id', async () => {
      const { useMeetingBookingQuery } = await import('../../src/queries/meetings')
      useMeetingBookingQuery('bid')
      mockFetchBooking.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockFetchBooking).toHaveBeenCalledWith('bid')
    })

    it('useSeriesCountQuery disabled when seriesId null', async () => {
      const { useSeriesCountQuery } = await import('../../src/queries/meetings')
      useSeriesCountQuery(null)
      expect(resolveKey(_capturedQueries[0].enabled)).toBe(false)
    })

    it('useSeriesCountQuery enabled when seriesId present', async () => {
      const { useSeriesCountQuery } = await import('../../src/queries/meetings')
      useSeriesCountQuery('sid')
      expect(resolveKey(_capturedQueries[0].enabled)).toBe(true)
      mockGetSeriesCount.mockResolvedValueOnce({ count: 3 })
      await _capturedQueries[0].queryFn()
      expect(mockGetSeriesCount).toHaveBeenCalledWith('sid')
    })
  })

  describe('mutations invalidate meetings cache on success', () => {
    it('useCreateRoomMutation', async () => {
      const { useCreateRoomMutation } = await import('../../src/queries/meetings')
      useCreateRoomMutation()
      mockCreateRoom.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn({ name: 'X' })
      expect(mockCreateRoom).toHaveBeenCalledWith({ name: 'X' })
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })

    it('useUpdateRoomMutation', async () => {
      const { useUpdateRoomMutation } = await import('../../src/queries/meetings')
      useUpdateRoomMutation()
      mockUpdateRoom.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn({ id: 'rid', dto: { name: 'Y' } })
      expect(mockUpdateRoom).toHaveBeenCalledWith('rid', { name: 'Y' })
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })

    it('useDeleteRoomMutation', async () => {
      const { useDeleteRoomMutation } = await import('../../src/queries/meetings')
      useDeleteRoomMutation()
      mockDeleteRoom.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn('rid')
      expect(mockDeleteRoom).toHaveBeenCalledWith('rid')
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })

    it('useCreateBookingMutation', async () => {
      const { useCreateBookingMutation } = await import('../../src/queries/meetings')
      useCreateBookingMutation()
      mockCreateBooking.mockResolvedValueOnce({})
      const dto = { title: 'T', start_time: 's', end_time: 'e', room_ids: ['r'] }
      await _capturedMutations[0].mutationFn(dto)
      expect(mockCreateBooking).toHaveBeenCalledWith(dto)
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })

    it('useUpdateBookingMutation invalidates booking detail too', async () => {
      const { useUpdateBookingMutation } = await import('../../src/queries/meetings')
      useUpdateBookingMutation()
      mockUpdateBooking.mockResolvedValueOnce({})
      await _capturedMutations[0].mutationFn({ id: 'bid', dto: { title: 'x' } })
      expect(mockUpdateBooking).toHaveBeenCalledWith('bid', { title: 'x' })
      await _capturedMutations[0].onSuccess({}, { id: 'bid' })
      expect(mockInvalidate).toHaveBeenCalledTimes(2)
    })

    it('useDeleteBookingMutation removes detail cache and invalidates list', async () => {
      const { useDeleteBookingMutation } = await import('../../src/queries/meetings')
      useDeleteBookingMutation()
      mockDeleteBooking.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn({ id: 'bid', dto: { apply_to: 'this' } })
      expect(mockDeleteBooking).toHaveBeenCalledWith('bid', { apply_to: 'this' })
      await _capturedMutations[0].onSuccess(undefined, { id: 'bid' })
      expect(mockRemove).toHaveBeenCalled()
      expect(mockInvalidate).toHaveBeenCalled()
    })

    it('useUpdateSeriesMutation', async () => {
      const { useUpdateSeriesMutation } = await import('../../src/queries/meetings')
      useUpdateSeriesMutation()
      mockUpdateSeries.mockResolvedValueOnce([])
      await _capturedMutations[0].mutationFn({ seriesId: 'sid', dto: { title: 'N' } })
      expect(mockUpdateSeries).toHaveBeenCalledWith('sid', { title: 'N' })
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })

    it('useDeleteSeriesMutation', async () => {
      const { useDeleteSeriesMutation } = await import('../../src/queries/meetings')
      useDeleteSeriesMutation()
      mockDeleteSeries.mockResolvedValueOnce(undefined)
      await _capturedMutations[0].mutationFn('sid')
      expect(mockDeleteSeries).toHaveBeenCalledWith('sid')
      await _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalled()
    })
  })
})
