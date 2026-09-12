import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockApi = vi.fn()

vi.mock('../../src/api/index', () => ({ api: mockApi }))

vi.mock('../../src/stores/modules', () => ({
  useModulesStore: vi.fn(),
}))

const _capturedQueries: any[] = []

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    _capturedQueries.push(opts)
    return { data: { value: undefined }, isLoading: { value: false } }
  }),
}))

describe('src/queries/modules', () => {
  beforeEach(() => {
    _capturedQueries.length = 0
    vi.clearAllMocks()
  })

  describe('useModulesQuery', () => {
    it('registers a query', async () => {
      const { useModulesQuery } = await import('../../src/queries/modules')
      useModulesQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryKey contains modules namespace', async () => {
      const { useModulesQuery } = await import('../../src/queries/modules')
      useModulesQuery()
      expect(JSON.stringify(_capturedQueries[0].queryKey)).toContain('modules')
    })

    it('queryFn calls api with /modules', async () => {
      const { useModulesQuery } = await import('../../src/queries/modules')
      useModulesQuery()
      mockApi.mockResolvedValueOnce({ nextcloud: { enabled: true }, photos: { enabled: false } })
      await _capturedQueries[0].queryFn()
      expect(mockApi).toHaveBeenCalledWith('/modules')
    })
  })
})
