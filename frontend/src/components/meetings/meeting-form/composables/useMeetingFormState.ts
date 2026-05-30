import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  dateRuRU, dateEnUS,
  useMessage,
  type FormInst,
} from 'naive-ui'
import { mapMeetingsError } from '../../../../utils/mapMeetingsError'
import { useModulesStore } from '../../../../stores/modules'
import { useAuthStore } from '../../../../stores/auth'
import {
  useMeetingRoomsQuery,
  useCreateBookingMutation,
  useUpdateBookingMutation,
  useDeleteBookingMutation,
  useUpdateSeriesMutation,
  useDeleteSeriesMutation,
} from '../../../../queries/meetings'
import type { BookingOut, InvitedUser, RecurrenceRule } from '../../../../api/meetings'

export interface FormState {
  title: string
  description: string
  room_ids: string[]
  invited_users: InvitedUser[]
  recurrence: RecurrenceRule | null
  apply_to: 'this' | 'series'
  start_time: number | null
  end_time: number | null
}

const DURATION_PRESETS = [30, 60, 90, 120, 150, 180]
const MS_PER_MIN = 60_000

function toTimestamp(iso: string | undefined): number | null {
  return iso ? new Date(iso).getTime() : null
}

export interface MeetingFormProps {
  show: boolean
  booking?: BookingOut | null
  prefillRoomIds?: string[]
  prefillStart?: string
  prefillEnd?: string
}

export type MeetingFormEmit = {
  (e: 'update:show', v: boolean): void
  (e: 'saved'): void
}

export function useMeetingFormState(props: Readonly<MeetingFormProps>, emit: MeetingFormEmit) {
  const { t, locale } = useI18n()
  const message = useMessage()
  const modulesStore = useModulesStore()
  const auth = useAuthStore()

  const isEdit = computed(() => !!props.booking)
  const canDelete = computed(() =>
    !!props.booking && (
      props.booking.creator_id === auth.user?.id || auth.isAdmin
    ),
  )
  const minSearchChars = computed(() => modulesStore.meetingsSettings.min_search_chars)
  const maxRecurrenceDays = computed(() => modulesStore.meetingsSettings.max_recurrence_horizon_days)
  const modulesEnabled = computed(() => modulesStore.isEnabled('meetings'))
  const dateLocaleValue = computed(() => (locale.value === 'ru' ? dateRuRU : dateEnUS))

  const { data: rooms, isLoading: roomsLoading } = useMeetingRoomsQuery(false, { enabled: modulesEnabled })

  function makeForm(): FormState {
    if (props.booking) {
      return {
        title: props.booking.title,
        description: props.booking.description ?? '',
        room_ids: props.booking.rooms.map(r => r.id),
        invited_users: [...props.booking.invited_users],
        recurrence: null,
        apply_to: 'this',
        start_time: toTimestamp(props.booking.start_time),
        end_time: toTimestamp(props.booking.end_time),
      }
    }
    return {
      title: '',
      description: '',
      room_ids: props.prefillRoomIds ?? [],
      invited_users: [],
      recurrence: null,
      apply_to: 'this',
      start_time: toTimestamp(props.prefillStart),
      end_time: toTimestamp(props.prefillEnd),
    }
  }

  function getInitialDuration(): number | null {
    if (props.booking) {
      const diffMin = Math.round(
        (new Date(props.booking.end_time).getTime() - new Date(props.booking.start_time).getTime()) / MS_PER_MIN,
      )
      return DURATION_PRESETS.includes(diffMin) ? diffMin : null
    }
    return 60
  }

  const form = ref<FormState>(makeForm())
  const formRef = ref<FormInst | null>(null)
  const saving = ref(false)
  const deleting = ref(false)
  const conflictError = ref<Array<{ room_name: string; booking_title: string; start: string; end: string }> | null>(null)
  const selectedDuration = ref<number | null>(getInitialDuration())

  const durationOptions = computed(() => [
    { label: t('meetings.form.duration30'),  value: 30 },
    { label: t('meetings.form.duration60'),  value: 60 },
    { label: t('meetings.form.duration90'),  value: 90 },
    { label: t('meetings.form.duration120'), value: 120 },
    { label: t('meetings.form.duration150'), value: 150 },
    { label: t('meetings.form.duration180'), value: 180 },
  ])

  const startDateStr = computed(() => {
    if (!form.value.start_time) return new Date().toISOString().slice(0, 10)
    return new Date(form.value.start_time).toISOString().slice(0, 10)
  })

  watch(selectedDuration, (dur) => {
    if (dur !== null && form.value.start_time !== null) {
      form.value.end_time = form.value.start_time + dur * MS_PER_MIN
    }
  })

  watch(() => form.value.start_time, (st) => {
    if (selectedDuration.value !== null && st !== null) {
      form.value.end_time = st + selectedDuration.value * MS_PER_MIN
    }
  })

  watch(() => props.show, (v) => {
    if (v) {
      form.value = makeForm()
      conflictError.value = null
      selectedDuration.value = getInitialDuration()
    }
  })

  function toggleRoom(id: string) {
    const idx = form.value.room_ids.indexOf(id)
    if (idx === -1) {
      form.value.room_ids = [...form.value.room_ids, id]
    } else {
      form.value.room_ids = form.value.room_ids.filter(r => r !== id)
    }
  }

  const { mutateAsync: doCreate } = useCreateBookingMutation()
  const { mutateAsync: doUpdate } = useUpdateBookingMutation()
  const { mutateAsync: doDelete } = useDeleteBookingMutation()
  const { mutateAsync: doUpdateSeries } = useUpdateSeriesMutation()
  const { mutateAsync: doDeleteSeries } = useDeleteSeriesMutation()

  function tsToIso(ts: number | null): string {
    if (ts === null) return ''
    const d = new Date(ts)
    d.setSeconds(0, 0)
    return d.toISOString()
  }

  async function onSubmit() {
    conflictError.value = null
    try {
      await formRef.value?.validate()
    } catch {
      return
    }

    saving.value = true
    try {
      if (isEdit.value && props.booking) {
        if (form.value.apply_to === 'series' && props.booking.series_id) {
          await doUpdateSeries({
            seriesId: props.booking.series_id,
            dto: {
              title: form.value.title,
              description: form.value.description || null,
              invited_users: form.value.invited_users,
            },
          })
        } else {
          await doUpdate({
            id: props.booking.id,
            dto: {
              apply_to: form.value.apply_to,
              title: form.value.title,
              description: form.value.description || null,
              start_time: tsToIso(form.value.start_time),
              end_time: tsToIso(form.value.end_time),
              room_ids: form.value.room_ids,
              invited_users: form.value.invited_users,
            },
          })
        }
      } else {
        await doCreate({
          title: form.value.title,
          description: form.value.description || null,
          start_time: tsToIso(form.value.start_time),
          end_time: tsToIso(form.value.end_time),
          room_ids: form.value.room_ids,
          invited_users: form.value.invited_users,
          recurrence: form.value.recurrence,
        })
      }
      message.success(t('meetings.form.savedSuccess'))
      emit('update:show', false)
      emit('saved')
    } catch (err: unknown) {
      const code = mapMeetingsError(err)
      if (code === 'BOOKING_CONFLICT') {
        const e = err as { data?: { conflicts?: unknown[] } }
        conflictError.value = e.data?.conflicts as Array<{ room_name: string; booking_title: string; start: string; end: string }>
      } else if (code === 'START_TIME_IN_PAST') {
        message.error(t('meetings.form.startTimeInPast'), { duration: 5000 })
      } else if (code === 'END_BEFORE_START') {
        message.error(t('meetings.form.endTimeAfterStart'), { duration: 5000 })
      } else {
        message.error(t('meetings.form.saveError'))
      }
    } finally {
      saving.value = false
    }
  }

  async function onDelete() {
    if (!props.booking) return
    deleting.value = true
    try {
      if (form.value.apply_to === 'series' && props.booking.series_id) {
        await doDeleteSeries(props.booking.series_id)
      } else {
        await doDelete({ id: props.booking.id, dto: { apply_to: 'this' } })
      }
      message.success(t('meetings.form.deletedSuccess'))
      emit('update:show', false)
      emit('saved')
    } catch {
      message.error(t('meetings.form.deleteError'))
    } finally {
      deleting.value = false
    }
  }

  function formatConflictTime(start: string, end: string): string {
    const s = new Date(start)
    const e = new Date(end)
    const loc = locale.value === 'ru' ? 'ru-RU' : 'en-GB'
    return `${s.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' })}–${e.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' })}`
  }

  return {
    form,
    formRef,
    saving,
    deleting,
    conflictError,
    selectedDuration,
    durationOptions,
    startDateStr,
    isEdit,
    canDelete,
    minSearchChars,
    maxRecurrenceDays,
    dateLocaleValue,
    rooms,
    roomsLoading,
    toggleRoom,
    onSubmit,
    onDelete,
    formatConflictTime,
  }
}
