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

  describe('load()', () => {
    it('fetches and returns module settings', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      const response = { nextcloud: { enabled: true }, photos: { enabled: false } }
      mockApi.mockResolvedValueOnce(response)
      const store = useModulesStore()
      const result = await store.load()
      expect(result).toEqual(response)
      expect(store.data).toEqual(response)
    })

    it('returns cached data within TTL', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      const response = { nextcloud: { enabled: true }, photos: { enabled: true } }
      mockApi.mockResolvedValueOnce(response)
      const store = useModulesStore()
      await store.load()
      await store.load()
      expect(mockApi).toHaveBeenCalledTimes(1)
    })

    it('re-fetches when force=true ignoring cache', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      const r1 = { nextcloud: { enabled: true }, photos: { enabled: true } }
      const r2 = { nextcloud: { enabled: false }, photos: { enabled: false } }
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
    })

    it('returns correct value from loaded data', async () => {
      const { useModulesStore } = await import('../../src/stores/modules')
      const response = { nextcloud: { enabled: false }, photos: { enabled: true } }
      mockApi.mockResolvedValueOnce(response)
      const store = useModulesStore()
      await store.load()
      expect(store.isEnabled('nextcloud')).toBe(false)
      expect(store.isEnabled('photos')).toBe(true)
    })
  })
})
