import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const msg = { success: vi.fn(), error: vi.fn() }
const mapMeetingsError = vi.fn(() => 'UNKNOWN')

const doCreate = vi.fn()
const doUpdate = vi.fn()
const doDelete = vi.fn()
const doUpdateSeries = vi.fn()
const doDeleteSeries = vi.fn()

const modulesStore = {
  meetingsSettings: { min_search_chars: 2, max_recurrence_horizon_days: 45 },
  isEnabled: vi.fn(() => true),
}
const authStore = { user: { id: 'u1' }, isAdmin: false }

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: ref('en') }),
}))

vi.mock('naive-ui', () => ({
  dateRuRU: { name: 'ru' },
  dateEnUS: { name: 'en' },
  useMessage: () => msg,
}))

vi.mock('../../src/utils/mapMeetingsError', () => ({
  mapMeetingsError: (...args: any[]) => mapMeetingsError(...args),
}))

vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => modulesStore,
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => authStore,
}))

vi.mock('../../src/queries/meetings', () => ({
  useMeetingRoomsQuery: () => ({ data: ref([{ id: 'r1', name: 'Room' }]), isLoading: ref(false) }),
  useCreateBookingMutation: () => ({ mutateAsync: doCreate }),
  useUpdateBookingMutation: () => ({ mutateAsync: doUpdate }),
  useDeleteBookingMutation: () => ({ mutateAsync: doDelete }),
  useUpdateSeriesMutation: () => ({ mutateAsync: doUpdateSeries }),
  useDeleteSeriesMutation: () => ({ mutateAsync: doDeleteSeries }),
}))

async function setupHost(props: any) {
  const emit = vi.fn()
  let api: any = null
  const mod = await import('../../src/components/meetings/meeting-form/composables/useMeetingFormState')
  const Host = defineComponent({
    setup() {
      api = mod.useMeetingFormState(props, ((e: string, v?: any) => emit(e, v)) as any)
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  await nextTick()
  return { api, emit, wrapper }
}

const booking = {
  id: 'b1',
  title: 'Weekly',
  description: 'desc',
  creator_id: 'u1',
  series_id: 's1',
  start_time: '2026-06-01T10:00:00.000Z',
  end_time: '2026-06-01T11:00:00.000Z',
  rooms: [{ id: 'r1' }],
  invited_users: [{ id: 'u2', first_name: 'A', last_name: 'B', email: 'a@b.c' }],
}

describe('cov-feat useMeetingFormState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authStore.user = { id: 'u1' }
    authStore.isAdmin = false
  })

  it('initializes create form and computes defaults', async () => {
    const { api } = await setupHost({ show: true, booking: null, prefillRoomIds: ['r2'], prefillStart: '2026-01-01T09:00:00.000Z', prefillEnd: '2026-01-01T10:00:00.000Z' })
    expect(api.isEdit.value).toBe(false)
    expect(api.canDelete.value).toBe(false)
    expect(api.minSearchChars.value).toBe(2)
    expect(api.maxRecurrenceDays.value).toBe(45)
    expect(api.form.value.room_ids).toEqual(['r2'])
    expect(api.selectedDuration.value).toBe(60)
    expect(api.dateLocaleValue.value.name).toBe('en')
    expect(api.startDateStr.value).toBe('2026-01-01')
  })

  it('initializes edit form and room toggle/watchers work', async () => {
    const { api } = await setupHost({ show: true, booking })
    expect(api.isEdit.value).toBe(true)
    expect(api.canDelete.value).toBe(true)

    api.toggleRoom('r2')
    expect(api.form.value.room_ids).toContain('r2')
    api.toggleRoom('r2')
    expect(api.form.value.room_ids).not.toContain('r2')

    api.selectedDuration.value = 90
    await nextTick()
    expect(api.form.value.end_time).toBe((api.form.value.start_time as number) + 90 * 60_000)

    api.form.value.start_time = (api.form.value.start_time as number) + 60_000
    await nextTick()
    expect(api.form.value.end_time).toBe((api.form.value.start_time as number) + 90 * 60_000)
  })

  it('onSubmit exits when validate rejects', async () => {
    const { api } = await setupHost({ show: true, booking: null })
    api.formRef.value = { validate: vi.fn().mockRejectedValue(new Error('bad')) }
    await api.onSubmit()
    expect(doCreate).not.toHaveBeenCalled()
  })

  it('onSubmit create success emits and shows success message', async () => {
    const { api, emit } = await setupHost({ show: true, booking: null })
    api.formRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    api.form.value.title = 'New'
    api.form.value.room_ids = ['r1']
    api.form.value.start_time = new Date('2026-06-01T10:01:33.000Z').getTime()
    api.form.value.end_time = new Date('2026-06-01T11:04:33.000Z').getTime()
    doCreate.mockResolvedValueOnce({})

    await api.onSubmit()
    expect(doCreate).toHaveBeenCalled()
    const payload = doCreate.mock.calls[0][0]
    expect(payload.start_time).toContain(':01:00.000Z')
    expect(payload.end_time).toContain(':01:00.000Z')
    expect(msg.success).toHaveBeenCalledWith('meetings.form.savedSuccess')
    expect(emit).toHaveBeenCalledWith('update:show', false)
    expect(emit).toHaveBeenCalledWith('saved', undefined)
  })

  it('onSubmit edit path updates series or single booking', async () => {
    const { api } = await setupHost({ show: true, booking })
    api.formRef.value = { validate: vi.fn().mockResolvedValue(undefined) }

    api.form.value.apply_to = 'series'
    doUpdateSeries.mockResolvedValueOnce({})
    await api.onSubmit()
    expect(doUpdateSeries).toHaveBeenCalledWith({
      seriesId: 's1',
      dto: expect.objectContaining({ title: booking.title }),
    })

    api.form.value.apply_to = 'this'
    doUpdate.mockResolvedValueOnce({})
    await api.onSubmit()
    expect(doUpdate).toHaveBeenCalledWith(expect.objectContaining({ id: 'b1' }))
  })

  it('onSubmit maps error branches', async () => {
    const { api } = await setupHost({ show: true, booking: null })
    api.formRef.value = { validate: vi.fn().mockResolvedValue(undefined) }

    mapMeetingsError.mockReturnValueOnce('BOOKING_CONFLICT')
    doCreate.mockRejectedValueOnce({ data: { conflicts: [{ room_name: 'A' }] } })
    await api.onSubmit()
    expect(api.conflictError.value).toEqual([{ room_name: 'A' }])

    mapMeetingsError.mockReturnValueOnce('START_TIME_IN_PAST')
    doCreate.mockRejectedValueOnce(new Error('x'))
    await api.onSubmit()
    expect(msg.error).toHaveBeenCalledWith('meetings.form.startTimeInPast', { duration: 5000 })

    mapMeetingsError.mockReturnValueOnce('END_BEFORE_START')
    doCreate.mockRejectedValueOnce(new Error('x'))
    await api.onSubmit()
    expect(msg.error).toHaveBeenCalledWith('meetings.form.endTimeAfterStart', { duration: 5000 })

    mapMeetingsError.mockReturnValueOnce('OTHER')
    doCreate.mockRejectedValueOnce(new Error('x'))
    await api.onSubmit()
    expect(msg.error).toHaveBeenCalledWith('meetings.form.saveError')
  })

  it('onDelete handles guard, series/single success and error', async () => {
    const noBooking = await setupHost({ show: true, booking: null })
    await noBooking.api.onDelete()
    expect(doDelete).not.toHaveBeenCalled()

    const withBooking = await setupHost({ show: true, booking })
    withBooking.api.form.value.apply_to = 'series'
    doDeleteSeries.mockResolvedValueOnce({})
    await withBooking.api.onDelete()
    expect(doDeleteSeries).toHaveBeenCalledWith('s1')

    withBooking.api.form.value.apply_to = 'this'
    doDelete.mockResolvedValueOnce({})
    await withBooking.api.onDelete()
    expect(doDelete).toHaveBeenCalledWith({ id: 'b1', dto: { apply_to: 'this' } })

    doDelete.mockRejectedValueOnce(new Error('boom'))
    await withBooking.api.onDelete()
    expect(msg.error).toHaveBeenCalledWith('meetings.form.deleteError')
  })

  it('formats conflict time string', async () => {
    const { api } = await setupHost({ show: true, booking: null })
    const out = api.formatConflictTime('2026-06-01T09:00:00.000Z', '2026-06-01T10:30:00.000Z')
    expect(out).toContain('–')
  })
})
