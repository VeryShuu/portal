<template>
  <button
    class="booking-card"
    :style="cardStyle"
    :title="booking.title"
    type="button"
    @click="$emit('click', booking)"
  >
    <div class="booking-card__title">
      {{ booking.title }}
    </div>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BookingOut } from '../../api/meetings'

const props = defineProps<{
  booking: BookingOut
  slotHeight: number
  startHour: number
  pixelsPerMinute: number
  roomTimezone?: string
}>()

defineEmits<{
  (e: 'click', booking: BookingOut): void
}>()

function minutesInTz(iso: string, tz?: string): number {
  const d = new Date(iso)
  if (!tz) {
    return d.getHours() * 60 + d.getMinutes()
  }
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(d)
    const h = Number(parts.find(p => p.type === 'hour')?.value ?? '0')
    const m = Number(parts.find(p => p.type === 'minute')?.value ?? '0')
    return h * 60 + m
  } catch {
    return d.getHours() * 60 + d.getMinutes()
  }
}

const TITLE_LINE_HEIGHT_PX = 16
const TITLE_VERTICAL_PADDING_PX = 8

const cardStyle = computed(() => {
  const startMinutes = minutesInTz(props.booking.start_time, props.roomTimezone)
  const endMinutes = minutesInTz(props.booking.end_time, props.roomTimezone)
  const offsetMinutes = startMinutes - props.startHour * 60
  let durationMinutes = endMinutes - startMinutes
  if (durationMinutes < 0) {
    durationMinutes += 24 * 60
  }

  const heightPx = Math.max(durationMinutes * props.pixelsPerMinute, 20)
  const availableForTitle = Math.max(heightPx - TITLE_VERTICAL_PADDING_PX, TITLE_LINE_HEIGHT_PX)
  const lineClamp = Math.max(1, Math.floor(availableForTitle / TITLE_LINE_HEIGHT_PX))

  return {
    top: `${offsetMinutes * props.pixelsPerMinute}px`,
    height: `${heightPx}px`,
    '--booking-title-line-clamp': String(lineClamp),
  }
})
</script>

<style scoped>
.booking-card {
  position: absolute;
  left: 2px;
  right: 2px;
  background: var(--meetings-event-bg, #dbeafe);
  border: 1px solid var(--meetings-event-border, #93c5fd);
  border-left: 3px solid var(--meetings-event-accent, #1d4ed8);
  border-radius: 4px;
  padding: 4px 6px;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.3;
  z-index: 1;
  transition: box-shadow 0.15s;
}
.booking-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  z-index: 2;
}
.booking-card:focus-visible {
  outline: 2px solid var(--meetings-event-accent, #1d4ed8);
  outline-offset: 1px;
}
.booking-card__title {
  font-weight: 600;
  color: var(--meetings-event-fg, #1e3a8a);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: var(--booking-title-line-clamp, 1);
  line-clamp: var(--booking-title-line-clamp, 1);
  overflow: hidden;
  text-overflow: ellipsis;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.booking-card__time,
.booking-card__organizer {
  color: var(--meetings-event-accent, #1d4ed8);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
