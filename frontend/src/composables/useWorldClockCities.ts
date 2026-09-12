import { ref, watch } from 'vue'

export interface ClockCity {
  id: string
  name: string
  code: string
  timezone: string
  lat?: number
  lon?: number
}

const STORAGE_KEY = 'portal.worldClockCities.v2'

const DEFAULT_CITIES: ClockCity[] = [
  { id: 'msk', name: 'Москва',      code: 'MSK', timezone: 'Europe/Moscow',     lat: 55.7558, lon: 37.6173 },
  { id: 'vvo', name: 'Владивосток', code: 'VVO', timezone: 'Asia/Vladivostok', lat: 43.1155, lon: 131.8855 },
  { id: 'sah', name: 'Сахалин',     code: 'SAH', timezone: 'Asia/Sakhalin',    lat: 46.9588, lon: 142.7386 },
  { id: 'pus', name: 'Пусан',       code: 'PUS', timezone: 'Asia/Seoul',       lat: 35.1796, lon: 129.0756 },
]

function load(): ClockCity[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return [...DEFAULT_CITIES]
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return [...DEFAULT_CITIES]
    return parsed.filter(
      (c): c is ClockCity =>
        c && typeof c.id === 'string' && typeof c.name === 'string' &&
        typeof c.code === 'string' && typeof c.timezone === 'string',
    )
  } catch {
    return [...DEFAULT_CITIES]
  }
}

const cities = ref<ClockCity[]>(load())

watch(
  cities,
  (val) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(val))
    } catch {
      /* ignore quota / privacy mode errors */
    }
  },
  { deep: true },
)

function isValidTimezone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz })
    return true
  } catch {
    return false
  }
}

function genId(): string {
  return `city-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function useWorldClockCities() {
  function add(city: Omit<ClockCity, 'id'>) {
    cities.value = [...cities.value, { ...city, id: genId() }]
  }
  function update(id: string, patch: Partial<Omit<ClockCity, 'id'>>) {
    cities.value = cities.value.map(c => (c.id === id ? { ...c, ...patch } : c))
  }
  function remove(id: string) {
    cities.value = cities.value.filter(c => c.id !== id)
  }
  function reset() {
    cities.value = [...DEFAULT_CITIES]
  }
  function reorder(next: ClockCity[]) {
    cities.value = next
  }
  return { cities, add, update, remove, reset, reorder, isValidTimezone }
}

export { DEFAULT_CITIES }
