<template>
  <!-- Карточка рендерится всегда (даже до загрузки городов) — skeleton-плейсхолдер
       с фиксированными размерами предотвращает layout-shift (CLS) при загрузке. -->
  <div
    class="hero-clock"
    :class="{ 'hero-clock--loading': !cities.length }"
    aria-label="Время в городах"
  >
    <div
      v-if="!cities.length"
      class="hero-clock__skeleton"
    >
      <span class="hero-clock__skeleton-title" />
      <span class="hero-clock__skeleton-text" />
    </div>
    <div
      v-else
      class="hero-clock__grid"
    >
      <div
        v-for="city in cities"
        :key="city.id"
        class="hero-clock__item"
        :class="{ 'hero-clock__item--night': isNight(city.timezone) }"
        :title="`${city.name} • ${city.timezone}`"
      >
        <div class="hero-clock__head">
          <span class="hero-clock__name">{{ city.name }}</span>
          <span class="hero-clock__diff">{{ diffLabel(city.timezone) }}</span>
        </div>
        <div class="hero-clock__time">
          <span
            class="hero-clock__icon"
            aria-hidden="true"
          >{{ cubeIcon(city) }}</span>
          <span class="hero-clock__hm">{{ formatTime(city.timezone) }}</span>
          <span
            v-if="weatherFor(city)"
            class="hero-clock__temp"
          >{{ formatTemp(weatherFor(city)!.temperature) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useWorldClockCities, type ClockCity } from '../../composables/useWorldClockCities'
import { useWorldClockWeather, weatherEmoji } from '../../composables/useWorldClockWeather'

const { cities } = useWorldClockCities()
const { getFor, dispose } = useWorldClockWeather(cities)

function weatherFor(city: ClockCity) {
  return getFor(city)
}

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
let startTimeout: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  const sync = () => {
    startTimeout = null
    now.value = new Date()
    timer = setInterval(() => {
      now.value = new Date()
    }, 30_000)
  }
  const ms = 1000 - (Date.now() % 1000)
  startTimeout = setTimeout(sync, ms)
})
onBeforeUnmount(() => {
  if (startTimeout) clearTimeout(startTimeout)
  if (timer) clearInterval(timer)
  dispose()
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
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
    const parts = dtf.formatToParts(base)
    const f: Record<string, string> = {}
    for (const p of parts) f[p.type] = p.value
    const asUTC = Date.UTC(
      Number(f.year),
      Number(f.month) - 1,
      Number(f.day),
      Number(f.hour) === 24 ? 0 : Number(f.hour),
      Number(f.minute),
      Number(f.second),
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
</script>

<style scoped>
/* Стеклянная карточка в правом верхнем углу Hero. Полупрозрачный белый фон +
   blur, чтобы города читались поверх любого фото-фона баннера. Масштаб +20%. */
.hero-clock {
  width: 310px;
  padding: 17px 19px;
  border-radius: var(--radius-card, 16px);
  background: rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: #fff;
}
.hero-clock__grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.hero-clock__item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 7px 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.1);
}
.hero-clock__item--night {
  background: rgba(20, 30, 60, 0.35);
}
.hero-clock__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 5px;
}
.hero-clock__name {
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hero-clock__diff {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  font-variant-numeric: tabular-nums;
}
.hero-clock__time {
  display: flex;
  align-items: baseline;
  gap: 5px;
}
.hero-clock__icon {
  font-size: 12px;
  opacity: 0.85;
}
.hero-clock__hm {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}
.hero-clock__temp {
  margin-left: auto;
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.8);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 720px) {
  .hero-clock {
    width: 100%;
  }
  .hero-clock__grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Skeleton-плейсхолдер при загрузке городов (anti-CLS, п.6 UX-аудита). */
.hero-clock--loading {
  min-height: 110px;
}
.hero-clock__skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 0;
}
.hero-clock__skeleton-title,
.hero-clock__skeleton-text {
  display: block;
  height: 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.18);
  animation: hero-clock-pulse 1.4s ease-in-out infinite;
}
.hero-clock__skeleton-title { width: 60%; }
.hero-clock__skeleton-text { width: 85%; height: 20px; }
@keyframes hero-clock-pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.85; }
}
@media (prefers-reduced-motion: reduce) {
  .hero-clock__skeleton-title,
  .hero-clock__skeleton-text { animation: none; }
}
</style>
