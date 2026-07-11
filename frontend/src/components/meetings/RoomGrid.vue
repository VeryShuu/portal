<template>
  <div
    ref="wrapperEl"
    class="room-grid-wrapper"
    :class="{ 'room-grid-wrapper--mobile': isMobile }"
  >
    <div
      ref="gridEl"
      class="room-grid"
      :style="{ '--px-per-min': `${PX_PER_MIN}px`, '--slot-height': `${slotHeight}px` }"
    >
      <div class="room-grid__time-col">
        <div class="room-grid__header-cell room-grid__corner" />
        <div class="room-grid__time-slots">
          <div
            v-for="slot in timeSlots"
            :key="slot.label"
            class="room-grid__time-label"
            :class="{ 'room-grid__time-label--hour': slot.isHour }"
            :style="{ height: `${slotHeight}px` }"
          >
            <span v-if="slot.isHour">{{ slot.label }}</span>
          </div>
        </div>
      </div>

      <div
        v-for="room in sortedRooms"
        :key="room.id"
        class="room-grid__room-col"
      >
        <div class="room-grid__header-cell">
          <a
            v-if="safeRoomLink(room)"
            :href="safeRoomLink(room)"
            target="_blank"
            rel="noopener noreferrer"
            class="room-grid__room-name room-grid__room-name--link"
          >{{ room.name }}</a>
          <span
            v-else
            class="room-grid__room-name"
          >{{ room.name }}</span>
          <span
            v-if="showTz(room)"
            class="room-grid__room-tz"
            :title="t('meetings.grid.roomTzTooltip')"
          >{{ shortTz(room.timezone) }}</span>
        </div>

        <div
          class="room-grid__cells"
          role="grid"
          :aria-label="`${room.name} ${t('meetings.grid.slotsLabel')}`"
          :style="{ height: `${totalHeight}px` }"
          tabindex="0"
          @click="onCellClick($event, room.id)"
          @keydown.enter.prevent="onCellKey($event, room.id)"
          @keydown.space.prevent="onCellKey($event, room.id)"
        >
          <div class="room-grid__slots-bg">
            <div
              v-for="slot in timeSlots"
              :key="slot.label"
              class="room-grid__slot"
              :class="{ 'room-grid__slot--hour': slot.isHour }"
              :style="{ height: `${slotHeight}px` }"
            />
          </div>

          <BookingCard
            v-for="b in bookingsForRoom(room.id)"
            :key="b.id"
            :booking="b"
            :slot-height="slotHeight"
            :start-hour="startHour"
            :pixels-per-minute="PX_PER_MIN"
            :room-timezone="room.timezone"
            @click="$emit('booking-click', b)"
          />

          <div
            v-if="isToday && currentTimeTop !== null"
            class="room-grid__now-line"
            :style="{ top: `${currentTimeTop}px` }"
          />
        </div>
      </div>
    </div>
    <div
      v-if="isMobile && sortedRooms.length > 1"
      class="room-grid__indicator"
      :aria-label="t('meetings.grid.mobileIndicator', { current: mobileActiveIndex + 1, total: sortedRooms.length })"
    >
      <span
        v-for="(_, idx) in sortedRooms"
        :key="idx"
        class="room-grid__indicator-dot"
        :class="{ 'room-grid__indicator-dot--active': idx === mobileActiveIndex }"
      />
      <span class="room-grid__indicator-text">
        {{ t('meetings.grid.mobileIndicator', { current: mobileActiveIndex + 1, total: sortedRooms.length }) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MeetingRoom, BookingOut } from '../../api/meetings'
import BookingCard from './BookingCard.vue'
import { useBreakpoints } from '../../composables/useBreakpoints'
import { isServiceLinkUrl } from '../../utils/url'

const { t } = useI18n()

const props = defineProps<{
  rooms: MeetingRoom[]
  bookings: BookingOut[]
  date: string
  startHour: number
  endHour: number
}>()

const sortedRooms = computed(() =>
  [...props.rooms].sort((a, b) => {
    const so = (a.sort_order ?? 0) - (b.sort_order ?? 0)
    if (so !== 0) return so
    return a.name.localeCompare(b.name)
  }),
)

const emit = defineEmits<{
  (e: 'slot-click', payload: { roomId: string; start: string; end: string }): void
  (e: 'booking-click', booking: BookingOut): void
}>()

const SLOT_MINUTES = 30
const MIN_PX_PER_MIN = 0.6
const MAX_PX_PER_MIN = 1.5
const HEADER_RESERVED_PX = 60
const { isMobile } = useBreakpoints()

const gridEl = ref<HTMLElement | null>(null)
const wrapperEl = ref<HTMLElement | null>(null)
const wrapperHeight = ref(0)
const headerHeight = ref(HEADER_RESERVED_PX)

const totalMinutes = computed(() => (props.endHour - props.startHour) * 60)

const PX_PER_MIN = computed(() => {
  if (totalMinutes.value <= 0) return MAX_PX_PER_MIN
  if (wrapperHeight.value <= 0) return MAX_PX_PER_MIN
  const available = wrapperHeight.value - headerHeight.value - 4
  if (available <= 0) return MIN_PX_PER_MIN
  const slotsCount = totalMinutes.value / SLOT_MINUTES
  const fitSlotPx = Math.floor(available / slotsCount)
  const fit = fitSlotPx / SLOT_MINUTES
  return Math.max(MIN_PX_PER_MIN, Math.min(MAX_PX_PER_MIN, fit))
})

const slotHeight = computed(() => Math.floor(PX_PER_MIN.value * SLOT_MINUTES))
const totalHeight = computed(() => slotHeight.value * (totalMinutes.value / SLOT_MINUTES))

const timeSlots = computed(() => {
  const slots: { label: string; minutes: number; isHour: boolean }[] = []
  for (let m = 0; m < totalMinutes.value; m += SLOT_MINUTES) {
    const h = props.startHour + Math.floor(m / 60)
    const min = m % 60
    slots.push({
      label: `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`,
      minutes: m,
      isHour: min === 0,
    })
  }
  return slots
})

const userTz = Intl.DateTimeFormat().resolvedOptions().timeZone

function showTz(room: MeetingRoom): boolean {
  return room.timezone !== userTz
}

function shortTz(tz: string): string {
  try {
    const now = new Date()
    const parts = new Intl.DateTimeFormat('en', { timeZone: tz, timeZoneName: 'shortOffset' }).formatToParts(now)
    const v = parts.find(p => p.type === 'timeZoneName')?.value
    if (v) return v.replace(/^GMT/, 'GMT')
    return tz
  } catch {
    return tz
  }
}

const bookingsByRoom = computed<Map<string, BookingOut[]>>(() => {
  const map = new Map<string, BookingOut[]>()
  for (const b of props.bookings) {
    for (const r of b.rooms) {
      const list = map.get(r.id)
      if (list) list.push(b)
      else map.set(r.id, [b])
    }
  }
  return map
})

function bookingsForRoom(roomId: string): BookingOut[] {
  return bookingsByRoom.value.get(roomId) ?? []
}

/**
 * FE-1 (code-audit): безопасная ссылка на переговорку.
 * Возвращает link только для разрешённых схем (http/https/internal-path),
 * иначе undefined → имя комнаты рендерится plain-text (без кликабельного якоря).
 * Защищает от XSS через ``javascript:``/``data:``/``vbscript:`` в room.link.
 */
function safeRoomLink(room: MeetingRoom): string | undefined {
  return room.link && isServiceLinkUrl(room.link) ? room.link : undefined
}

const isToday = computed(() => {
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  return props.date === today
})

const nowTick = ref(Date.now())
let nowTimer: ReturnType<typeof setInterval> | null = null

const currentTimeTop = computed<number | null>(() => {
  void nowTick.value
  if (!isToday.value) return null
  const now = new Date()
  const minutes = now.getHours() * 60 + now.getMinutes() - props.startHour * 60
  if (minutes < 0 || minutes > totalMinutes.value) return null
  return minutes * PX_PER_MIN.value
})

const mobileActiveIndex = ref(0)

function onGridScroll() {
  if (!isMobile.value || !wrapperEl.value || !gridEl.value) return
  const wrap = wrapperEl.value
  const cols = gridEl.value.querySelectorAll<HTMLElement>('.room-grid__room-col')
  if (!cols.length) return
  const timeColWidth = gridEl.value.querySelector<HTMLElement>('.room-grid__time-col')?.offsetWidth ?? 0
  const scrollLeft = wrap.scrollLeft
  let best = 0
  let bestDist = Infinity
  cols.forEach((col, idx) => {
    const dist = Math.abs(col.offsetLeft - timeColWidth - scrollLeft)
    if (dist < bestDist) {
      bestDist = dist
      best = idx
    }
  })
  mobileActiveIndex.value = best
}

let resizeObs: ResizeObserver | null = null

function measureWrapper() {
  if (!wrapperEl.value) return
  wrapperHeight.value = wrapperEl.value.clientHeight
  const header = gridEl.value?.querySelector<HTMLElement>('.room-grid__header-cell')
  if (header) {
    headerHeight.value = header.offsetHeight
  }
}

onMounted(() => {
  nowTimer = setInterval(() => {
    nowTick.value = Date.now()
  }, 60_000)
  wrapperEl.value?.addEventListener('scroll', onGridScroll, { passive: true })
  onGridScroll()
  measureWrapper()
  if (typeof ResizeObserver !== 'undefined' && wrapperEl.value) {
    resizeObs = new ResizeObserver(() => {
      measureWrapper()
    })
    resizeObs.observe(wrapperEl.value)
  }
  window.addEventListener('resize', measureWrapper)
})

onBeforeUnmount(() => {
  if (nowTimer) clearInterval(nowTimer)
  wrapperEl.value?.removeEventListener('scroll', onGridScroll)
  if (resizeObs) {
    resizeObs.disconnect()
    resizeObs = null
  }
  window.removeEventListener('resize', measureWrapper)
})

function onCellKey(_event: KeyboardEvent, roomId: string) {
  const startH = props.startHour
  const startStr = `${props.date}T${String(startH).padStart(2, '0')}:00:00`
  const endH = Math.min(startH + 1, props.endHour)
  const endStr = `${props.date}T${String(endH).padStart(2, '0')}:00:00`
  emit('slot-click', { roomId, start: startStr, end: endStr })
}

function onCellClick(event: MouseEvent, roomId: string) {
  const target = event.target as HTMLElement
  if (target.closest('.booking-card')) return

  const cells = (event.currentTarget as HTMLElement)
  const rect = cells.getBoundingClientRect()
  const y = event.clientY - rect.top
  const clickMinutes = Math.floor(y / PX_PER_MIN.value / SLOT_MINUTES) * SLOT_MINUTES
  const absoluteMinutes = clickMinutes + props.startHour * 60
  const endHourMinutes = props.endHour * 60
  const endMinutes = Math.min(absoluteMinutes + 60, endHourMinutes)
  // Guarantee at least one slot (handled by parent dialog if it needs to clamp further).
  const finalEnd = Math.max(endMinutes, absoluteMinutes + SLOT_MINUTES)

  const startH = Math.floor(absoluteMinutes / 60)
  const startM = absoluteMinutes % 60
  const endH = Math.floor(finalEnd / 60)
  const endM = finalEnd % 60

  const startStr = `${props.date}T${String(startH).padStart(2, '0')}:${String(startM).padStart(2, '0')}:00`
  const endStr = `${props.date}T${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}:00`

  emit('slot-click', { roomId, start: startStr, end: endStr })
}
</script>

<style scoped>
.room-grid-wrapper {
  overflow: auto;
  width: 100%;
  flex: 1 1 auto;
  min-height: 0;
}
.room-grid {
  display: flex;
  min-width: max-content;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--color-surface);
}
.room-grid__time-col,
.room-grid__room-col {
  min-height: 0;
}
.room-grid__time-col {
  display: flex;
  flex-direction: column;
  min-width: 52px;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg);
  flex-shrink: 0;
}
.room-grid__corner {
  border-bottom: 1px solid var(--color-border);
}
.room-grid__time-slots {
  position: relative;
}
.room-grid__time-label {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding-right: 6px;
  font-size: 11px;
  color: var(--color-text-muted);
  box-sizing: border-box;
  padding-top: 2px;
}
.room-grid__time-label--hour {
  border-top: 1px solid var(--color-border);
}
.room-grid__time-label:first-child {
  border-top: none;
}
.room-grid__room-col {
  display: flex;
  flex-direction: column;
  min-width: 160px;
  border-right: 1px solid var(--color-border);
  flex: 1;
}
.room-grid__room-col:last-child {
  border-right: none;
}
.room-grid__header-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 4px;
  min-height: 44px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
  text-align: center;
}
.room-grid__room-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.room-grid__room-name--link {
  color: var(--primary-color, #2563eb);
  text-decoration: underline;
}
.room-grid__room-tz {
  font-size: 10px;
  color: var(--color-text-muted);
  margin-top: 2px;
}
.room-grid__cells {
  position: relative;
  cursor: pointer;
}
.room-grid__slot {
  border-top: 1px dashed var(--color-border);
  box-sizing: border-box;
}
.room-grid__slot--hour {
  border-top: 1px solid var(--color-border);
}
.room-grid__slot:first-child {
  border-top: none;
}
.room-grid__now-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
  background: #ef4444;
  z-index: 10;
  pointer-events: none;
}
.room-grid__now-line::before {
  content: '';
  position: absolute;
  left: -4px;
  top: -3px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
}

.room-grid__indicator {
  display: none;
}

@media (max-width: 767px) {
  .room-grid-wrapper--mobile {
    scroll-snap-type: x mandatory;
    -webkit-overflow-scrolling: touch;
  }
  .room-grid-wrapper--mobile .room-grid__room-col {
    min-width: calc(100vw - 68px);
    scroll-snap-align: start;
  }
  .room-grid__indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 8px 4px;
    font-size: 12px;
    color: var(--color-text-muted);
  }
  .room-grid__indicator-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-border);
    transition: background 0.15s;
  }
  .room-grid__indicator-dot--active {
    background: var(--primary-color, #2563eb);
  }
  .room-grid__indicator-text {
    margin-left: 6px;
  }
}
</style>
