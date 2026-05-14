import { ref as vRef, isRef } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const mockFetchFolderTree = vi.fn()
const mockFetchFolderDetail = vi.fn()
const mockCreateFolder = vi.fn()
const mockDeleteFolder = vi.fn()
const mockSyncFromNextcloud = vi.fn()

vi.mock('../../src/api/files', () => ({
  fetchFolderTree: mockFetchFolderTree,
  fetchFolderDetail: mockFetchFolderDetail,
  createFolder: mockCreateFolder,
  deleteFolder: mockDeleteFolder,
  syncFromNextcloud: mockSyncFromNextcloud,
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({ isAdmin: false }),
}))

interface MockQuery {
  keyArr: unknown[]
  queryFn: () => Promise<unknown>
  data: ReturnType<typeof vRef>
  isLoading: ReturnType<typeof vRef>
}

const _queries: MockQuery[] = []
const _mockQcInvalidate = vi.fn()
const _mockQcRemove = vi.fn()

function resolveKey(k: unknown): unknown[] {
  if (isRef(k)) return resolveKey(k.value)
  if (Array.isArray(k)) return k
  return [k]
}

function keyStartsWith(full: unknown[], prefix: unknown[]) {
  return prefix.every((v, i) => JSON.stringify(full[i]) === JSON.stringify(v))
}

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    const data = vRef<any>(undefined)
    const isLoading = vRef(false)
    _queries.push({ keyArr: opts.queryKey, queryFn: opts.queryFn, data, isLoading })
    return { data, isLoading }
  }),
  useMutation: vi.fn(({ mutationFn, onSuccess }: any) => {
    const isPending = vRef(false)
    return {
      mutateAsync: vi.fn(async (...args: any[]) => {
        isPending.value = true
        try {
          const result = await mutationFn(...args)
          if (onSuccess) await onSuccess(result, ...args)
          return result
        } finally {
          isPending.value = false
        }
      }),
      isPending,
    }
  }),
  useQueryClient: vi.fn(() => ({
    invalidateQueries: _mockQcInvalidate,
    removeQueries: _mockQcRemove,
  })),
}))

describe('useFilesData', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    _queries.length = 0
    _mockQcInvalidate.mockImplementation(async ({ queryKey }: any) => {
      const prefix = resolveKey(queryKey)
      for (const q of _queries) {
        if (keyStartsWith(resolveKey(q.keyArr), prefix)) {
          q.isLoading.value = true
          try {
            q.data.value = await q.queryFn()
          } catch (e) {
            q.isLoading.value = false
            throw e
          }
          q.isLoading.value = false
        }
      }
    })
  })

  describe('initial state', () => {
    it('tree is empty array', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      const store = useFilesData()
      expect(store.tree).toEqual([])
    })

    it('selectedFolderId is null', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      const store = useFilesData()
      expect(store.selectedFolderId).toBeNull()
    })

    it('loadingTree is false', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      const store = useFilesData()
      expect(store.loadingTree).toBe(false)
    })
  })

  describe('loadTree()', () => {
    it('populates tree on success', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      const nodes = [{ id: '1', name: 'Root', nc_path: '/root', parent_id: null, permission: null, children: [] }]
      mockFetchFolderTree.mockResolvedValueOnce({ items: nodes })

      const store = useFilesData()
      await store.loadTree()

      expect(store.tree).toEqual(nodes)
      expect(store.loadingTree).toBe(false)
    })

    it('resets loadingTree to false on error', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      mockFetchFolderTree.mockRejectedValueOnce(new Error('network'))

      const store = useFilesData()
      await expect(store.loadTree()).rejects.toThrow()
      expect(store.loadingTree).toBe(false)
    })
  })

  describe('loadDetail()', () => {
    it('updates currentFolder, ncItems, breadcrumbs on success', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      const folder = { id: 'f1', name: 'Docs', nc_path: '/docs', parent_id: null, permission: 'editor', children_count: 0, created_at: '', updated_at: '' }
      const items = [{ name: 'file.txt', nc_path: '/docs/file.txt', is_dir: false, size_bytes: 100, mime_type: null, last_modified: null, etag: null, uploaded_at: null, uploaded_by: null }]
      const breadcrumbs = [folder]
      mockFetchFolderDetail.mockResolvedValueOnce({ folder, items, breadcrumbs })

      const store = useFilesData()
      store.selectFolder('f1')
      await store.loadDetail('f1')

      expect(store.currentFolder).toEqual(folder)
      expect(store.ncItems).toEqual(items)
      expect(store.breadcrumbs).toEqual(breadcrumbs)
      expect(store.loadingDetail).toBe(false)
    })

    it('resets loadingDetail to false on error', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      mockFetchFolderDetail.mockRejectedValueOnce(new Error('fail'))

      const store = useFilesData()
      store.selectFolder('x')
      await expect(store.loadDetail('x')).rejects.toThrow()
      expect(store.loadingDetail).toBe(false)
    })
  })

  describe('selectFolder()', () => {
    it('sets selectedFolderId', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      const store = useFilesData()
      store.selectFolder('abc')
      expect(store.selectedFolderId).toBe('abc')
    })

    it('can be set to null', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      const store = useFilesData()
      store.selectFolder('abc')
      store.selectFolder(null)
      expect(store.selectedFolderId).toBeNull()
    })
  })

  describe('deleteFolder()', () => {
    it('clears selectedFolderId if deleted folder was selected', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      mockDeleteFolder.mockResolvedValueOnce(undefined)
      mockFetchFolderTree.mockResolvedValueOnce({ items: [] })

      const store = useFilesData()
      store.selectFolder('del-id')
      await store.deleteFolder('del-id')

      expect(store.selectedFolderId).toBeNull()
    })

    it('does not clear selectedFolderId when a different folder is deleted', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      mockDeleteFolder.mockResolvedValueOnce(undefined)
      mockFetchFolderTree.mockResolvedValueOnce({ items: [] })

      const store = useFilesData()
      store.selectFolder('other-id')
      await store.deleteFolder('del-id')

      expect(store.selectedFolderId).toBe('other-id')
    })
  })

  describe('findNodeById()', () => {
    it('finds a node by id in nested tree', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      const child = { id: 'c1', name: 'Child', nc_path: '/r/c', parent_id: 'r1', permission: null, children: [] }
      const root = { id: 'r1', name: 'Root', nc_path: '/r', parent_id: null, permission: null, children: [child] }
      mockFetchFolderTree.mockResolvedValueOnce({ items: [root] })

      const store = useFilesData()
      await store.loadTree()

      expect(store.findNodeById('c1')).toEqual(child)
      expect(store.findNodeById('missing')).toBeNull()
    })
  })

  describe('syncFromNextcloud()', () => {
    it('returns sync report and calls loadTree', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      const report = { created: 3, skipped: 1, errors: [] }
      mockSyncFromNextcloud.mockResolvedValueOnce(report)
      mockFetchFolderTree.mockResolvedValueOnce({ items: [] })

      const store = useFilesData()
      const result = await store.syncFromNextcloud()

      expect(result).toEqual(report)
      expect(mockFetchFolderTree).toHaveBeenCalledTimes(1)
      expect(store.syncing).toBe(false)
    })

    it('resets syncing to false on error', async () => {
      const { useFilesData } = await import('../../src/composables/useFilesData')
      mockSyncFromNextcloud.mockRejectedValueOnce(new Error('sync failed'))

      const store = useFilesData()
      await expect(store.syncFromNextcloud()).rejects.toThrow()
      expect(store.syncing).toBe(false)
    })
  })
})
