<template>
  <div
    v-if="isLoading"
    class="meetings-calendar__loading"
  >
    <n-spin size="large" />
  </div>
  <template v-else>
    <RoomGrid
      v-if="rooms.length"
      :rooms="rooms"
      :bookings="bookings"
      :date="date"
      :start-hour="startHour"
      :end-hour="endHour"
      @slot-click="$emit('slot-click', $event)"
      @booking-click="$emit('booking-click', $event)"
    />
    <n-empty
      v-else
      :description="t('meetings.noRooms')"
      class="meetings-calendar__empty"
    />
  </template>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NSpin, NEmpty } from 'naive-ui'
import type { MeetingRoom, BookingOut } from '../../api/meetings'
import RoomGrid from './RoomGrid.vue'

defineProps<{
  rooms: MeetingRoom[]
  bookings: BookingOut[]
  date: string
  startHour: number
  endHour: number
  isLoading: boolean
}>()

defineEmits<{
  'slot-click': [payload: { roomId: string; start: string; end: string }]
  'booking-click': [booking: BookingOut]
}>()

const { t } = useI18n()
</script>

<style scoped>
.meetings-calendar__loading {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
.meetings-calendar__empty {
  margin-top: 48px;
}
</style>
