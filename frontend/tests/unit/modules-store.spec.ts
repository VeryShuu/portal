import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const mockApi = vi.fn()
vi.mock('../../src/api/index', () => ({ api: mockApi }))

describe('useModulesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockApi.mockReset()
  })

  const fullResponse = (over: Partial<any> = {}) => ({
    nextcloud: { enabled: true },
    photos: { enabled: false },
    meetings: {
      enabled: false,
      calendar_start_hour: 8,
      calendar_end_hour: 19,
      max_recurrence_horizon_days: 31,
      min_search_chars: 3,
    },
    ...over,
  })

  describe('load()', () => {
    it('fetches and returns module settings', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      const response = fullResponse()
      mockApi.mockResolvedValueOnce(response)
      const store = useModulesStore()
      const result = await store.load()
      expect(result).toEqual(response)
      expect(store.data).toEqual(response)
    })

    it('returns cached data within TTL', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      mockApi.mockResolvedValueOnce(fullResponse())
      const store = useModulesStore()
      await store.load()
      await store.load()
      expect(mockApi).toHaveBeenCalledTimes(1)
    })

    it('re-fetches when force=true ignoring cache', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      const r1 = fullResponse()
      const r2 = fullResponse({ nextcloud: { enabled: false } })
      mockApi.mockResolvedValueOnce(r1).mockResolvedValueOnce(r2)
      const store = useModulesStore()
      await store.load()
      await store.load(true)
      expect(mockApi).toHaveBeenCalledTimes(2)
      expect(store.data).toEqual(r2)
    })
  })

  describe('isEnabled()', () => {
    it('returns false when data is null (conservative, prevents flash-then-redirect)', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      const store = useModulesStore()
      expect(store.isEnabled('nextcloud')).toBe(false)
      expect(store.isEnabled('photos')).toBe(false)
      expect(store.isEnabled('meetings')).toBe(false)
    })

    it('returns correct value from loaded data', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      mockApi.mockResolvedValueOnce(
        fullResponse({
          nextcloud: { enabled: false },
          photos: { enabled: true },
          meetings: {
            enabled: true,
            calendar_start_hour: 9,
            calendar_end_hour: 18,
            max_recurrence_horizon_days: 31,
            min_search_chars: 3,
          },
        }),
      )
      const store = useModulesStore()
      await store.load()
      expect(store.isEnabled('nextcloud')).toBe(false)
      expect(store.isEnabled('photos')).toBe(true)
      expect(store.isEnabled('meetings')).toBe(true)
    })
  })

  describe('meetingsSettings computed', () => {
    it('returns defaults when data is null', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      const store = useModulesStore()
      expect(store.meetingsSettings).toMatchObject({
        enabled: false,
        calendar_start_hour: 8,
        calendar_end_hour: 19,
        max_recurrence_horizon_days: 31,
        min_search_chars: 3,
      })
    })

    it('returns server values when data is loaded', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      mockApi.mockResolvedValueOnce(
        fullResponse({
          meetings: {
            enabled: true,
            calendar_start_hour: 10,
            calendar_end_hour: 20,
            max_recurrence_horizon_days: 60,
            min_search_chars: 2,
          },
        }),
      )
      const store = useModulesStore()
      await store.load()
      expect(store.meetingsSettings.enabled).toBe(true)
      expect(store.meetingsSettings.calendar_start_hour).toBe(10)
      expect(store.meetingsSettings.min_search_chars).toBe(2)
    })
  })

  describe('setData()', () => {
    it('caches the provided modules payload', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      const store = useModulesStore()
      const payload = fullResponse({ meetings: {
        enabled: true,
        calendar_start_hour: 7,
        calendar_end_hour: 22,
        max_recurrence_horizon_days: 31,
        min_search_chars: 3,
      } })
      store.setData(payload)
      expect(store.data).toEqual(payload)
      await store.load()
      expect(mockApi).not.toHaveBeenCalled()
    })
  })
})
