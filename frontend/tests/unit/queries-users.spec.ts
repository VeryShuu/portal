import { isRef } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetchUserById = vi.fn()
const mockFetchUsers = vi.fn()
const mockFetchUserDepartments = vi.fn()
const mockFetchUserOffices = vi.fn()
const mockAdminFetchUserKeycloakGroups = vi.fn()
const mockFetchAttributeSchema = vi.fn()
const mockApi = vi.fn()

vi.mock('../../src/api/users', () => ({
  fetchUserById: mockFetchUserById,
  fetchUsers: mockFetchUsers,
  fetchUserDepartments: mockFetchUserDepartments,
  fetchUserOffices: mockFetchUserOffices,
  adminFetchUserKeycloakGroups: mockAdminFetchUserKeycloakGroups,
}))

vi.mock('../../src/api/userAttributeMappings', () => ({
  fetchAttributeSchema: mockFetchAttributeSchema,
}))

vi.mock('../../src/api/index', () => ({ api: mockApi }))

const _capturedQueries: any[] = []

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    _capturedQueries.push(opts)
    return { data: { value: undefined }, isLoading: { value: false } }
  }),
  keepPreviousData: undefined,
}))

function resolveKey(k: unknown): unknown {
  if (isRef(k)) return resolveKey(k.value)
  return k
}

describe('src/queries/users', () => {
  beforeEach(() => {
    _capturedQueries.length = 0
    vi.clearAllMocks()
  })

  describe('useStaffListQuery', () => {
    it('registers a query', async () => {
      const { useStaffListQuery } = await import('../../src/queries/users')
      useStaffListQuery({ q: 'test' })
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchUsers with params and signal', async () => {
      const { useStaffListQuery } = await import('../../src/queries/users')
      useStaffListQuery({ q: 'ivan', page: 1 })
      mockFetchUsers.mockResolvedValueOnce({ items: [], total: 0 })
      const signal = new AbortController().signal
      await _capturedQueries[0].queryFn({ signal })
      expect(mockFetchUsers).toHaveBeenCalledWith({ q: 'ivan', page: 1 }, { signal })
    })

    it('queryKey contains users namespace', async () => {
      const { useStaffListQuery } = await import('../../src/queries/users')
      useStaffListQuery({})
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('users')
    })
  })

  describe('useUserDepartmentsQuery', () => {
    it('registers a query', async () => {
      const { useUserDepartmentsQuery } = await import('../../src/queries/users')
      useUserDepartmentsQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchUserDepartments with ordered=false by default', async () => {
      const { useUserDepartmentsQuery } = await import('../../src/queries/users')
      useUserDepartmentsQuery()
      mockFetchUserDepartments.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchUserDepartments).toHaveBeenCalledWith({ ordered: false })
    })

    it('queryFn calls fetchUserDepartments with ordered=true when specified', async () => {
      const { useUserDepartmentsQuery } = await import('../../src/queries/users')
      useUserDepartmentsQuery({ ordered: true })
      mockFetchUserDepartments.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchUserDepartments).toHaveBeenCalledWith({ ordered: true })
    })
  })

  describe('useUserOfficesQuery', () => {
    it('registers a query', async () => {
      const { useUserOfficesQuery } = await import('../../src/queries/users')
      useUserOfficesQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchUserOffices', async () => {
      const { useUserOfficesQuery } = await import('../../src/queries/users')
      useUserOfficesQuery()
      mockFetchUserOffices.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchUserOffices).toHaveBeenCalled()
    })
  })

  describe('useUserQuery', () => {
    it('registers a query', async () => {
      const { useUserQuery } = await import('../../src/queries/users')
      useUserQuery('user-1')
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchUserById', async () => {
      const { useUserQuery } = await import('../../src/queries/users')
      useUserQuery('user-1')
      mockFetchUserById.mockResolvedValueOnce({ id: 'user-1' })
      await _capturedQueries[0].queryFn()
      expect(mockFetchUserById).toHaveBeenCalledWith('user-1')
    })

    it('queryKey includes user id', async () => {
      const { useUserQuery } = await import('../../src/queries/users')
      useUserQuery('user-abc')
      const key = resolveKey(_capturedQueries[0].queryKey)
      expect(JSON.stringify(key)).toContain('user-abc')
    })

    it('enabled is false when id is empty', async () => {
      const { useUserQuery } = await import('../../src/queries/users')
      useUserQuery('')
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(false)
    })

    it('enabled respects options.enabled=false', async () => {
      const { useUserQuery } = await import('../../src/queries/users')
      useUserQuery('u1', { enabled: false })
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(false)
    })
  })

  describe('useUserAttributeSchemaQuery', () => {
    it('registers a query', async () => {
      const { useUserAttributeSchemaQuery } = await import('../../src/queries/users')
      useUserAttributeSchemaQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls fetchAttributeSchema', async () => {
      const { useUserAttributeSchemaQuery } = await import('../../src/queries/users')
      useUserAttributeSchemaQuery()
      mockFetchAttributeSchema.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockFetchAttributeSchema).toHaveBeenCalled()
    })
  })

  describe('useStaffSettingsQuery', () => {
    it('registers a query', async () => {
      const { useStaffSettingsQuery } = await import('../../src/queries/users')
      useStaffSettingsQuery()
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls api with /portal/staff-settings', async () => {
      const { useStaffSettingsQuery } = await import('../../src/queries/users')
      useStaffSettingsQuery()
      mockApi.mockResolvedValueOnce({ phone_extract_regex: '\\d+' })
      await _capturedQueries[0].queryFn()
      expect(mockApi).toHaveBeenCalledWith('/portal/staff-settings')
    })
  })

  describe('useUserKeycloakGroupsQuery', () => {
    it('registers a query', async () => {
      const { useUserKeycloakGroupsQuery } = await import('../../src/queries/users')
      useUserKeycloakGroupsQuery('u1')
      expect(_capturedQueries).toHaveLength(1)
    })

    it('queryFn calls adminFetchUserKeycloakGroups', async () => {
      const { useUserKeycloakGroupsQuery } = await import('../../src/queries/users')
      useUserKeycloakGroupsQuery('u1')
      mockAdminFetchUserKeycloakGroups.mockResolvedValueOnce([])
      await _capturedQueries[0].queryFn()
      expect(mockAdminFetchUserKeycloakGroups).toHaveBeenCalledWith('u1')
    })

    it('enabled is false when id is empty', async () => {
      const { useUserKeycloakGroupsQuery } = await import('../../src/queries/users')
      useUserKeycloakGroupsQuery('')
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(false)
    })

    it('enabled respects options.enabled=false', async () => {
      const { useUserKeycloakGroupsQuery } = await import('../../src/queries/users')
      useUserKeycloakGroupsQuery('u1', { enabled: false })
      const enabled = resolveKey(_capturedQueries[0].enabled)
      expect(enabled).toBe(false)
    })
  })
})
