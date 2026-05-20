import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
}))

import {
  fetchRooms,
  fetchRoom,
  createRoom,
  updateRoom,
  deleteRoom,
  fetchBookings,
  fetchMyBookings,
  fetchBooking,
  createBooking,
  updateBooking,
  deleteBooking,
  getSeriesCount,
  updateSeries,
  deleteSeries,
  searchParticipants,
} from '../../src/api/meetings'

describe('meetings API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({})
  })

  describe('rooms', () => {
    it('fetchRooms() — no include_inactive by default', async () => {
      await fetchRooms()
      expect(apiMock).toHaveBeenCalledWith('/meetings/rooms', { params: undefined })
    })

    it('fetchRooms(true) — passes include_inactive=true', async () => {
      await fetchRooms(true)
      expect(apiMock).toHaveBeenCalledWith('/meetings/rooms', {
        params: { include_inactive: 'true' },
      })
    })

    it('fetchRoom builds URL', async () => {
      await fetchRoom('rid')
      expect(apiMock).toHaveBeenCalledWith('/meetings/rooms/rid')
    })

    it('createRoom POSTs', async () => {
      await createRoom({ name: 'X' })
      expect(apiMock).toHaveBeenCalledWith('/meetings/rooms', {
        method: 'POST',
        body: { name: 'X' },
      })
    })

    it('updateRoom PUTs', async () => {
      await updateRoom('rid', { name: 'Y' })
      expect(apiMock).toHaveBeenCalledWith('/meetings/rooms/rid', {
        method: 'PUT',
        body: { name: 'Y' },
      })
    })

    it('deleteRoom DELETEs', async () => {
      await deleteRoom('rid')
      expect(apiMock).toHaveBeenCalledWith('/meetings/rooms/rid', { method: 'DELETE' })
    })
  })

  describe('bookings', () => {
    it('fetchBookings with no params still passes empty obj', async () => {
      await fetchBookings()
      expect(apiMock).toHaveBeenCalledWith('/meetings/bookings', { params: {} })
    })

    it('fetchBookings forwards filter params', async () => {
      await fetchBookings({ date: '2030-01-15', room_id: 'r1', limit: 100, offset: 5 })
      expect(apiMock).toHaveBeenCalledWith('/meetings/bookings', {
        params: { date: '2030-01-15', room_id: 'r1', limit: 100, offset: 5 },
      })
    })

    it('fetchMyBookings forwards params', async () => {
      await fetchMyBookings({ start_date: '2030-01-15', limit: 5 })
      expect(apiMock).toHaveBeenCalledWith('/meetings/bookings/my', {
        params: { start_date: '2030-01-15', limit: 5 },
      })
    })

    it('fetchBooking', async () => {
      await fetchBooking('bid')
      expect(apiMock).toHaveBeenCalledWith('/meetings/bookings/bid')
    })

    it('createBooking POSTs', async () => {
      await createBooking({
        title: 'T',
        start_time: 's',
        end_time: 'e',
        room_ids: ['r'],
      })
      expect(apiMock).toHaveBeenCalledWith('/meetings/bookings', {
        method: 'POST',
        body: { title: 'T', start_time: 's', end_time: 'e', room_ids: ['r'] },
      })
    })

    it('updateBooking PUTs', async () => {
      await updateBooking('bid', { title: 'N', apply_to: 'this' })
      expect(apiMock).toHaveBeenCalledWith('/meetings/bookings/bid', {
        method: 'PUT',
        body: { title: 'N', apply_to: 'this' },
      })
    })

    it('deleteBooking DELETEs with body', async () => {
      await deleteBooking('bid', { apply_to: 'series' })
      expect(apiMock).toHaveBeenCalledWith('/meetings/bookings/bid', {
        method: 'DELETE',
        body: { apply_to: 'series' },
      })
    })

    it('deleteBooking defaults to empty body', async () => {
      await deleteBooking('bid')
      expect(apiMock).toHaveBeenCalledWith('/meetings/bookings/bid', {
        method: 'DELETE',
        body: {},
      })
    })
  })

  describe('series', () => {
    it('getSeriesCount', async () => {
      await getSeriesCount('sid')
      expect(apiMock).toHaveBeenCalledWith('/meetings/series/sid/count')
    })

    it('updateSeries PUTs', async () => {
      await updateSeries('sid', { title: 'N' })
      expect(apiMock).toHaveBeenCalledWith('/meetings/series/sid', {
        method: 'PUT',
        body: { title: 'N' },
      })
    })

    it('deleteSeries DELETEs', async () => {
      await deleteSeries('sid')
      expect(apiMock).toHaveBeenCalledWith('/meetings/series/sid', { method: 'DELETE' })
    })
  })

  describe('participants', () => {
    it('searchParticipants forwards q', async () => {
      await searchParticipants('ali')
      expect(apiMock).toHaveBeenCalledWith('/meetings/participants/search', {
        params: { q: 'ali' },
      })
    })
  })

  it('propagates errors from api()', async () => {
    apiMock.mockRejectedValueOnce(new Error('boom'))
    await expect(fetchRooms()).rejects.toThrow('boom')
  })
})
