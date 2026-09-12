import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

function city(lat: number, lon: number) {
  return { id: `${lat}-${lon}`, name: 'City', timezone: 'UTC', lat, lon }
}

async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

describe('cov-feat useWorldClockWeather', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.restoreAllMocks()
    vi.resetModules()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('weatherEmoji handles null/known/unknown codes', async () => {
    const mod = await import('../../src/composables/useWorldClockWeather')
    expect(mod.weatherEmoji(null)).toBe('')
    expect(mod.weatherEmoji(0)).toBe('☀')
    expect(mod.weatherEmoji(999)).toBe('🌡')
  })

  it('does not fetch for invalid city coordinates', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch' as any).mockResolvedValue({ ok: true, json: async () => ({}) } as any)
    const mod = await import('../../src/composables/useWorldClockWeather')
    const citiesRef = ref<any[]>([{ lat: undefined, lon: 1 }])
    const api = mod.useWorldClockWeather(citiesRef as any)

    expect(fetchSpy).not.toHaveBeenCalled()
    api.dispose()
  })

  it('fetches and caches weather data from successful response', async () => {
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(1000)
    vi.spyOn(globalThis, 'fetch' as any).mockResolvedValue({
      ok: true,
      json: async () => ({ current: { temperature_2m: 24, weather_code: 1 } }),
    } as any)

    const mod = await import('../../src/composables/useWorldClockWeather')
    const c = city(55.75, 37.62)
    const citiesRef = ref([c])
    const api = mod.useWorldClockWeather(citiesRef as any)

    await flush()
    const sample = api.getFor(c as any)
    expect(sample?.temperature).toBe(24)
    expect(sample?.code).toBe(1)
    expect(sample?.fetchedAt).toBe(1000)
    expect(localStorage.getItem('portal.worldClockWeather.v1')).toContain('55.75|37.62')
    nowSpy.mockRestore()
    api.dispose()
  })

  it('handles non-ok and thrown fetch gracefully', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch' as any)
      .mockResolvedValueOnce({ ok: false, json: async () => ({}) } as any)
      .mockRejectedValueOnce(new Error('network'))

    const mod = await import('../../src/composables/useWorldClockWeather')
    const c = city(1, 2)
    const citiesRef = ref([c])
    const api = mod.useWorldClockWeather(citiesRef as any)

    await flush()
    expect(api.getFor(c as any)).toBeNull()

    citiesRef.value = [city(3, 4)] as any
    await nextTick()
    await flush()
    expect(fetchSpy).toHaveBeenCalledTimes(2)
    api.dispose()
  })

  it('refreshes stale entries on interval and clears interval when disposed', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(10_000)
    const fetchSpy = vi.spyOn(globalThis, 'fetch' as any).mockResolvedValue({
      ok: true,
      json: async () => ({ current: { temperature_2m: 10, weather_code: 0 } }),
    } as any)
    const clearSpy = vi.spyOn(globalThis, 'clearInterval')

    const mod = await import('../../src/composables/useWorldClockWeather')
    const c = city(10, 20)
    const citiesRef = ref([c])

    const a = mod.useWorldClockWeather(citiesRef as any)
    const b = mod.useWorldClockWeather(citiesRef as any)

    await flush()
    expect(fetchSpy).toHaveBeenCalledTimes(2)

    vi.spyOn(Date, 'now').mockReturnValue(10_000 + 31 * 60 * 1000)
    vi.advanceTimersByTime(30 * 60 * 1000)
    await flush()
    expect(fetchSpy).toHaveBeenCalledTimes(3)

    a.dispose()
    expect(clearSpy).not.toHaveBeenCalled()
    b.dispose()
    expect(clearSpy).toHaveBeenCalled()
  })

  it('loadCache survives malformed localStorage JSON', async () => {
    localStorage.setItem('portal.worldClockWeather.v1', '{bad')
    vi.spyOn(globalThis, 'fetch' as any).mockResolvedValue({ ok: false, json: async () => ({}) } as any)

    const mod = await import('../../src/composables/useWorldClockWeather')
    const c = city(7, 8)
    const api = mod.useWorldClockWeather(ref([c]) as any)
    await flush()
    expect(api.getFor(c as any)).toBeNull()
    api.dispose()
  })
})
