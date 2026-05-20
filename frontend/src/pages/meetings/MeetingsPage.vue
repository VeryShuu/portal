<template>
  <div class="meetings-page">
    <div class="meetings-page__header">
      <div class="meetings-page__center">
        <div class="meetings-page__date-row">
          <n-button
            size="small"
            circle
            @click="prevDay"
          >
            <template #icon>
              <n-icon><ChevronBackOutline /></n-icon>
            </template>
          </n-button>
          <span class="meetings-page__date-text">{{ formattedDate }}</span>
          <n-button
            size="small"
            circle
            @click="nextDay"
          >
            <template #icon>
              <n-icon><ChevronForwardOutline /></n-icon>
            </template>
          </n-button>
        </div>
        <span class="meetings-page__day-of-week">{{ formattedDow }}</span>
        <n-button
          size="small"
          @click="today"
        >
          {{ t('meetings.today') }}
        </n-button>
      </div>
      <n-button
        v-if="auth.isAdmin"
        class="meetings-page__settings"
        size="tiny"
        quaternary
        circle
        :title="t('admin.modules.openMeetingsSettings')"
        @click="manage.open('module')"
      >
        <template #icon>
          <n-icon :component="SettingsOutline" />
        </template>
      </n-button>
    </div>

    <n-drawer
      v-if="auth.isAdmin"
      :show="manage.is('module')"
      :width="640"
      placement="right"
      :on-update:show="(v: boolean) => { if (!v) manage.close() }"
    >
      <n-drawer-content
        :title="t('admin.modules.openMeetingsSettings')"
        closable
      >
        <Suspense>
          <MeetingsModuleSettings />
        </Suspense>
      </n-drawer-content>
    </n-drawer>

    <div
      v-if="isLoading"
      class="meetings-page__loading"
    >
      <n-spin size="large" />
    </div>

    <template v-else>
      <RoomGrid
        v-if="rooms.length"
        :rooms="rooms"
        :bookings="bookings"
        :date="currentDate"
        :start-hour="startHour"
        :end-hour="endHour"
        @slot-click="onSlotClick"
        @booking-click="onBookingClick"
      />
      <n-empty
        v-else
        :description="t('meetings.noRooms')"
        class="meetings-page__empty"
      />
    </template>

    <MeetingFormDialog
      v-model:show="dialogVisible"
      :booking="selectedBooking"
      :prefill-room-ids="prefillRoomIds"
      :prefill-start="prefillStart"
      :prefill-end="prefillEnd"
      @saved="onSaved"
    />

    <n-modal
      v-model:show="bookingDetailVisible"
      preset="card"
      style="max-width: 480px"
      :title="selectedBooking?.title ?? ''"
    >
      <template v-if="selectedBooking">
        <div class="booking-detail">
          <div class="booking-detail__row">
            <span class="booking-detail__label">{{ t('meetings.detail.time') }}</span>
            <span>{{ formatTime(selectedBooking.start_time) }}–{{ formatTime(selectedBooking.end_time) }}</span>
          </div>
          <div class="booking-detail__row">
            <span class="booking-detail__label">{{ t('meetings.detail.rooms') }}</span>
            <span>{{ selectedBooking.rooms.map(r => r.name).join(', ') }}</span>
          </div>
          <div class="booking-detail__row">
            <span class="booking-detail__label">{{ t('meetings.detail.organizer') }}</span>
            <span>{{ selectedBooking.organizer_name }}</span>
          </div>
          <div
            v-if="selectedBooking.description"
            class="booking-detail__row"
          >
            <span class="booking-detail__label">{{ t('meetings.detail.description') }}</span>
            <span>{{ selectedBooking.description }}</span>
          </div>
          <div
            v-if="selectedBooking.invited_users.length"
            class="booking-detail__row"
          >
            <span class="booking-detail__label">{{ t('meetings.detail.participants') }}</span>
            <div>
              <div
                v-for="u in selectedBooking.invited_users"
                :key="u.user_id"
              >
                {{ u.full_name }} &lt;{{ u.email }}&gt;
              </div>
            </div>
          </div>
        </div>
      </template>
      <template #footer>
        <n-space justify="end">
          <n-button @click="bookingDetailVisible = false">
            {{ t('common.close') }}
          </n-button>
          <n-button
            v-if="canEditBooking"
            type="error"
            @click="confirmDeleteBooking"
          >
            {{ t('common.delete') }}
          </n-button>
          <n-button
            v-if="canEditBooking"
            type="primary"
            @click="openEditDialog"
          >
            {{ t('common.edit') }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDrawer, NDrawerContent, NIcon, NSpin, NEmpty, NModal, NSpace, useDialog, useMessage } from 'naive-ui'
import { ChevronBackOutline, ChevronForwardOutline, SettingsOutline } from '@vicons/ionicons5'
import { useManageDrawer } from '../../composables/useManageDrawer'
import { useQueryClient } from '@tanstack/vue-query'
import { useModulesStore } from '../../stores/modules'
import { useAuthStore } from '../../stores/auth'
import {
  useMeetingRoomsQuery,
  useMeetingBookingsQuery,
  useDeleteBookingMutation,
  useDeleteSeriesMutation,
} from '../../queries/meetings'
import { queryKeys } from '../../queries/keys'
import type { BookingOut } from '../../api/meetings'
import RoomGrid from '../../components/meetings/RoomGrid.vue'
import MeetingFormDialog from '../../components/meetings/MeetingFormDialog.vue'

const { t, locale } = useI18n()
const modulesStore = useModulesStore()
const auth = useAuthStore()
const qc = useQueryClient()
const dialog = useDialog()
const message = useMessage()

const manage = useManageDrawer(['module'])
const MeetingsModuleSettings = defineAsyncComponent(() => import('../../components/admin/MeetingsModuleSettings.vue'))

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
    const err = e as { status?: number; data?: { detail?: string } }
    if (err.status === 403) {
      message.error(t('errors.forbidden'))
    } else {
      message.error(err.data?.detail ?? t('errors.generic'))
    }
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

function onSaved() {
  qc.invalidateQueries({ queryKey: queryKeys.meetings.bookings({ date: currentDate.value }) })
  qc.invalidateQueries({ queryKey: queryKeys.meetings.myBookings({}) })
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(
    locale.value === 'ru' ? 'ru-RU' : 'en-GB',
    { hour: '2-digit', minute: '2-digit' },
  )
}

function handleMeetingsChanged() {
  qc.invalidateQueries({ queryKey: queryKeys.meetings.bookings({ date: currentDate.value }) })
  qc.invalidateQueries({ queryKey: queryKeys.meetings.myBookings({}) })
}

onMounted(() => {
  modulesStore.load()
  window.addEventListener('meetings:changed', handleMeetingsChanged)
})

onBeforeUnmount(() => {
  window.removeEventListener('meetings:changed', handleMeetingsChanged)
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
.meetings-page__header {
  display: flex;
  justify-content: center;
  position: relative;
}
.meetings-page__settings {
  position: absolute;
  right: 0;
  top: 0;
}
.meetings-page__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.meetings-page__date-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.meetings-page__date-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
}
.meetings-page__day-of-week {
  font-size: 12px;
  color: var(--color-text-muted);
  text-transform: capitalize;
}
.meetings-page__loading {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
.meetings-page__empty {
  margin-top: 48px;
}
.booking-detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.booking-detail__row {
  display: flex;
  gap: 12px;
  font-size: 14px;
}
.booking-detail__label {
  font-weight: 600;
  color: var(--color-text-muted);
  min-width: 110px;
  flex-shrink: 0;
}
</style>
