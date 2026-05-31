/* eslint-disable vue/one-component-per-file -- тестовые компоненты-заглушки объявляются в одном файле */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, defineComponent, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import type { BookingOut } from '../../src/api/meetings'

const i18n = createI18n({ legacy: false, locale: 'ru', messages: { ru: {}, en: {} } })

const mockDialogWarning = vi.fn()
const mockMessageError = vi.fn()
const mockMessageSuccess = vi.fn()

vi.mock('naive-ui', () => ({
  useDialog: () => ({ warning: mockDialogWarning }),
  useMessage: () => ({ error: mockMessageError, success: mockMessageSuccess, warning: vi.fn() }),
}))

const mockInvalidateQueries = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: vi.fn(() => ({ invalidateQueries: mockInvalidateQueries })),
}))

vi.mock('../../src/stores/modules', () => ({
  useModulesStore: vi.fn(() => ({
    isEnabled: (_m: string) => true,
    meetingsSettings: { calendar_start_hour: 8, calendar_end_hour: 20 },
    load: vi.fn(),
  })),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({ user: { id: 'user-1' }, isAdmin: false })),
}))

const mockDoDeleteBooking = vi.fn()
const mockDoDeleteSeries = vi.fn()

vi.mock('../../src/queries/meetings', () => ({
  useMeetingRoomsQuery: vi.fn(() => ({ data: ref([{ id: 'r1', name: 'Room A' }]), isLoading: ref(false) })),
  useMeetingBookingsQuery: vi.fn(() => ({ data: ref([]), isLoading: ref(false) })),
  useDeleteBookingMutation: vi.fn(() => ({ mutateAsync: mockDoDeleteBooking })),
  useDeleteSeriesMutation: vi.fn(() => ({ mutateAsync: mockDoDeleteSeries })),
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

const MeetingsFiltersStub = defineComponent({
  name: 'MeetingsFilters',
  props: {
    formattedDate: { type: String, default: '' },
    formattedDow: { type: String, default: '' },
  },
  emits: ['prev', 'next', 'today'],
  template: '<div class="meetings-filters-stub" />',
})

const MeetingsCalendarStub = defineComponent({
  name: 'MeetingsCalendar',
  props: {
    rooms: { type: Array, default: () => [] },
    bookings: { type: Array, default: () => [] },
    date: { type: String, default: '' },
    startHour: { type: Number, default: 8 },
    endHour: { type: Number, default: 20 },
    isLoading: { type: Boolean, default: false },
  },
  emits: ['slot-click', 'booking-click'],
  template: '<div class="meetings-calendar-stub" />',
})

const MeetingFormDialogStub = defineComponent({
  name: 'MeetingFormDialog',
  props: {
    show: { type: Boolean, default: false },
    booking: { type: Object, default: null },
    prefillRoomIds: { type: Array, default: () => [] },
    prefillStart: { type: String, default: undefined },
    prefillEnd: { type: String, default: undefined },
  },
  emits: ['update:show', 'saved'],
  template: '<div class="meeting-form-dialog-stub" />',
})

const MeetingsListStub = defineComponent({
  name: 'MeetingsList',
  props: {
    show: { type: Boolean, default: false },
    booking: { type: Object, default: null },
    canEdit: { type: Boolean, default: false },
  },
  emits: ['update:show', 'edit', 'confirm-delete'],
  template: '<div class="meetings-list-stub" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    MeetingsFilters: MeetingsFiltersStub,
    MeetingsCalendar: MeetingsCalendarStub,
    MeetingFormDialog: MeetingFormDialogStub,
    MeetingsList: MeetingsListStub,
  },
}

function makeBooking(overrides: Partial<BookingOut> = {}): BookingOut {
  return {
    id: 'b1',
    title: 'Test Meeting',
    description: '',
    rooms: [{ id: 'r1', name: 'Room A' }],
    invited_users: [],
    start_time: '2024-06-15T10:00:00Z',
    end_time: '2024-06-15T11:00:00Z',
    creator_id: 'user-1',
    series_id: null,
    ...overrides,
  } as BookingOut
}

let currentWrapper: ReturnType<typeof mount> | null = null

describe('MeetingsPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockDialogWarning.mockClear()
    mockMessageError.mockClear()
    mockMessageSuccess.mockClear()
    mockInvalidateQueries.mockClear()
    mockDoDeleteBooking.mockResolvedValue(undefined)
    mockDoDeleteSeries.mockResolvedValue(undefined)
  })

  afterEach(() => {
    if (currentWrapper) {
      currentWrapper.unmount()
      currentWrapper = null
    }
  })

  it('nextDay and prevDay change currentDate by one day', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper

    const calendar = wrapper.findComponent(MeetingsCalendarStub)
    const dateBefore = calendar.props('date') as string

    const filters = wrapper.findComponent(MeetingsFiltersStub)
    await filters.vm.$emit('next')
    await nextTick()

    const dateAfterNext = wrapper.findComponent(MeetingsCalendarStub).props('date') as string
    const expectedNext = new Date(dateBefore)
    expectedNext.setDate(expectedNext.getDate() + 1)
    expect(dateAfterNext).toBe(expectedNext.toISOString().slice(0, 10))

    await filters.vm.$emit('prev')
    await nextTick()

    const dateAfterPrev = wrapper.findComponent(MeetingsCalendarStub).props('date') as string
    expect(dateAfterPrev).toBe(dateBefore)
  })

  it('today() resets currentDate to today', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper
    const filters = wrapper.findComponent(MeetingsFiltersStub)

    await filters.vm.$emit('next')
    await nextTick()

    await filters.vm.$emit('today')
    await nextTick()

    const todayStr = new Date().toISOString().slice(0, 10)
    expect(wrapper.findComponent(MeetingsCalendarStub).props('date')).toBe(todayStr)
  })

  it('formattedDate and formattedDow are non-empty strings passed to MeetingsFilters', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper

    const filters = wrapper.findComponent(MeetingsFiltersStub)
    expect(typeof filters.props('formattedDate')).toBe('string')
    expect((filters.props('formattedDate') as string).length).toBeGreaterThan(0)
    expect(typeof filters.props('formattedDow')).toBe('string')
    expect((filters.props('formattedDow') as string).length).toBeGreaterThan(0)
  })

  it('onSlotClick opens dialog with prefillRoomIds, prefillStart, prefillEnd', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper

    const calendar = wrapper.findComponent(MeetingsCalendarStub)
    await calendar.vm.$emit('slot-click', { roomId: 'r1', start: '10:00', end: '11:00' })
    await nextTick()

    const dialog = wrapper.findComponent(MeetingFormDialogStub)
    expect(dialog.props('show')).toBe(true)
    expect(dialog.props('prefillRoomIds')).toEqual(['r1'])
    expect(dialog.props('prefillStart')).toBe('10:00')
    expect(dialog.props('prefillEnd')).toBe('11:00')
    expect(dialog.props('booking')).toBeNull()
  })

  it('onBookingClick sets selectedBooking and opens MeetingsList', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper
    const booking = makeBooking()

    const calendar = wrapper.findComponent(MeetingsCalendarStub)
    await calendar.vm.$emit('booking-click', booking)
    await nextTick()

    const list = wrapper.findComponent(MeetingsListStub)
    expect(list.props('show')).toBe(true)
    expect((list.props('booking') as BookingOut).id).toBe('b1')
    expect(wrapper.findComponent(MeetingFormDialogStub).props('show')).toBe(false)
  })

  it('openEditDialog closes MeetingsList and opens MeetingFormDialog', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper

    const calendar = wrapper.findComponent(MeetingsCalendarStub)
    await calendar.vm.$emit('booking-click', makeBooking())
    await nextTick()

    const list = wrapper.findComponent(MeetingsListStub)
    await list.vm.$emit('edit')
    await nextTick()

    expect(list.props('show')).toBe(false)
    expect(wrapper.findComponent(MeetingFormDialogStub).props('show')).toBe(true)
  })

  it('confirmDeleteBooking without series_id calls dialog.warning and deleteBookingMutation on positive', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper

    await wrapper.findComponent(MeetingsCalendarStub).vm.$emit('booking-click', makeBooking({ series_id: null }))
    await nextTick()

    await wrapper.findComponent(MeetingsListStub).vm.$emit('confirm-delete')
    await nextTick()

    expect(mockDialogWarning).toHaveBeenCalledTimes(1)
    const opts = mockDialogWarning.mock.calls[0][0]
    expect(opts.negativeText).toBeDefined()

    await opts.onPositiveClick()
    await flushPromises()

    expect(mockDoDeleteBooking).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'b1', dto: { apply_to: 'this' } }),
    )
  })

  it('confirmDeleteBooking with series_id: positive → deleteSeriesMutation, negative → deleteBookingMutation', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper

    await wrapper.findComponent(MeetingsCalendarStub).vm.$emit(
      'booking-click',
      makeBooking({ series_id: 'series-1' }),
    )
    await nextTick()

    await wrapper.findComponent(MeetingsListStub).vm.$emit('confirm-delete')
    await nextTick()

    expect(mockDialogWarning).toHaveBeenCalledTimes(1)
    const opts = mockDialogWarning.mock.calls[0][0]

    await opts.onPositiveClick()
    await flushPromises()
    expect(mockDoDeleteSeries).toHaveBeenCalledWith('series-1')

    mockDoDeleteBooking.mockClear()
    mockDoDeleteSeries.mockClear()
    mockDialogWarning.mockClear()

    await wrapper.findComponent(MeetingsCalendarStub).vm.$emit(
      'booking-click',
      makeBooking({ series_id: 'series-1' }),
    )
    await nextTick()
    await wrapper.findComponent(MeetingsListStub).vm.$emit('confirm-delete')
    await nextTick()

    const opts2 = mockDialogWarning.mock.calls[0][0]
    await opts2.onNegativeClick()
    await flushPromises()
    expect(mockDoDeleteBooking).toHaveBeenCalledWith(
      expect.objectContaining({ dto: { apply_to: 'this' } }),
    )
  })

  it('shows message.error with errors.forbidden on 403 delete error', async () => {
    mockDoDeleteBooking.mockRejectedValue({ status: 403 })

    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper

    await wrapper.findComponent(MeetingsCalendarStub).vm.$emit('booking-click', makeBooking())
    await nextTick()
    await wrapper.findComponent(MeetingsListStub).vm.$emit('confirm-delete')
    await nextTick()

    const opts = mockDialogWarning.mock.calls[0][0]
    await opts.onPositiveClick()
    await flushPromises()

    expect(mockMessageError).toHaveBeenCalledWith('errors.forbidden')
  })

  it('onSaved invalidates bookings and myBookings queries', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper

    await wrapper.findComponent(MeetingFormDialogStub).vm.$emit('saved')
    await nextTick()

    expect(mockInvalidateQueries).toHaveBeenCalledTimes(2)
  })

  it('meetings:changed event invalidates queries and listener removed on unmount', async () => {
    const MeetingsPage = (await import('../../src/pages/meetings/MeetingsPage.vue')).default
    currentWrapper = mount(MeetingsPage, { global: globalOptions })
    const wrapper = currentWrapper

    window.dispatchEvent(new Event('meetings:changed'))
    await nextTick()

    expect(mockInvalidateQueries).toHaveBeenCalledTimes(2)

    mockInvalidateQueries.mockClear()
    wrapper.unmount()

    window.dispatchEvent(new Event('meetings:changed'))
    await nextTick()

    expect(mockInvalidateQueries).not.toHaveBeenCalled()
  })
})
