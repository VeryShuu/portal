import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const mockApi = vi.fn()
const mockApiUpload = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: mockApi,
  apiUpload: mockApiUpload,
  BASE_URL: '/api/v1',
}))

describe('src/api/audit', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('fetchAuditEvents calls api with filters', async () => {
    const { fetchAuditEvents } = await import('../../src/api/audit')
    mockApi.mockResolvedValueOnce({ items: [], total: 0, limit: 20, offset: 0 })
    await fetchAuditEvents({ event_type: 'login', user_id: 'u1' })
    expect(mockApi).toHaveBeenCalledWith('/audit', {
      query: { event_type: 'login', user_id: 'u1' },
    })
  })

  it('fetchAuditEvents omits empty/null/undefined filters', async () => {
    const { fetchAuditEvents } = await import('../../src/api/audit')
    mockApi.mockResolvedValueOnce({ items: [], total: 0, limit: 20, offset: 0 })
    await fetchAuditEvents({ event_type: '', user_id: undefined, q: 'test' })
    const call = mockApi.mock.calls[0]
    expect(call[1].query).not.toHaveProperty('event_type')
    expect(call[1].query).not.toHaveProperty('user_id')
    expect(call[1].query).toHaveProperty('q', 'test')
  })

  it('fetchAuditEvents with no args calls api with empty query', async () => {
    const { fetchAuditEvents } = await import('../../src/api/audit')
    mockApi.mockResolvedValueOnce({ items: [], total: 0, limit: 20, offset: 0 })
    await fetchAuditEvents()
    expect(mockApi).toHaveBeenCalledWith('/audit', { query: {} })
  })

  it('fetchAuditEventTypes calls api', async () => {
    const { fetchAuditEventTypes } = await import('../../src/api/audit')
    mockApi.mockResolvedValueOnce([])
    await fetchAuditEventTypes()
    expect(mockApi).toHaveBeenCalledWith('/audit/event-types')
  })

  it('fetchAuditQueueDepth calls api', async () => {
    const { fetchAuditQueueDepth } = await import('../../src/api/audit')
    mockApi.mockResolvedValueOnce({ pending: 0, processing: 0 })
    await fetchAuditQueueDepth()
    expect(mockApi).toHaveBeenCalledWith('/audit/queue/depth')
  })

  it('buildAuditCsvUrl returns base url when no filters', async () => {
    const { buildAuditCsvUrl } = await import('../../src/api/audit')
    const url = buildAuditCsvUrl()
    expect(url).toContain('/audit/export.csv')
    expect(url).not.toContain('?')
  })

  it('buildAuditCsvUrl includes non-empty filters', async () => {
    const { buildAuditCsvUrl } = await import('../../src/api/audit')
    const url = buildAuditCsvUrl({ event_type: 'login', q: 'test' })
    expect(url).toContain('event_type=login')
    expect(url).toContain('q=test')
  })

  it('buildAuditCsvUrl omits empty filters', async () => {
    const { buildAuditCsvUrl } = await import('../../src/api/audit')
    const url = buildAuditCsvUrl({ event_type: '', user_id: undefined })
    expect(url).not.toContain('event_type')
  })
})

describe('src/api/analytics', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('fetchDashboard calls api', async () => {
    const { fetchDashboard } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce({})
    await fetchDashboard()
    expect(mockApi).toHaveBeenCalledWith('/analytics/dashboard', expect.objectContaining({}))
  })

  it('fetchDashboard passes signal', async () => {
    const { fetchDashboard } = await import('../../src/api/analytics')
    const signal = new AbortController().signal
    mockApi.mockResolvedValueOnce({})
    await fetchDashboard(14, { signal })
    expect(mockApi).toHaveBeenCalledWith('/analytics/dashboard', expect.objectContaining({ signal }))
  })

  it('fetchTopArticles calls api with defaults', async () => {
    const { fetchTopArticles } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce([])
    await fetchTopArticles()
    expect(mockApi).toHaveBeenCalledWith('/analytics/top-articles', expect.objectContaining({
      query: { days: 30, limit: 20 },
    }))
  })

  it('fetchTopArticles passes custom params', async () => {
    const { fetchTopArticles } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce([])
    await fetchTopArticles(7, 5)
    expect(mockApi).toHaveBeenCalledWith('/analytics/top-articles', expect.objectContaining({
      query: { days: 7, limit: 5 },
    }))
  })

  it('fetchTopNews calls api', async () => {
    const { fetchTopNews } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce([])
    await fetchTopNews(14, 10)
    expect(mockApi).toHaveBeenCalledWith('/analytics/top-news', expect.objectContaining({
      query: { days: 14, limit: 10 },
    }))
  })

  it('fetchTopFiles calls api', async () => {
    const { fetchTopFiles } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce([])
    await fetchTopFiles()
    expect(mockApi).toHaveBeenCalledWith('/analytics/top-files', expect.objectContaining({
      query: { days: 30, limit: 20 },
    }))
  })

  it('fetchDepartments calls api', async () => {
    const { fetchDepartments } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce([])
    await fetchDepartments(30)
    expect(mockApi).toHaveBeenCalledWith('/analytics/departments', expect.objectContaining({
      query: { days: 30 },
    }))
  })

  it('fetchTopLinks calls api', async () => {
    const { fetchTopLinks } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce([])
    await fetchTopLinks(7, 5)
    expect(mockApi).toHaveBeenCalledWith('/analytics/top-links', expect.objectContaining({
      query: { days: 7, limit: 5 },
    }))
  })

  it('fetchStaleContent calls api with defaults', async () => {
    const { fetchStaleContent } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce([])
    await fetchStaleContent()
    expect(mockApi).toHaveBeenCalledWith('/analytics/stale-content', expect.objectContaining({
      query: { days: 90, limit: 20 },
    }))
  })

  it('fetchFeedbackStats calls api', async () => {
    const { fetchFeedbackStats } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce({})
    await fetchFeedbackStats(30)
    expect(mockApi).toHaveBeenCalledWith('/analytics/feedback', expect.objectContaining({
      query: { days: 30 },
    }))
  })

  it('fetchResourceTrend calls api with resource_id/kind/days', async () => {
    const { fetchResourceTrend } = await import('../../src/api/analytics')
    mockApi.mockResolvedValueOnce([])
    await fetchResourceTrend('res-1', 'file', 14)
    expect(mockApi).toHaveBeenCalledWith('/analytics/resource-trend', expect.objectContaining({
      query: { resource_id: 'res-1', kind: 'file', days: 14 },
    }))
  })

  it('analyticsExportUrl builds a download url', async () => {
    const { analyticsExportUrl } = await import('../../src/api/analytics')
    const url = analyticsExportUrl('top-links', 'xlsx', 7, 50)
    expect(url).toContain('/api/v1/analytics/export?')
    expect(url).toContain('dataset=top-links')
    expect(url).toContain('format=xlsx')
    expect(url).toContain('days=7')
    expect(url).toContain('limit=50')
  })
})

describe('src/api/userAttributeMappings', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('fetchAttributeSchema calls api', async () => {
    const { fetchAttributeSchema } = await import('../../src/api/userAttributeMappings')
    mockApi.mockResolvedValueOnce({ items: [] })
    await fetchAttributeSchema()
    expect(mockApi).toHaveBeenCalledWith('/user-attribute-mappings/schema')
  })

  it('fetchAttributeMappings calls api', async () => {
    const { fetchAttributeMappings } = await import('../../src/api/userAttributeMappings')
    mockApi.mockResolvedValueOnce({ items: [], total: 0 })
    await fetchAttributeMappings()
    expect(mockApi).toHaveBeenCalledWith('/user-attribute-mappings')
  })

  it('discoverAttributes calls api', async () => {
    const { discoverAttributes } = await import('../../src/api/userAttributeMappings')
    mockApi.mockResolvedValueOnce({ items: [] })
    await discoverAttributes()
    expect(mockApi).toHaveBeenCalledWith('/user-attribute-mappings/discover')
  })

  it('createAttributeMapping calls api with POST', async () => {
    const { createAttributeMapping } = await import('../../src/api/userAttributeMappings')
    const dto = { attr_key: 'phone', label_ru: 'Телефон' }
    mockApi.mockResolvedValueOnce({ id: '1', ...dto })
    await createAttributeMapping(dto)
    expect(mockApi).toHaveBeenCalledWith('/user-attribute-mappings', {
      method: 'POST',
      body: dto,
    })
  })

  it('updateAttributeMapping calls api with PUT', async () => {
    const { updateAttributeMapping } = await import('../../src/api/userAttributeMappings')
    const dto = { label_ru: 'Обновлено' }
    mockApi.mockResolvedValueOnce({ id: 'attr-1' })
    await updateAttributeMapping('attr-1', dto)
    expect(mockApi).toHaveBeenCalledWith('/user-attribute-mappings/attr-1', {
      method: 'PUT',
      body: dto,
    })
  })

  it('deleteAttributeMapping calls api with DELETE', async () => {
    const { deleteAttributeMapping } = await import('../../src/api/userAttributeMappings')
    mockApi.mockResolvedValueOnce(undefined)
    await deleteAttributeMapping('attr-1')
    expect(mockApi).toHaveBeenCalledWith('/user-attribute-mappings/attr-1', { method: 'DELETE' })
  })
})

describe('src/api/users (extended)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('fetchUsers calls api with params', async () => {
    const { fetchUsers } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce({ items: [], total: 0 })
    await fetchUsers({ q: 'ivan', page: 1 })
    expect(mockApi).toHaveBeenCalledWith('/users', {
      params: { q: 'ivan', page: 1 },
      signal: undefined,
    })
  })

  it('fetchUsers passes signal', async () => {
    const { fetchUsers } = await import('../../src/api/users')
    const signal = new AbortController().signal
    mockApi.mockResolvedValueOnce({ items: [], total: 0 })
    await fetchUsers({}, { signal })
    expect(mockApi).toHaveBeenCalledWith('/users', expect.objectContaining({ signal }))
  })

  it('fetchUserDepartments calls api', async () => {
    const { fetchUserDepartments } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce({ items: [] })
    await fetchUserDepartments({ ordered: true })
    expect(mockApi).toHaveBeenCalledWith('/users/departments', { params: { ordered: true } })
  })

  it('fetchUserOffices calls api', async () => {
    const { fetchUserOffices } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce({ items: [] })
    await fetchUserOffices()
    expect(mockApi).toHaveBeenCalledWith('/users/offices')
  })

  it('fetchUserById calls api', async () => {
    const { fetchUserById } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce({ id: 'u1' })
    await fetchUserById('u1')
    expect(mockApi).toHaveBeenCalledWith('/users/u1')
  })

  it('patchMyProfile calls api with PATCH', async () => {
    const { patchMyProfile } = await import('../../src/api/users')
    const dto = { presence_status: 'remote' as const }
    mockApi.mockResolvedValueOnce({ id: 'me' })
    await patchMyProfile(dto)
    expect(mockApi).toHaveBeenCalledWith('/users/me/profile', { method: 'PATCH', body: dto })
  })

  it('patchMyPreferences calls api with PATCH', async () => {
    const { patchMyPreferences } = await import('../../src/api/users')
    const dto = { onboarding_completed: true }
    mockApi.mockResolvedValueOnce({ id: 'me' })
    await patchMyPreferences(dto)
    expect(mockApi).toHaveBeenCalledWith('/users/me/preferences', { method: 'PATCH', body: dto })
  })

  it('uploadAvatar calls apiUpload', async () => {
    const { uploadAvatar } = await import('../../src/api/users')
    const file = new File([''], 'avatar.jpg', { type: 'image/jpeg' })
    mockApiUpload.mockResolvedValueOnce({ id: 'me' })
    await uploadAvatar(file)
    expect(mockApiUpload).toHaveBeenCalledWith('/users/me/avatar', expect.any(FormData))
  })

  it('changeUserRole calls api with PATCH', async () => {
    const { changeUserRole } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce({ id: 'u1', role: 'editor' })
    await changeUserRole('u1', 'editor')
    expect(mockApi).toHaveBeenCalledWith('/users/admin/u1/role', {
      method: 'PATCH',
      body: { role: 'editor' },
    })
  })

  it('syncUsersFromKeycloak calls api with POST', async () => {
    const { syncUsersFromKeycloak } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce({ job_id: null, status: 'ok' })
    await syncUsersFromKeycloak()
    expect(mockApi).toHaveBeenCalledWith('/users/admin/sync', { method: 'POST' })
  })

  it('adminCreateLocalUser calls api with POST', async () => {
    const { adminCreateLocalUser } = await import('../../src/api/users')
    const dto = { email: 'test@test.com', full_name: 'Test', password: 'pass', role: 'reader' as const }
    mockApi.mockResolvedValueOnce({ id: 'new-u' })
    await adminCreateLocalUser(dto)
    expect(mockApi).toHaveBeenCalledWith('/users/admin/local', { method: 'POST', body: dto })
  })

  it('adminPatchUserProfile calls api with PATCH', async () => {
    const { adminPatchUserProfile } = await import('../../src/api/users')
    const dto = { full_name: 'Updated Name' }
    mockApi.mockResolvedValueOnce({ id: 'u1' })
    await adminPatchUserProfile('u1', dto)
    expect(mockApi).toHaveBeenCalledWith('/users/admin/u1/profile', { method: 'PATCH', body: dto })
  })

  it('adminResetUserPassword calls api with PATCH', async () => {
    const { adminResetUserPassword } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce(undefined)
    await adminResetUserPassword('u1', 'newpass123')
    expect(mockApi).toHaveBeenCalledWith('/users/admin/u1/password', {
      method: 'PATCH',
      body: { new_password: 'newpass123' },
    })
  })

  it('adminDeleteUser calls api with DELETE', async () => {
    const { adminDeleteUser } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce(undefined)
    await adminDeleteUser('u1')
    expect(mockApi).toHaveBeenCalledWith('/users/admin/u1', { method: 'DELETE' })
  })

  it('adminFetchUserKeycloakGroups calls api', async () => {
    const { adminFetchUserKeycloakGroups } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce({ groups: [] })
    await adminFetchUserKeycloakGroups('u1')
    expect(mockApi).toHaveBeenCalledWith('/users/admin/u1/groups')
  })

  it('fetchStaffOrder calls api', async () => {
    const { fetchStaffOrder } = await import('../../src/api/users')
    mockApi.mockResolvedValueOnce({ departments: [], hidden_user_ids: [] })
    await fetchStaffOrder()
    expect(mockApi).toHaveBeenCalledWith('/users/admin/staff-order')
  })

  it('saveStaffOrder calls api with PUT', async () => {
    const { saveStaffOrder } = await import('../../src/api/users')
    const body = { departments: [], users: [], hidden_user_ids: [] }
    mockApi.mockResolvedValueOnce({ departments: [], hidden_user_ids: [] })
    await saveStaffOrder(body)
    expect(mockApi).toHaveBeenCalledWith('/users/admin/staff-order', { method: 'PUT', body })
  })
})

describe('src/stores/layout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('headerText is empty string by default', async () => {
    const { useLayoutStore } = await import('../../src/stores/layout')
    const store = useLayoutStore()
    expect(store.headerText).toBe('')
  })

  it('setHeader sets headerText', async () => {
    const { useLayoutStore } = await import('../../src/stores/layout')
    const store = useLayoutStore()
    store.setHeader('My Page')
    expect(store.headerText).toBe('My Page')
  })

  it('clearHeader resets headerText to empty', async () => {
    const { useLayoutStore } = await import('../../src/stores/layout')
    const store = useLayoutStore()
    store.setHeader('Something')
    store.clearHeader()
    expect(store.headerText).toBe('')
  })
})
