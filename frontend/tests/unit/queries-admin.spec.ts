import { isRef } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetchUsers = vi.fn()
const mockFetchAuditEvents = vi.fn()
const mockFetchAuditEventTypes = vi.fn()
const mockFetchAuditQueueDepth = vi.fn()
const mockFetchDashboard = vi.fn()
const mockFetchTopArticles = vi.fn()
const mockFetchTopNews = vi.fn()
const mockFetchTopFiles = vi.fn()
const mockFetchTopLinks = vi.fn()
const mockFetchDepartments = vi.fn()
const mockFetchAttributeMappings = vi.fn()
const mockDiscoverAttributes = vi.fn()
const mockFetchLinks = vi.fn()
const mockApi = vi.fn()
const mockFetchEmailOutbox = vi.fn()
const mockFetchEmailOutboxItem = vi.fn()
const mockRetryEmailOutboxItem = vi.fn()
const mockCancelEmailOutboxItem = vi.fn()

vi.mock('../../src/api/users', () => ({
  fetchUsers: mockFetchUsers,
}))

vi.mock('../../src/api/audit', () => ({
  fetchAuditEvents: mockFetchAuditEvents,
  fetchAuditEventTypes: mockFetchAuditEventTypes,
  fetchAuditQueueDepth: mockFetchAuditQueueDepth,
}))

vi.mock('../../src/api/analytics', () => ({
  fetchDashboard: mockFetchDashboard,
  fetchTopArticles: mockFetchTopArticles,
  fetchTopNews: mockFetchTopNews,
  fetchTopFiles: mockFetchTopFiles,
  fetchTopLinks: mockFetchTopLinks,
  fetchDepartments: mockFetchDepartments,
}))

vi.mock('../../src/api/userAttributeMappings', () => ({
  fetchAttributeMappings: mockFetchAttributeMappings,
  discoverAttributes: mockDiscoverAttributes,
}))

vi.mock('../../src/api/links', () => ({
  fetchLinks: mockFetchLinks,
}))

vi.mock('../../src/api/index', () => ({ api: mockApi }))

vi.mock('../../src/api/emailOutbox', () => ({
  fetchEmailOutbox: mockFetchEmailOutbox,
  fetchEmailOutboxItem: mockFetchEmailOutboxItem,
  retryEmailOutboxItem: mockRetryEmailOutboxItem,
  cancelEmailOutboxItem: mockCancelEmailOutboxItem,
}))

const _capturedQueries: any[] = []
const _capturedMutations: any[] = []
const mockInvalidate = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    _capturedQueries.push(opts)
    return { data: { value: undefined }, isLoading: { value: false } }
  }),
  useMutation: vi.fn((opts: any) => {
    _capturedMutations.push(opts)
    return { mutateAsync: vi.fn(), isPending: { value: false } }
  }),
  useQueryClient: vi.fn(() => ({ invalidateQueries: mockInvalidate })),
}))

function resolveKey(k: unknown): unknown {
  if (isRef(k)) return resolveKey(k.value)
  return k
}

describe('src/queries/admin', () => {
  beforeEach(() => {
    _capturedQueries.length = 0
    _capturedMutations.length = 0
    vi.clearAllMocks()
  })

  describe('useAdminUsersQuery', () => {
    it('registers a query', async () => {
      const { useAdminUsersQuery } = await import('../../src/queries/admin')
      useAdminUsersQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchUsers with params', async () => {
      const { useAdminUsersQuery } = await import('../../src/queries/admin')
      useAdminUsersQuery({ q: 'search', page: 2 })
      mockFetchUsers.mockResolvedValueOnce({ items: [], total: 0 })
      await _capturedQueries[0].queryFn()
      expect(mockFetchUsers).toHaveBeenCalledWith({ q: 'search', page: 2 })
    })

    it('queryKey contains admin namespace', async () => {
      const { useAdminUsersQuery } = await import('../../src/queries/admin')
      useAdminUsersQuery()
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('admin')
    })
  })

  describe('useAuditEventTypesQuery', () => {
    it('queryFn calls fetchAuditEventTypes', async () => {
      const { useAuditEventTypesQuery } = await import('../../src/queries/admin')
      useAuditEventTypesQuery()
      mockFetchAuditEventTypes.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchAuditEventTypes).toHaveBeenCalled()
    })
  })

  describe('useAuditQueueQuery', () => {
    it('queryFn calls fetchAuditQueueDepth', async () => {
      const { useAuditQueueQuery } = await import('../../src/queries/admin')
      useAuditQueueQuery()
      mockFetchAuditQueueDepth.mockResolvedValueOnce({ depth: 0 })
      await _capturedQueries[0].queryFn()
      expect(mockFetchAuditQueueDepth).toHaveBeenCalled()
    })
  })

  describe('useAuditEventsQuery', () => {
    it('queryFn calls fetchAuditEvents with filters', async () => {
      const { useAuditEventsQuery } = await import('../../src/queries/admin')
      useAuditEventsQuery({ event_type: 'login' })
      mockFetchAuditEvents.mockResolvedValueOnce({ items: [], total: 0 })
      await _capturedQueries[0].queryFn()
      expect(mockFetchAuditEvents).toHaveBeenCalledWith({ event_type: 'login' })
    })
  })

  describe('useAnalyticsDashboardQuery', () => {
    it('queryFn calls fetchDashboard', async () => {
      const { useAnalyticsDashboardQuery } = await import('../../src/queries/admin')
      useAnalyticsDashboardQuery()
      mockFetchDashboard.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockFetchDashboard).toHaveBeenCalled()
    })
  })

  describe('useAnalyticsTopArticlesQuery', () => {
    it('queryFn calls fetchTopArticles with 30 days and 10 items', async () => {
      const { useAnalyticsTopArticlesQuery } = await import('../../src/queries/admin')
      useAnalyticsTopArticlesQuery()
      mockFetchTopArticles.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchTopArticles).toHaveBeenCalledWith(30, 10)
    })
  })

  describe('useAnalyticsTopNewsQuery', () => {
    it('queryFn calls fetchTopNews with 30 days and 10 items', async () => {
      const { useAnalyticsTopNewsQuery } = await import('../../src/queries/admin')
      useAnalyticsTopNewsQuery()
      mockFetchTopNews.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchTopNews).toHaveBeenCalledWith(30, 10)
    })
  })

  describe('useAnalyticsTopFilesQuery', () => {
    it('queryFn calls fetchTopFiles with 30 days and 10 items', async () => {
      const { useAnalyticsTopFilesQuery } = await import('../../src/queries/admin')
      useAnalyticsTopFilesQuery()
      mockFetchTopFiles.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchTopFiles).toHaveBeenCalledWith(30, 10)
    })
  })

  describe('useAnalyticsTopLinksQuery', () => {
    it('queryFn calls fetchTopLinks with 30 days and 10 items', async () => {
      const { useAnalyticsTopLinksQuery } = await import('../../src/queries/admin')
      useAnalyticsTopLinksQuery()
      mockFetchTopLinks.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchTopLinks).toHaveBeenCalledWith(30, 10)
    })
  })

  describe('useAnalyticsDepartmentsQuery', () => {
    it('queryFn calls fetchDepartments with 30 items', async () => {
      const { useAnalyticsDepartmentsQuery } = await import('../../src/queries/admin')
      useAnalyticsDepartmentsQuery()
      mockFetchDepartments.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchDepartments).toHaveBeenCalledWith(30)
    })
  })

  describe('useEmailSettingsQuery', () => {
    it('queryFn calls api with /admin/email-settings', async () => {
      const { useEmailSettingsQuery } = await import('../../src/queries/admin')
      useEmailSettingsQuery()
      mockApi.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockApi).toHaveBeenCalledWith('/admin/email-settings')
    })
  })

  describe('useSystemSettingsQuery', () => {
    it('queryFn calls api with /admin/system/settings', async () => {
      const { useSystemSettingsQuery } = await import('../../src/queries/admin')
      useSystemSettingsQuery()
      mockApi.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockApi).toHaveBeenCalledWith('/admin/system/settings')
    })
  })

  describe('useTlsStatusQuery', () => {
    it('queryFn calls api with /admin/system/tls/status', async () => {
      const { useTlsStatusQuery } = await import('../../src/queries/admin')
      useTlsStatusQuery()
      mockApi.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockApi).toHaveBeenCalledWith('/admin/system/tls/status')
    })
  })

  describe('useKeycloakSettingsQuery', () => {
    it('queryFn calls api with /admin/keycloak/settings', async () => {
      const { useKeycloakSettingsQuery } = await import('../../src/queries/admin')
      useKeycloakSettingsQuery()
      mockApi.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockApi).toHaveBeenCalledWith('/admin/keycloak/settings')
    })
  })

  describe('useKeycloakSyncStatusQuery', () => {
    it('queryFn calls api with /admin/keycloak/sync/status', async () => {
      const { useKeycloakSyncStatusQuery } = await import('../../src/queries/admin')
      useKeycloakSyncStatusQuery()
      mockApi.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockApi).toHaveBeenCalledWith('/admin/keycloak/sync/status')
    })
  })

  describe('useModulesAdminQuery', () => {
    it('queryFn calls api with /admin/modules', async () => {
      const { useModulesAdminQuery } = await import('../../src/queries/admin')
      useModulesAdminQuery()
      mockApi.mockResolvedValueOnce({})
      await _capturedQueries[0].queryFn()
      expect(mockApi).toHaveBeenCalledWith('/admin/modules')
    })
  })

  describe('useUserAttributeMappingsQuery', () => {
    it('queryFn calls fetchAttributeMappings', async () => {
      const { useUserAttributeMappingsQuery } = await import('../../src/queries/admin')
      useUserAttributeMappingsQuery()
      mockFetchAttributeMappings.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchAttributeMappings).toHaveBeenCalled()
    })
  })

  describe('useDiscoverAttributesQuery', () => {
    it('queryFn calls discoverAttributes', async () => {
      const { useDiscoverAttributesQuery } = await import('../../src/queries/admin')
      useDiscoverAttributesQuery()
      mockDiscoverAttributes.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockDiscoverAttributes).toHaveBeenCalled()
    })
  })

  describe('useAdminLinksQuery', () => {
    it('queryFn calls fetchLinks with include_inactive=true', async () => {
      const { useAdminLinksQuery } = await import('../../src/queries/admin')
      useAdminLinksQuery()
      mockFetchLinks.mockResolvedValueOnce({ items: [] })
      await _capturedQueries[0].queryFn()
      expect(mockFetchLinks).toHaveBeenCalledWith({ include_inactive: true })
    })

    it('queryKey contains admin.links key', async () => {
      const { useAdminLinksQuery } = await import('../../src/queries/admin')
      useAdminLinksQuery()
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('admin')
    })
  })

  describe('useInvalidateAdminLinks', () => {
    it('returns a function that invalidates admin links', async () => {
      const { useInvalidateAdminLinks } = await import('../../src/queries/admin')
      const invalidate = useInvalidateAdminLinks()
      expect(typeof invalidate).toBe('function')
      await invalidate()
      expect(mockInvalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: expect.anything() }),
      )
    })
  })

  describe('useEmailOutboxQuery', () => {
    it('queryFn calls fetchEmailOutbox with filters', async () => {
      const { useEmailOutboxQuery } = await import('../../src/queries/admin')
      useEmailOutboxQuery({ status: 'DLQ', limit: 50, offset: 0 })
      mockFetchEmailOutbox.mockResolvedValueOnce({ items: [], total: 0 })
      await _capturedQueries[0].queryFn()
      expect(mockFetchEmailOutbox).toHaveBeenCalledWith({ status: 'DLQ', limit: 50, offset: 0 })
    })

    it('queryKey contains email-outbox namespace', async () => {
      const { useEmailOutboxQuery } = await import('../../src/queries/admin')
      useEmailOutboxQuery({ limit: 50, offset: 0 })
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('email-outbox')
    })
  })

  describe('useEmailOutboxItemQuery', () => {
    it('queryFn calls fetchEmailOutboxItem with id', async () => {
      const { useEmailOutboxItemQuery } = await import('../../src/queries/admin')
      useEmailOutboxItemQuery('abc')
      mockFetchEmailOutboxItem.mockResolvedValueOnce({ id: 'abc' })
      await _capturedQueries[0].queryFn()
      expect(mockFetchEmailOutboxItem).toHaveBeenCalledWith('abc')
    })

    it('is disabled when id is null', async () => {
      const { useEmailOutboxItemQuery } = await import('../../src/queries/admin')
      useEmailOutboxItemQuery(null)
      expect(resolveKey(_capturedQueries[0].enabled)).toBe(false)
    })

    it('is enabled when id is set', async () => {
      const { useEmailOutboxItemQuery } = await import('../../src/queries/admin')
      useEmailOutboxItemQuery('xyz')
      expect(resolveKey(_capturedQueries[0].enabled)).toBe(true)
    })
  })

  describe('useRetryEmailOutboxMutation', () => {
    it('mutationFn calls retryEmailOutboxItem with reset_attempts=true', async () => {
      const { useRetryEmailOutboxMutation } = await import('../../src/queries/admin')
      useRetryEmailOutboxMutation()
      mockRetryEmailOutboxItem.mockResolvedValueOnce({ detail: 'ok' })
      await _capturedMutations[0].mutationFn('id1')
      expect(mockRetryEmailOutboxItem).toHaveBeenCalledWith('id1', true)
    })

    it('onSuccess invalidates the email-outbox list', async () => {
      const { useRetryEmailOutboxMutation } = await import('../../src/queries/admin')
      useRetryEmailOutboxMutation()
      _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalledWith({ queryKey: ['admin', 'email-outbox'] })
    })
  })

  describe('useCancelEmailOutboxMutation', () => {
    it('mutationFn calls cancelEmailOutboxItem', async () => {
      const { useCancelEmailOutboxMutation } = await import('../../src/queries/admin')
      useCancelEmailOutboxMutation()
      mockCancelEmailOutboxItem.mockResolvedValueOnce({ detail: 'ok' })
      await _capturedMutations[0].mutationFn('id2')
      expect(mockCancelEmailOutboxItem).toHaveBeenCalledWith('id2')
    })

    it('onSuccess invalidates the email-outbox list', async () => {
      const { useCancelEmailOutboxMutation } = await import('../../src/queries/admin')
      useCancelEmailOutboxMutation()
      _capturedMutations[0].onSuccess()
      expect(mockInvalidate).toHaveBeenCalledWith({ queryKey: ['admin', 'email-outbox'] })
    })
  })
})
