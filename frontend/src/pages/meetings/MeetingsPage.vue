<template>
  <div class="meetings-page">
    <MeetingsFilters
      :formatted-date="formattedDate"
      :formatted-dow="formattedDow"
      @prev="prevDay"
      @next="nextDay"
      @today="today"
    />

    <MeetingsCalendar
      :rooms="rooms"
      :bookings="bookings"
      :date="currentDate"
      :start-hour="startHour"
      :end-hour="endHour"
      :is-loading="isLoading"
      @slot-click="onSlotClick"
      @booking-click="onBookingClick"
    />

    <MeetingFormDialog
      v-model:show="dialogVisible"
      :booking="selectedBooking"
      :prefill-room-ids="prefillRoomIds"
      :prefill-start="prefillStart"
      :prefill-end="prefillEnd"
      @saved="onSaved"
    />

    <MeetingsList
      v-model:show="bookingDetailVisible"
      :booking="selectedBooking"
      :can-edit="canEditBooking"
      @edit="openEditDialog"
      @confirm-delete="confirmDeleteBooking"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialog, useMessage } from 'naive-ui'
import { useModulesStore } from '../../stores/modules'
import { useAuthStore } from '../../stores/auth'
import {
  useDeleteBookingMutation,
  useDeleteSeriesMutation,
} from '../../queries/meetings'
import type { BookingOut } from '../../api/meetings'
import MeetingFormDialog from '../../components/meetings/MeetingFormDialog.vue'
import MeetingsFilters from '../../components/meetings/MeetingsFilters.vue'
import MeetingsCalendar from '../../components/meetings/MeetingsCalendar.vue'
import MeetingsList from '../../components/meetings/MeetingsList.vue'
import { useMeetingsQuery } from './composables/useMeetingsQuery'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const modulesStore = useModulesStore()
const auth = useAuthStore()
const dialog = useDialog()
const message = useMessage()

const {
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
} = useMeetingsQuery()

const dialogVisible = ref(false)
const bookingDetailVisible = ref(false)
const selectedBooking = ref<BookingOut | null>(null)
const prefillRoomIds = ref<string[]>([])
const prefillStart = ref<string | undefined>()
const prefillEnd = ref<string | undefined>()

const canEditBooking = computed(() =>
  selectedBooking.value !== null && (
    selectedBooking.value.creator_id === auth.user?.id || auth.isAdmin
  ),
)

function openCreateDialog(roomId?: string, start?: string, end?: string) {
  selectedBooking.value = null
  prefillRoomIds.value = roomId ? [roomId] : []
  prefillStart.value = start
  prefillEnd.value = end
  dialogVisible.value = true
}

function onSlotClick(payload: { roomId: string; start: string; end: string }) {
  openCreateDialog(payload.roomId, payload.start, payload.end)
}

function onBookingClick(booking: BookingOut) {
  selectedBooking.value = booking
  bookingDetailVisible.value = true
}

function openEditDialog() {
  bookingDetailVisible.value = false
  dialogVisible.value = true
}

const deleteBookingMutation = useDeleteBookingMutation()
const deleteSeriesMutation = useDeleteSeriesMutation()

async function performDelete(scope: 'this' | 'series') {
  if (!selectedBooking.value) return
  const id = selectedBooking.value.id
  const seriesId = selectedBooking.value.series_id
  try {
    if (scope === 'series' && seriesId) {
      await deleteSeriesMutation.mutateAsync(seriesId)
    } else {
      await deleteBookingMutation.mutateAsync({ id, dto: { apply_to: 'this' } })
    }
    bookingDetailVisible.value = false
    selectedBooking.value = null
    message.success(t('meetings.detail.deleted'))
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

function confirmDeleteBooking() {
  if (!selectedBooking.value) return
  const meetingTitle = selectedBooking.value.title
  if (selectedBooking.value.series_id) {
    dialog.warning({
      title: t('common.confirm'),
      content: `«${meetingTitle}»: ${t('meetings.detail.deleteSeriesPrompt')}`,
      positiveText: t('meetings.detail.deleteWholeSeries'),
      negativeText: t('meetings.detail.deleteThisOnly'),
      onPositiveClick: () => {
        performDelete('series')
      },
      onNegativeClick: () => {
        performDelete('this')
      },
    })
    return
  }
  dialog.warning({
    title: t('common.confirm'),
    content: `«${meetingTitle}»: ${t('meetings.detail.deleteConfirm')}`,
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => {
      performDelete('this')
    },
  })
}

onMounted(() => {
  modulesStore.load()
})
</script>

<style scoped>
.meetings-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: calc(100vh - var(--layout-header-height, 64px) - 48px);
  min-height: 480px;
}
@media (max-width: 767px) {
  .meetings-page {
    height: calc(100vh - var(--layout-header-height, 64px) - 32px);
  }
}
</style>
