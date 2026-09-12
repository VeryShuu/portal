import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQueryClient } from '@tanstack/vue-query'
import { useModulesStore } from '../../../stores/modules'
import {
  useMeetingRoomsQuery,
  useMeetingBookingsQuery,
} from '../../../queries/meetings'
import { queryKeys } from '../../../queries/keys'

export function useMeetingsQuery() {
  const { locale } = useI18n()
  const modulesStore = useModulesStore()
  const qc = useQueryClient()

  const modulesEnabled = computed(() => modulesStore.isEnabled('meetings'))
  const startHour = computed(() => modulesStore.meetingsSettings.calendar_start_hour)
  const endHour = computed(() => modulesStore.meetingsSettings.calendar_end_hour)

  const currentDate = ref(new Date().toISOString().slice(0, 10))

  function today() {
    currentDate.value = new Date().toISOString().slice(0, 10)
  }

  function prevDay() {
    const d = new Date(currentDate.value)
    d.setDate(d.getDate() - 1)
    currentDate.value = d.toISOString().slice(0, 10)
  }

  function nextDay() {
    const d = new Date(currentDate.value)
    d.setDate(d.getDate() + 1)
    currentDate.value = d.toISOString().slice(0, 10)
  }

  const formattedDate = computed(() => {
    const d = new Date(currentDate.value + 'T12:00:00')
    return d.toLocaleDateString(locale.value === 'ru' ? 'ru-RU' : 'en-GB', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })
  })

  const formattedDow = computed(() => {
    const d = new Date(currentDate.value + 'T12:00:00')
    return d.toLocaleDateString(locale.value === 'ru' ? 'ru-RU' : 'en-GB', { weekday: 'long' })
  })

  const { data: roomsData, isLoading: roomsLoading } = useMeetingRoomsQuery(false, {
    enabled: modulesEnabled,
  })
  const { data: bookingsData, isLoading: bookingsLoading } = useMeetingBookingsQuery(
    computed(() => ({ date: currentDate.value })),
    { enabled: modulesEnabled },
  )

  const rooms = computed(() => roomsData.value ?? [])
  const bookings = computed(() => bookingsData.value ?? [])
  const isLoading = computed(() => roomsLoading.value || bookingsLoading.value)

  function onSaved() {
    qc.invalidateQueries({ queryKey: queryKeys.meetings.bookings({ date: currentDate.value }) })
    qc.invalidateQueries({ queryKey: queryKeys.meetings.myBookings({}) })
  }

  function handleMeetingsChanged() {
    qc.invalidateQueries({ queryKey: queryKeys.meetings.bookings({ date: currentDate.value }) })
    qc.invalidateQueries({ queryKey: queryKeys.meetings.myBookings({}) })
  }

  onMounted(() => {
    window.addEventListener('meetings:changed', handleMeetingsChanged)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('meetings:changed', handleMeetingsChanged)
  })

  return {
    currentDate,
    today,
    prevDay,
    nextDay,
    formattedDate,
    formattedDow,
    startHour,
    endHour,
    rooms,
    bookings,
    isLoading,
    onSaved,
  }
}
