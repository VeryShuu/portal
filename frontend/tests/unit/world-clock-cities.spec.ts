import { describe, it, expect, beforeEach } from 'vitest'
import { useWorldClockCities, DEFAULT_CITIES } from '../../src/composables/useWorldClockCities'

describe('useWorldClockCities', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('isValidTimezone — отделяет валидные IANA-зоны от мусора', () => {
    const { isValidTimezone } = useWorldClockCities()
    expect(isValidTimezone('Europe/Moscow')).toBe(true)
    expect(isValidTimezone('Asia/Vladivostok')).toBe(true)
    expect(isValidTimezone('Mars/Olympus_Mons')).toBe(false)
    expect(isValidTimezone('')).toBe(false)
  })

  it('add — добавляет город с автогенерированным id', () => {
    const { cities, add, reset } = useWorldClockCities()
    reset()
    const before = cities.value.length
    add({ name: 'Лондон', code: 'LON', timezone: 'Europe/London' })
    expect(cities.value.length).toBe(before + 1)
    const added = cities.value[cities.value.length - 1]
    expect(added.name).toBe('Лондон')
    expect(added.id).toMatch(/^city-/)
  })

  it('update — патчит существующий город по id', () => {
    const { cities, add, update, reset } = useWorldClockCities()
    reset()
    add({ name: 'Лондон', code: 'LON', timezone: 'Europe/London' })
    const id = cities.value[cities.value.length - 1].id
    update(id, { name: 'London' })
    expect(cities.value.find((c) => c.id === id)?.name).toBe('London')
  })

  it('remove — удаляет город', () => {
    const { cities, add, remove, reset } = useWorldClockCities()
    reset()
    add({ name: 'Лондон', code: 'LON', timezone: 'Europe/London' })
    const id = cities.value[cities.value.length - 1].id
    remove(id)
    expect(cities.value.find((c) => c.id === id)).toBeUndefined()
  })

  it('reset — возвращает дефолтный набор', () => {
    const { cities, add, reset } = useWorldClockCities()
    add({ name: 'X', code: 'X', timezone: 'UTC' })
    reset()
    expect(cities.value.map((c) => c.id).sort()).toEqual(
      DEFAULT_CITIES.map((c) => c.id).sort(),
    )
  })

  it('reorder — заменяет последовательность', () => {
    const { cities, reset, reorder } = useWorldClockCities()
    reset()
    const reversed = [...cities.value].reverse()
    reorder(reversed)
    expect(cities.value.map((c) => c.id)).toEqual(reversed.map((c) => c.id))
  })
})
