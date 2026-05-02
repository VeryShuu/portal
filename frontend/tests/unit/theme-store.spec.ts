import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

describe('useThemeStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('isDark is false when localStorage has no theme', async () => {
    const { useThemeStore } = await import('../../src/stores/theme')
    const store = useThemeStore()
    expect(store.isDark).toBe(false)
  })

  it('isDark is true when localStorage has "dark"', async () => {
    localStorage.setItem('theme', 'dark')
    const { useThemeStore } = await import('../../src/stores/theme')
    setActivePinia(createPinia())
    const store = useThemeStore()
    expect(store.isDark).toBe(true)
  })

  it('toggle() flips isDark', async () => {
    const { useThemeStore } = await import('../../src/stores/theme')
    const store = useThemeStore()
    expect(store.isDark).toBe(false)
    store.toggle()
    expect(store.isDark).toBe(true)
    store.toggle()
    expect(store.isDark).toBe(false)
  })

  it('toggle() persists to localStorage', async () => {
    const { useThemeStore } = await import('../../src/stores/theme')
    const store = useThemeStore()
    store.toggle()
    expect(localStorage.getItem('theme')).toBe('dark')
    store.toggle()
    expect(localStorage.getItem('theme')).toBe('light')
  })
})
