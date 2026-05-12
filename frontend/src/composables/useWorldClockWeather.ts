import { ref, watch } from 'vue'
import type { ClockCity } from './useWorldClockCities'

export interface WeatherSample {
  temperature: number
  code: number
  fetchedAt: number
}

const CACHE_KEY = 'portal.worldClockWeather.v1'
const REFRESH_MS = 30 * 60 * 1000

const cache = ref<Record<string, WeatherSample>>(loadCache())
let timer: ReturnType<typeof setInterval> | null = null
let refCount = 0

function loadCache(): Record<string, WeatherSample> {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return typeof parsed === 'object' && parsed ? parsed : {}
  } catch {
    return {}
  }
}

watch(cache, (val) => {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(val))
  } catch {
    /* ignore */
  }
}, { deep: true })

function cityKey(c: ClockCity): string {
  return `${c.lat}|${c.lon}`
}

async function fetchBatch(cities: ClockCity[]): Promise<void> {
  const valid = cities.filter(c => typeof c.lat === 'number' && typeof c.lon === 'number')
  if (!valid.length) return

  const lats = valid.map(c => c.lat).join(',')
  const lons = valid.map(c => c.lon).join(',')
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${lats}&longitude=${lons}&current=temperature_2m,weather_code&timezone=auto`

  try {
    const res = await fetch(url, { method: 'GET' })
    if (!res.ok) return
    const data = await res.json()
    const list = Array.isArray(data) ? data : [data]
    const next = { ...cache.value }
    valid.forEach((city, idx) => {
      const entry = list[idx]
      const cur = entry?.current
      if (!cur || typeof cur.temperature_2m !== 'number' || typeof cur.weather_code !== 'number') return
      next[cityKey(city)] = {
        temperature: cur.temperature_2m,
        code: cur.weather_code,
        fetchedAt: Date.now(),
      }
    })
    cache.value = next
  } catch {
    /* network or CORS error — silently skip */
  }
}

function maybeRefresh(cities: ClockCity[]) {
  const now = Date.now()
  const stale = cities.some(c => {
    if (typeof c.lat !== 'number' || typeof c.lon !== 'number') return false
    const sample = cache.value[cityKey(c)]
    return !sample || now - sample.fetchedAt > REFRESH_MS
  })
  if (stale) void fetchBatch(cities)
}

export function useWorldClockWeather(citiesRef: { value: ClockCity[] }) {
  refCount++
  maybeRefresh(citiesRef.value)
  if (!timer) {
    timer = setInterval(() => maybeRefresh(citiesRef.value), REFRESH_MS)
  }

  watch(
    () => citiesRef.value.map(c => cityKey(c)).join(','),
    () => maybeRefresh(citiesRef.value),
  )

  function getFor(city: ClockCity): WeatherSample | null {
    return cache.value[cityKey(city)] ?? null
  }

  function dispose() {
    refCount--
    if (refCount <= 0 && timer) {
      clearInterval(timer)
      timer = null
      refCount = 0
    }
  }

  return { getFor, dispose }
}

const WMO_EMOJI: Record<number, string> = {
  0: '☀',
  1: '🌤', 2: '⛅', 3: '☁',
  45: '🌫', 48: '🌫',
  51: '🌦', 53: '🌦', 55: '🌦',
  56: '🌧', 57: '🌧',
  61: '🌧', 63: '🌧', 65: '🌧',
  66: '🌧', 67: '🌧',
  71: '🌨', 73: '🌨', 75: '🌨', 77: '🌨',
  80: '🌦', 81: '🌧', 82: '⛈',
  85: '🌨', 86: '🌨',
  95: '⛈', 96: '⛈', 99: '⛈',
}

export function weatherEmoji(code: number | undefined | null): string {
  if (code == null) return ''
  return WMO_EMOJI[code] ?? '🌡'
}
