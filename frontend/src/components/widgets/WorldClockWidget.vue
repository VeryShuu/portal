<template>
  <section
    v-if="cities.length"
    class="widget world-clock"
    :style="{ '--cols': columns }"
  >
    <div class="widget__header">
      <h3 class="widget__title">
        {{ t('home.sections.worldClock') }}
      </h3>
    </div>
    <div
      class="clock-grid"
      aria-live="polite"
    >
      <div
        v-for="city in cities"
        :key="city.id"
        class="clock-cube"
        :class="{ 'clock-cube--night': isNight(city.timezone), 'clock-cube--weekend': isWeekend(city.timezone) }"
        :title="`${city.name} • ${city.timezone}`"
      >
        <div class="clock-cube__head">
          <span class="clock-cube__name">{{ city.name }}</span>
          <span class="clock-cube__diff">{{ diffLabel(city.timezone) }}</span>
        </div>
        <div class="clock-cube__time">
          <span
            class="clock-cube__icon"
            :aria-hidden="true"
          >{{ cubeIcon(city) }}</span>
          <span class="clock-cube__hm">{{ formatTime(city.timezone) }}</span>
          <span
            v-if="weatherFor(city)"
            class="clock-cube__temp"
          >{{ formatTemp(weatherFor(city)!.temperature) }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWorldClockCities, type ClockCity } from '../../composables/useWorldClockCities'
import { useWorldClockWeather, weatherEmoji } from '../../composables/useWorldClockWeather'

const { t } = useI18n()
const { cities } = useWorldClockCities()
const { getFor, dispose } = useWorldClockWeather(cities)

function weatherFor(city: ClockCity) { return getFor(city) }

function cubeIcon(city: ClockCity): string {
  const w = getFor(city)
  if (w) return weatherEmoji(w.code)
  return isNight(city.timezone) ? '🌙' : '☀'
}

function formatTemp(value: number): string {
  const rounded = Math.round(value)
  return `${rounded > 0 ? '+' : ''}${rounded}°`
}

const now = ref(new Date())
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  const sync = () => {
    now.value = new Date()
    timer = setInterval(() => { now.value = new Date() }, 30_000)
  }
  const ms = 1000 - (Date.now() % 1000)
  setTimeout(sync, ms)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer); dispose() })

const columns = computed(() => {
  const n = cities.value.length
  if (n <= 1) return 1
  return 2
})

function getParts(tz: string) {
  try {
    const fmt = new Intl.DateTimeFormat('en-GB', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      weekday: 'short',
      hourCycle: 'h23',
    })
    const parts = fmt.formatToParts(now.value)
    const o: Record<string, string> = {}
    for (const p of parts) o[p.type] = p.value
    return o
  } catch {
    return {} as Record<string, string>
  }
}

function formatTime(tz: string) {
  const p = getParts(tz)
  return `${p.hour ?? '--'}:${p.minute ?? '--'}`
}

function tzOffsetMinutes(tz: string, base = now.value): number {
  try {
    const dtf = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    })
    const parts = dtf.formatToParts(base)
    const f: Record<string, string> = {}
    for (const p of parts) f[p.type] = p.value
    const asUTC = Date.UTC(
      Number(f.year), Number(f.month) - 1, Number(f.day),
      Number(f.hour) === 24 ? 0 : Number(f.hour),
      Number(f.minute), Number(f.second),
    )
    return Math.round((asUTC - base.getTime()) / 60000)
  } catch {
    return 0
  }
}

function diffLabel(tz: string): string {
  const local = -now.value.getTimezoneOffset()
  const target = tzOffsetMinutes(tz)
  const diffH = Math.round((target - local) / 60)
  if (diffH === 0) return '±0'
  return diffH > 0 ? `+${diffH}` : `${diffH}`
}

function getHour(tz: string): number {
  const p = getParts(tz)
  return Number(p.hour ?? '12')
}

function isNight(tz: string): boolean {
  const h = getHour(tz)
  return h < 7 || h >= 21
}

function isWeekend(tz: string): boolean {
  const wd = getParts(tz).weekday ?? ''
  return wd === 'Sat' || wd === 'Sun'
}
</script>

<style scoped>
.clock-grid {
  display: grid;
  grid-template-columns: repeat(var(--cols, 2), minmax(0, 1fr));
  gap: 8px;
}
.clock-cube {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: var(--color-bg-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  transition: border-color var(--t-fast), background var(--t-fast);
}
.clock-cube:hover {
  border-color: var(--color-brand-red);
}
.clock-cube--night {
  background: var(--color-brand-ice, rgba(99, 122, 232, 0.08));
}
[data-theme='dark'] .clock-cube--night {
  background: rgba(99, 122, 232, 0.15);
}
.clock-cube--weekend {
  opacity: 0.78;
}
.clock-cube__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  font-size: 11px;
  letter-spacing: 0.06em;
}
.clock-cube__name {
  font-weight: 700;
  color: var(--color-text);
  font-size: 12px;
  letter-spacing: normal;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.clock-cube__diff {
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--color-text-muted);
  font-size: 10px;
  padding: 1px 5px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 999px;
}
.clock-cube__time {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.clock-cube__icon {
  font-size: 11px;
  opacity: 0.7;
}
.clock-cube__hm {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.clock-cube__temp {
  margin-left: auto;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
