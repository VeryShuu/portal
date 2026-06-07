import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, toValue } from 'vue'

const capturedQueries: any[] = []
const capturedMutations: any[] = []
const qc = {
  invalidateQueries: vi.fn(),
  removeQueries: vi.fn(),
  getQueryData: vi.fn(),
  setQueryData: vi.fn(),
}

const apiDirectories = {
  fetchDirectories: vi.fn(),
  createDirectory: vi.fn(),
  updateDirectory: vi.fn(),
  deleteDirectory: vi.fn(),
  fetchEntries: vi.fn(),
  fetchEntry: vi.fn(),
  createEntry: vi.fn(),
  updateEntry: vi.fn(),
  deleteEntry: vi.fn(),
  reorderEntries: vi.fn(),
}

const apiFiles = {
  fetchFolderTree: vi.fn(),
  fetchFolderDetail: vi.fn(),
  createFolder: vi.fn(),
  deleteFolder: vi.fn(),
  syncFromNextcloud: vi.fn(),
  createFileShare: vi.fn(),
  fetchFileShares: vi.fn(),
  revokeFileShare: vi.fn(),
  fetchMyShares: vi.fn(),
  fetchSharedWithMe: vi.fn(),
  fetchAdminShares: vi.fn(),
}

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    capturedQueries.push(opts)
    return { data: ref(undefined), isLoading: ref(false) }
  }),
  useMutation: vi.fn((opts: any) => {
    capturedMutations.push(opts)
    return { mutate: vi.fn() }
  }),
  useQueryClient: vi.fn(() => qc),
}))

vi.mock('../../src/api/directories', () => apiDirectories)
vi.mock('../../src/api/files', () => apiFiles)

describe('src/queries/directories', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    capturedQueries.length = 0
    capturedMutations.length = 0
  })

  it('useDirectoriesQuery registers queryKey/queryFn and enabled branches', async () => {
    const { useDirectoriesQuery } = await import('../../src/queries/directories')

    useDirectoriesQuery()
    expect(capturedQueries).toHaveLength(1)
    expect(capturedQueries[0].queryKey).toEqual(['directories', 'list'])
    expect(toValue(capturedQueries[0].enabled)).toBe(true)

    apiDirectories.fetchDirectories.mockResolvedValueOnce({ items: [], total: 0 })
    await capturedQueries[0].queryFn()
    expect(apiDirectories.fetchDirectories).toHaveBeenCalled()

    useDirectoriesQuery({ enabled: ref(false) })
    expect(toValue(capturedQueries[1].enabled)).toBe(false)
  })

  it('useDirectoryEntriesQuery builds key/fn/placeholder and enabled branches', async () => {
    const { useDirectoryEntriesQuery } = await import('../../src/queries/directories')

    const slug = ref('staff')
    const params = ref({ q: 'ivan', limit: 5 })
    useDirectoryEntriesQuery(slug, params)

    const q = capturedQueries[0]
    expect(toValue(q.queryKey)).toEqual(['directories', 'entries', 'staff', { q: 'ivan', limit: 5 }])
    expect(q.placeholderData({ prev: 1 })).toEqual({ prev: 1 })
    expect(toValue(q.enabled)).toBe(true)

    apiDirectories.fetchEntries.mockResolvedValueOnce({ items: [], total: 0, limit: 5, offset: 0 })
    await q.queryFn()
    expect(apiDirectories.fetchEntries).toHaveBeenCalledWith('staff', { q: 'ivan', limit: 5 })

    useDirectoryEntriesQuery(ref(''), ref({}), { enabled: ref(true) })
    expect(toValue(capturedQueries[1].enabled)).toBe(false)

    useDirectoryEntriesQuery(ref('staff'), ref({}), { enabled: ref(false) })
    expect(toValue(capturedQueries[2].enabled)).toBe(false)
  })

  it('useDirectoryEntryQuery builds key/fn and enabled branch', async () => {
    const { useDirectoryEntryQuery } = await import('../../src/queries/directories')

    useDirectoryEntryQuery(ref('staff'), ref('e1'))
    expect(toValue(capturedQueries[0].queryKey)).toEqual(['directories', 'entry', 'staff', 'e1'])
    expect(toValue(capturedQueries[0].enabled)).toBe(true)

    apiDirectories.fetchEntry.mockResolvedValueOnce({ id: 'e1' })
    await capturedQueries[0].queryFn()
    expect(apiDirectories.fetchEntry).toHaveBeenCalledWith('staff', 'e1')

    useDirectoryEntryQuery(ref(''), ref('e1'))
    expect(toValue(capturedQueries[1].enabled)).toBe(false)
  })

  it('directory mutations call API and invalidate expected keys', async () => {
    const {
      useCreateDirectoryMutation,
      useUpdateDirectoryMutation,
      useDeleteDirectoryMutation,
      useCreateEntryMutation,
      useUpdateEntryMutation,
      useDeleteEntryMutation,
      useReorderEntriesMutation,
    } = await import('../../src/queries/directories')

    useCreateDirectoryMutation()
    await capturedMutations[0].mutationFn({ slug: 'a', label_ru: 'A' })
    expect(apiDirectories.createDirectory).toHaveBeenCalledWith({ slug: 'a', label_ru: 'A' })
    capturedMutations[0].onSuccess()
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['directories', 'list'] })

    useUpdateDirectoryMutation()
    await capturedMutations[1].mutationFn({ id: 'd1', dto: { label_ru: 'B' } })
    expect(apiDirectories.updateDirectory).toHaveBeenCalledWith('d1', { label_ru: 'B' })
    capturedMutations[1].onSuccess()
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['directories'] })

    useDeleteDirectoryMutation()
    await capturedMutations[2].mutationFn('d2')
    expect(apiDirectories.deleteDirectory).toHaveBeenCalledWith('d2')
    capturedMutations[2].onSuccess()
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['directories'] })

    useCreateEntryMutation(ref('staff'))
    await capturedMutations[3].mutationFn({ name: 'N' })
    expect(apiDirectories.createEntry).toHaveBeenCalledWith('staff', { name: 'N' })
    capturedMutations[3].onSuccess()
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['directories', 'entries', 'staff', {}] })

    useUpdateEntryMutation(ref('staff'))
    await capturedMutations[4].mutationFn({ id: 'e1', dto: { name: 'U' } })
    expect(apiDirectories.updateEntry).toHaveBeenCalledWith('staff', 'e1', { name: 'U' })
    capturedMutations[4].onSuccess(undefined, { id: 'e1' })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['directories', 'entry', 'staff', 'e1'] })

    useDeleteEntryMutation(ref('staff'))
    await capturedMutations[5].mutationFn('e2')
    expect(apiDirectories.deleteEntry).toHaveBeenCalledWith('staff', 'e2')
    capturedMutations[5].onSuccess()

    useReorderEntriesMutation(ref('staff'))
    await capturedMutations[6].mutationFn([{ id: 'e1', sort_order: 1 }])
    expect(apiDirectories.reorderEntries).toHaveBeenCalledWith('staff', [{ id: 'e1', sort_order: 1 }])
    capturedMutations[6].onSuccess()

    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['directories', 'entries', 'staff', {}] })
  })
})

describe('src/queries/files', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    capturedQueries.length = 0
    capturedMutations.length = 0
  })

  it('folder tree/detail queries register key/fn/enabled branches', async () => {
    const { useFolderTreeQuery, useFolderDetailQuery } = await import('../../src/queries/files')

    useFolderTreeQuery()
    expect(capturedQueries[0].queryKey).toEqual(['files', 'tree'])
    apiFiles.fetchFolderTree.mockResolvedValueOnce({ items: [] })
    await capturedQueries[0].queryFn()
    expect(apiFiles.fetchFolderTree).toHaveBeenCalled()

    useFolderDetailQuery(ref('f1'))
    expect(toValue(capturedQueries[1].queryKey)).toEqual(['files', 'folder', 'f1'])
    expect(toValue(capturedQueries[1].enabled)).toBe(true)
    apiFiles.fetchFolderDetail.mockResolvedValueOnce({ folder: { id: 'f1' }, items: [], breadcrumbs: [] })
    await capturedQueries[1].queryFn()
    expect(apiFiles.fetchFolderDetail).toHaveBeenCalledWith('f1')

    useFolderDetailQuery(ref(null))
    expect(toValue(capturedQueries[2].enabled)).toBe(false)
  })

  it('file shares queries capture key/fn/enabled and static share queries', async () => {
    const {
      useFileSharesQuery,
      useMyFileSharesQuery,
      useSharedWithMeQuery,
      useAdminSharesQuery,
    } = await import('../../src/queries/files')

    useFileSharesQuery(ref('f1'), ref('a.txt'))
    expect(toValue(capturedQueries[0].queryKey)).toEqual(['files', 'shares', 'file', 'f1', 'a.txt'])
    expect(toValue(capturedQueries[0].enabled)).toBe(true)
    apiFiles.fetchFileShares.mockResolvedValueOnce({ items: [] })
    await capturedQueries[0].queryFn()
    expect(apiFiles.fetchFileShares).toHaveBeenCalledWith('f1', 'a.txt')

    useFileSharesQuery(ref(null), ref('a.txt'))
    expect(toValue(capturedQueries[1].enabled)).toBe(false)

    useMyFileSharesQuery()
    expect(capturedQueries[2].queryKey).toEqual(['files', 'shares', 'my'])
    await capturedQueries[2].queryFn()
    expect(apiFiles.fetchMyShares).toHaveBeenCalled()

    useSharedWithMeQuery()
    expect(capturedQueries[3].queryKey).toEqual(['files', 'shares', 'shared-with-me'])
    await capturedQueries[3].queryFn()
    expect(apiFiles.fetchSharedWithMe).toHaveBeenCalled()

    useAdminSharesQuery(ref({ subject_id: 'u1', limit: 10 }))
    expect(toValue(capturedQueries[4].queryKey)).toEqual(['files', 'shares', 'admin', { subject_id: 'u1', limit: 10 }])
    await capturedQueries[4].queryFn()
    expect(apiFiles.fetchAdminShares).toHaveBeenCalledWith({ subject_id: 'u1', limit: 10 })
  })

  it('file mutations call API and invalidate/remove expected keys', async () => {
    const {
      useCreateFolderMutation,
      useDeleteFolderMutation,
      useSyncFromNcMutation,
      useCreateFileShareMutation,
      useRevokeFileShareMutation,
    } = await import('../../src/queries/files')

    useCreateFolderMutation()
    await capturedMutations[0].mutationFn({ name: 'N', parent_id: null, description: null })
    expect(apiFiles.createFolder).toHaveBeenCalledWith({ name: 'N', parent_id: null, description: null })
    capturedMutations[0].onSuccess()
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['files', 'tree'] })

    useDeleteFolderMutation()
    await capturedMutations[1].mutationFn('f1')
    expect(apiFiles.deleteFolder).toHaveBeenCalledWith('f1')
    capturedMutations[1].onSuccess(undefined, 'f1')
    expect(qc.removeQueries).toHaveBeenCalledWith({ queryKey: ['files', 'folder', 'f1'] })

    useSyncFromNcMutation()
    await capturedMutations[2].mutationFn()
    expect(apiFiles.syncFromNextcloud).toHaveBeenCalled()
    capturedMutations[2].onSuccess()
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['files'] })

    useCreateFileShareMutation()
    const input = {
      folderId: 'f1',
      filename: 'doc.txt',
      body: {
        subject_type: 'user' as const,
        subject_id: 'u1',
        subject_name: 'U',
        permission: 'viewer' as const,
      },
    }
    await capturedMutations[3].mutationFn(input)
    expect(apiFiles.createFileShare).toHaveBeenCalledWith('f1', 'doc.txt', input.body)
    capturedMutations[3].onSuccess(undefined, input)
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['files', 'shares', 'file', 'f1', 'doc.txt'] })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['files', 'shares', 'my'] })

    useRevokeFileShareMutation()
    const revokeInput = { folderId: 'f1', filename: 'doc.txt', shareId: 's1' }
    await capturedMutations[4].mutationFn(revokeInput)
    expect(apiFiles.revokeFileShare).toHaveBeenCalledWith('f1', 'doc.txt', 's1')
    capturedMutations[4].onSuccess(undefined, revokeInput)
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['files', 'shares', 'file', 'f1', 'doc.txt'] })
  })

  it('useUpdateFolderDetailCache updates only when cached value exists', async () => {
    const { useUpdateFolderDetailCache } = await import('../../src/queries/files')
    const update = useUpdateFolderDetailCache()

    qc.getQueryData.mockReturnValueOnce(undefined)
    update('f1', () => ({ id: 'f1' } as any))
    expect(qc.setQueryData).not.toHaveBeenCalled()

    qc.getQueryData.mockReturnValueOnce({ folder: { id: 'f1', name: 'Old' }, items: [], breadcrumbs: [] })
    update('f1', (prev) => ({ ...prev, name: 'New' } as any))

    expect(qc.setQueryData).toHaveBeenCalledWith(
      ['files', 'folder', 'f1'],
      expect.objectContaining({ folder: expect.objectContaining({ name: 'New' }) }),
    )
  })
})
