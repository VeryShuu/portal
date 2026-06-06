import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

const h = vi.hoisted(() => ({
  msg: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  confirmMock: vi.fn(),
  loadRecent: vi.fn(),
  qc: {
    invalidateQueries: vi.fn().mockResolvedValue(undefined),
    ensureQueryData: vi.fn().mockResolvedValue(undefined),
    setQueryData: vi.fn(),
  },
  refetch: vi.fn().mockResolvedValue(undefined),
  tagsRefetch: vi.fn().mockResolvedValue(undefined),
  api: {
    bulkAction: vi.fn(),
    createFolder: vi.fn(),
    deleteFolder: vi.fn(),
    moveFolder: vi.fn(),
    deletePhoto: vi.fn(),
    fetchFolder: vi.fn(),
    updateFolder: vi.fn(),
    startFolderZip: vi.fn(),
    getZipJob: vi.fn(),
    zipJobDownloadUrl: vi.fn((id: string) => `/zip/${id}`),
    importScan: vi.fn(),
    getImportScanStatus: vi.fn(),
  },
}))

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({ useMessage: () => h.msg, useDialog: () => ({}) }))
vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: h.confirmMock }),
}))
vi.mock('@/stores/photos', () => ({
  usePhotosStore: () => ({ loadRecent: h.loadRecent }),
  RECENT_LIMIT: 4,
}))
vi.mock('@tanstack/vue-query', () => ({ useQueryClient: () => h.qc }))
vi.mock('@/queries/photos', () => ({
  usePhotoFolderPhotosQuery: () => ({
    isFetching: ref(false),
    error: ref(null),
    data: ref(null),
    refetch: h.refetch,
  }),
  usePhotoAllTagsQuery: () => ({ data: ref([]), refetch: h.tagsRefetch }),
  usePhotoFolderTreeQuery: () => ({ data: ref({ items: [] }), isLoading: ref(false) }),
  usePhotoFolderQuery: () => ({ data: ref(null) }),
}))
vi.mock('@/api/photos', () => h.api)

import { usePhotoSelection } from '@/composables/usePhotoSelection'
import { usePhotoFolderActions } from '@/composables/usePhotoFolderActions'
import { usePhotoListing } from '@/composables/usePhotoListing'
import { usePhotoFolderSelection } from '@/composables/usePhotoFolderSelection'
import { useZipExport } from '@/composables/useZipExport'
import { useImportScan } from '@/composables/useImportScan'

beforeEach(() => {
  vi.clearAllMocks()
  h.api.zipJobDownloadUrl.mockImplementation((id: string) => `/zip/${id}`)
})

function photo(id: string, extra: Record<string, unknown> = {}) {
  return { id, original_name: `${id}.jpg`, uploaded_by: 'u1', ...extra } as never
}

describe('usePhotoSelection', () => {
  it('toggleSelectMode clears selection when leaving select mode', () => {
    const s = usePhotoSelection({ photos: ref([]), totalPhotos: ref(0), reloadPhotos: vi.fn() })
    s.toggleSelectMode()
    expect(s.selectMode.value).toBe(true)
    s.togglePhotoSelect('a')
    expect(s.selectedPhotoIds.value.has('a')).toBe(true)
    s.toggleSelectMode()
    expect(s.selectMode.value).toBe(false)
    expect(s.selectedPhotoIds.value.size).toBe(0)
  })

  it('togglePhotoSelect adds then removes an id', () => {
    const s = usePhotoSelection({ photos: ref([]), totalPhotos: ref(0), reloadPhotos: vi.fn() })
    s.togglePhotoSelect('x')
    expect(s.selectedPhotoIds.value.has('x')).toBe(true)
    s.togglePhotoSelect('x')
    expect(s.selectedPhotoIds.value.has('x')).toBe(false)
  })

  it('bulkDelete is a no-op when nothing selected', async () => {
    const s = usePhotoSelection({ photos: ref([]), totalPhotos: ref(0), reloadPhotos: vi.fn() })
    await s.bulkDelete()
    expect(h.confirmMock).not.toHaveBeenCalled()
    expect(h.api.bulkAction).not.toHaveBeenCalled()
  })

  it('bulkDelete aborts when confirm is declined', async () => {
    const photos = ref([photo('a'), photo('b')])
    const s = usePhotoSelection({ photos, totalPhotos: ref(2), reloadPhotos: vi.fn() })
    s.togglePhotoSelect('a')
    h.confirmMock.mockResolvedValue(false)
    await s.bulkDelete()
    expect(h.api.bulkAction).not.toHaveBeenCalled()
  })

  it('bulkDelete removes processed photos and leaves select mode', async () => {
    const photos = ref([photo('a'), photo('b'), photo('c')])
    const total = ref(3)
    const s = usePhotoSelection({ photos, totalPhotos: total, reloadPhotos: vi.fn() })
    s.toggleSelectMode()
    s.togglePhotoSelect('a')
    s.togglePhotoSelect('b')
    h.confirmMock.mockResolvedValue(true)
    h.api.bulkAction.mockResolvedValue({ processed: 2 })
    await s.bulkDelete()
    expect(h.api.bulkAction).toHaveBeenCalledWith({ action: 'delete', photo_ids: ['a', 'b'] })
    expect(photos.value.map(p => (p as { id: string }).id)).toEqual(['c'])
    expect(total.value).toBe(1)
    expect(s.selectMode.value).toBe(false)
    expect(h.msg.success).toHaveBeenCalled()
    expect(h.loadRecent).toHaveBeenCalled()
  })

  it('bulkDelete surfaces an error on API failure', async () => {
    const photos = ref([photo('a')])
    const s = usePhotoSelection({ photos, totalPhotos: ref(1), reloadPhotos: vi.fn() })
    s.togglePhotoSelect('a')
    h.confirmMock.mockResolvedValue(true)
    h.api.bulkAction.mockRejectedValue(new Error('boom'))
    await s.bulkDelete()
    expect(h.msg.error).toHaveBeenCalledWith('errors.generic')
  })

  it('openMoveModal requires a selection', () => {
    const s = usePhotoSelection({ photos: ref([]), totalPhotos: ref(0), reloadPhotos: vi.fn() })
    s.openMoveModal()
    expect(s.moveModalOpen.value).toBe(false)
    s.togglePhotoSelect('a')
    s.openMoveModal()
    expect(s.moveModalOpen.value).toBe(true)
    expect(s.moveTargetFolderId.value).toBeNull()
  })

  it('confirmMove returns false when no target chosen', async () => {
    const s = usePhotoSelection({ photos: ref([]), totalPhotos: ref(0), reloadPhotos: vi.fn() })
    s.togglePhotoSelect('a')
    const r = await s.confirmMove()
    expect(r).toBe(false)
    expect(h.api.bulkAction).not.toHaveBeenCalled()
  })

  it('confirmMove moves selection and reloads', async () => {
    const reload = vi.fn().mockResolvedValue(undefined)
    const s = usePhotoSelection({ photos: ref([]), totalPhotos: ref(0), reloadPhotos: reload })
    s.toggleSelectMode()
    s.togglePhotoSelect('a')
    s.moveTargetFolderId.value = 'dest'
    h.api.bulkAction.mockResolvedValue({ processed: 1 })
    await s.confirmMove()
    expect(h.api.bulkAction).toHaveBeenCalledWith({
      action: 'move',
      photo_ids: ['a'],
      target_folder_id: 'dest',
    })
    expect(s.moveModalOpen.value).toBe(false)
    expect(reload).toHaveBeenCalled()
    expect(s.selectMode.value).toBe(false)
  })

  it('confirmMove returns false on API error', async () => {
    const s = usePhotoSelection({ photos: ref([]), totalPhotos: ref(0), reloadPhotos: vi.fn() })
    s.togglePhotoSelect('a')
    s.moveTargetFolderId.value = 'dest'
    h.api.bulkAction.mockRejectedValue(new Error('x'))
    const r = await s.confirmMove()
    expect(r).toBe(false)
    expect(h.msg.error).toHaveBeenCalled()
  })
})

describe('usePhotoFolderActions', () => {
  function make() {
    return usePhotoFolderActions({
      selectedFolderId: ref<string | null>(null),
      selectedFolder: ref(null),
      photos: ref([]),
      loadTree: vi.fn().mockResolvedValue(undefined),
    })
  }

  it('openCreateRoot resets form and opens modal with null parent', () => {
    const a = make()
    a.newFolderName.value = 'stale'
    a.openCreateRoot()
    expect(a.folderModalOpen.value).toBe(true)
    expect(a.newFolderName.value).toBe('')
  })

  it('openCreateChild stores the parent node id', () => {
    const a = make()
    a.openCreateChild({ id: 'parent', name: 'P' } as never)
    expect(a.folderModalOpen.value).toBe(true)
  })

  it('submitCreateFolder validates a required name', async () => {
    const a = make()
    a.newFolderName.value = '   '
    const r = await a.submitCreateFolder()
    expect(r).toBe(false)
    expect(h.msg.warning).toHaveBeenCalled()
    expect(h.api.createFolder).not.toHaveBeenCalled()
  })

  it('submitCreateFolder creates and reloads tree', async () => {
    const loadTree = vi.fn().mockResolvedValue(undefined)
    const a = usePhotoFolderActions({
      selectedFolderId: ref(null),
      selectedFolder: ref(null),
      photos: ref([]),
      loadTree,
    })
    a.newFolderName.value = ' New '
    a.newFolderDesc.value = ' desc '
    h.api.createFolder.mockResolvedValue({ id: 'f1' })
    await a.submitCreateFolder()
    expect(h.api.createFolder).toHaveBeenCalledWith({
      parent_id: null,
      name: 'New',
      description: 'desc',
    })
    expect(a.folderModalOpen.value).toBe(false)
    expect(loadTree).toHaveBeenCalled()
  })

  it('submitCreateFolder reports API error', async () => {
    const a = make()
    a.newFolderName.value = 'X'
    h.api.createFolder.mockRejectedValue(new Error('e'))
    const r = await a.submitCreateFolder()
    expect(r).toBe(false)
    expect(h.msg.error).toHaveBeenCalled()
  })

  it('confirmDeleteFolder clears selection when the active folder is deleted', async () => {
    const selectedFolderId = ref<string | null>('f1')
    const selectedFolder = ref<unknown>({ id: 'f1' })
    const photos = ref([photo('a')])
    const loadTree = vi.fn().mockResolvedValue(undefined)
    const a = usePhotoFolderActions({
      selectedFolderId,
      selectedFolder: selectedFolder as never,
      photos,
      loadTree,
    })
    h.confirmMock.mockResolvedValue(true)
    h.api.deleteFolder.mockResolvedValue(undefined)
    await a.confirmDeleteFolder({ id: 'f1', name: 'F1' } as never)
    expect(h.api.deleteFolder).toHaveBeenCalledWith('f1')
    expect(selectedFolderId.value).toBeNull()
    expect(photos.value).toEqual([])
    expect(loadTree).toHaveBeenCalled()
    expect(h.loadRecent).toHaveBeenCalled()
  })

  it('confirmDeleteFolder aborts when declined', async () => {
    const a = make()
    h.confirmMock.mockResolvedValue(false)
    await a.confirmDeleteFolder({ id: 'f1', name: 'F1' } as never)
    expect(h.api.deleteFolder).not.toHaveBeenCalled()
  })

  it('openPermissions sets target and opens the modal', () => {
    const a = make()
    a.openPermissions({ id: 'f1', name: 'F1' } as never)
    expect(a.permsModalOpen.value).toBe(true)
    expect(a.permsTarget.value).toMatchObject({ id: 'f1' })
  })

  it('onFolderDrop rejects drop without manager permission', async () => {
    const a = make()
    a.onFolderDragStart({ id: 'src', name: 'S', permission: 'manager' } as never)
    await a.onFolderDrop({ id: 'dst', name: 'D', permission: 'viewer' } as never)
    expect(h.msg.error).toHaveBeenCalledWith('photos.folders.cannotMoveNoPermission')
    expect(h.api.moveFolder).not.toHaveBeenCalled()
  })

  it('onFolderDrop rejects dropping a folder into its own descendant', async () => {
    const a = make()
    const src = { id: 'src', name: 'S', children: [{ id: 'dst', name: 'D' }] }
    a.onFolderDragStart(src as never)
    await a.onFolderDrop({ id: 'dst', name: 'D', permission: 'manager' } as never)
    expect(h.msg.error).toHaveBeenCalledWith('photos.folders.cannotMoveToDescendant')
    expect(h.api.moveFolder).not.toHaveBeenCalled()
  })

  it('onFolderDrop ignores a drop onto itself', async () => {
    const a = make()
    a.onFolderDragStart({ id: 'same', name: 'S', permission: 'manager' } as never)
    await a.onFolderDrop({ id: 'same', name: 'S', permission: 'manager' } as never)
    expect(h.api.moveFolder).not.toHaveBeenCalled()
  })

  it('onFolderDrop moves when confirmed', async () => {
    const loadTree = vi.fn().mockResolvedValue(undefined)
    const a = usePhotoFolderActions({
      selectedFolderId: ref(null),
      selectedFolder: ref(null),
      photos: ref([]),
      loadTree,
    })
    a.onFolderDragStart({ id: 'src', name: 'S' } as never)
    h.confirmMock.mockResolvedValue(true)
    h.api.moveFolder.mockResolvedValue(undefined)
    await a.onFolderDrop({ id: 'dst', name: 'D', permission: 'manager' } as never)
    expect(h.api.moveFolder).toHaveBeenCalledWith('src', 'dst')
    expect(loadTree).toHaveBeenCalled()
  })

  it('onFolderMoveToRoot moves to null parent when confirmed', async () => {
    const loadTree = vi.fn().mockResolvedValue(undefined)
    const a = usePhotoFolderActions({
      selectedFolderId: ref(null),
      selectedFolder: ref(null),
      photos: ref([]),
      loadTree,
    })
    h.confirmMock.mockResolvedValue(true)
    h.api.moveFolder.mockResolvedValue(undefined)
    await a.onFolderMoveToRoot({ id: 'n1', name: 'N' } as never)
    expect(h.api.moveFolder).toHaveBeenCalledWith('n1', null)
    expect(loadTree).toHaveBeenCalled()
  })
})

describe('usePhotoListing', () => {
  it('onSortChange resets to first page and clears photos', () => {
    const l = usePhotoListing({ selectedFolderId: ref('f1') })
    l.photos.value = [photo('a')]
    l.page.value = 3
    l.onSortChange()
    expect(l.page.value).toBe(1)
    expect(l.photos.value).toEqual([])
  })

  it('setTagFilter toggles the active filter id', () => {
    const l = usePhotoListing({ selectedFolderId: ref('f1') })
    l.setTagFilter({ id: 't1', name: 'tag' } as never)
    expect(l.activeTagFilter.value).toBe('t1')
    expect(l.hasActiveFilters.value).toBe(true)
    l.setTagFilter({ id: 't1', name: 'tag' } as never)
    expect(l.activeTagFilter.value).toBeNull()
  })

  it('clearTagFilter removes the active filter', () => {
    const l = usePhotoListing({ selectedFolderId: ref('f1') })
    l.setTagFilter({ id: 't1', name: 'tag' } as never)
    l.clearTagFilter()
    expect(l.activeTagFilter.value).toBeNull()
  })

  it('onTagsUpdated stores tags for a photo', () => {
    const l = usePhotoListing({ selectedFolderId: ref('f1') })
    l.onTagsUpdated('p1', [{ id: 't1', name: 'tag' } as never])
    expect(l.photoTagsMap.value.p1).toHaveLength(1)
  })

  it('resetForFolder clears photos and totals', () => {
    const l = usePhotoListing({ selectedFolderId: ref('f1') })
    l.photos.value = [photo('a')]
    l.totalPhotos.value = 5
    l.resetForFolder()
    expect(l.photos.value).toEqual([])
    expect(l.totalPhotos.value).toBe(0)
  })

  it('loadMorePhotos increments the page', async () => {
    const l = usePhotoListing({ selectedFolderId: ref('f1') })
    await l.loadMorePhotos()
    expect(l.page.value).toBe(2)
  })

  it('confirmDeletePhoto deletes and decrements total', async () => {
    const l = usePhotoListing({ selectedFolderId: ref('f1') })
    l.photos.value = [photo('a'), photo('b')]
    l.totalPhotos.value = 2
    h.confirmMock.mockResolvedValue(true)
    h.api.deletePhoto.mockResolvedValue(undefined)
    await l.confirmDeletePhoto(photo('a'))
    expect(h.api.deletePhoto).toHaveBeenCalledWith('a')
    expect(l.photos.value.map(p => (p as { id: string }).id)).toEqual(['b'])
    expect(l.totalPhotos.value).toBe(1)
    expect(h.qc.invalidateQueries).toHaveBeenCalled()
  })

  it('confirmDeletePhoto aborts when declined', async () => {
    const l = usePhotoListing({ selectedFolderId: ref('f1') })
    h.confirmMock.mockResolvedValue(false)
    await l.confirmDeletePhoto(photo('a'))
    expect(h.api.deletePhoto).not.toHaveBeenCalled()
  })

  it('confirmDeletePhoto reports API error', async () => {
    const l = usePhotoListing({ selectedFolderId: ref('f1') })
    l.photos.value = [photo('a')]
    h.confirmMock.mockResolvedValue(true)
    h.api.deletePhoto.mockRejectedValue(new Error('e'))
    await l.confirmDeletePhoto(photo('a'))
    expect(h.msg.error).toHaveBeenCalledWith('errors.generic')
  })
})

describe('usePhotoFolderSelection', () => {
  it('flatten walks the tree depth-first', () => {
    const s = usePhotoFolderSelection()
    const flat = s.flatten([
      { id: '1', name: 'a', children: [{ id: '2', name: 'b', children: [{ id: '3', name: 'c' }] }] },
      { id: '4', name: 'd' },
    ] as never)
    expect(flat.map(n => (n as { id: string }).id)).toEqual(['1', '2', '3', '4'])
  })

  it('selectFolder runs hooks and ensures folder data', async () => {
    const beforeSelect = vi.fn()
    const onAfterSelect = vi.fn().mockResolvedValue(undefined)
    const s = usePhotoFolderSelection({ beforeSelect, onAfterSelect })
    await s.selectFolder({ id: 'f9', name: 'F9' } as never)
    expect(beforeSelect).toHaveBeenCalled()
    expect(s.selectedFolderId.value).toBe('f9')
    expect(h.qc.ensureQueryData).toHaveBeenCalled()
    expect(onAfterSelect).toHaveBeenCalled()
  })

  it('startEditDescription seeds the edit field', () => {
    const s = usePhotoFolderSelection()
    s.startEditDescription()
    expect(s.editingDescription.value).toBe(true)
    expect(s.editDescValue.value).toBe('')
  })

  it('saveDescription is a no-op without a selected folder', async () => {
    const s = usePhotoFolderSelection()
    await s.saveDescription()
    expect(h.api.updateFolder).not.toHaveBeenCalled()
  })

  it('saveDescription persists and updates the cache', async () => {
    const s = usePhotoFolderSelection()
    s.selectedFolderId.value = 'f1'
    s.editDescValue.value = ' hello '
    h.api.updateFolder.mockResolvedValue({ id: 'f1', description: 'hello' })
    await s.saveDescription()
    expect(h.api.updateFolder).toHaveBeenCalledWith('f1', { description: 'hello' })
    expect(s.editingDescription.value).toBe(false)
    expect(h.qc.setQueryData).toHaveBeenCalled()
  })

  it('saveDescription reports API error', async () => {
    const s = usePhotoFolderSelection()
    s.selectedFolderId.value = 'f1'
    h.api.updateFolder.mockRejectedValue(new Error('e'))
    await s.saveDescription()
    expect(h.msg.error).toHaveBeenCalled()
  })

  it('loadTree invalidates the tree query', async () => {
    const s = usePhotoFolderSelection()
    await s.loadTree()
    expect(h.qc.invalidateQueries).toHaveBeenCalled()
  })
})

describe('useZipExport', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('startZip is a no-op when no folder is selected', async () => {
    const z = useZipExport(ref<string | null>(null))
    await z.startZip()
    expect(h.api.startFolderZip).not.toHaveBeenCalled()
  })

  it('startZip opens download immediately when the job is already done', async () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    const z = useZipExport(ref<string | null>('f1'))
    h.api.startFolderZip.mockResolvedValue({ id: 'job1', status: 'done' })
    await z.startZip()
    expect(openSpy).toHaveBeenCalledWith('/zip/job1', '_blank', 'noopener,noreferrer')
    expect(h.msg.success).toHaveBeenCalled()
  })

  it('startZip reports an immediate error status', async () => {
    const z = useZipExport(ref<string | null>('f1'))
    h.api.startFolderZip.mockResolvedValue({ id: 'job1', status: 'error' })
    await z.startZip()
    expect(h.msg.error).toHaveBeenCalledWith('photos.zip.error')
  })

  it('startZip reports a start failure', async () => {
    const z = useZipExport(ref<string | null>('f1'))
    h.api.startFolderZip.mockRejectedValue(new Error('e'))
    await z.startZip()
    expect(h.msg.error).toHaveBeenCalledWith('errors.generic')
  })

  it('startZip polls until done then opens the download', async () => {
    vi.useFakeTimers()
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    const z = useZipExport(ref<string | null>('f1'))
    h.api.startFolderZip.mockResolvedValue({ id: 'job1', status: 'processing' })
    h.api.getZipJob.mockResolvedValue({ id: 'job1', status: 'done' })
    await z.startZip()
    expect(z.zipJob.value?.status).toBe('processing')
    await vi.advanceTimersByTimeAsync(2000)
    expect(h.api.getZipJob).toHaveBeenCalledWith('job1')
    expect(openSpy).toHaveBeenCalled()
  })

  it('stopZipPolling cancels an in-flight poll', async () => {
    vi.useFakeTimers()
    const z = useZipExport(ref<string | null>('f1'))
    h.api.startFolderZip.mockResolvedValue({ id: 'job1', status: 'processing' })
    h.api.getZipJob.mockResolvedValue({ id: 'job1', status: 'processing' })
    await z.startZip()
    z.stopZipPolling()
    await vi.advanceTimersByTimeAsync(4000)
    expect(h.api.getZipJob).not.toHaveBeenCalled()
  })
})

describe('useImportScan', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('confirmImportScan aborts when declined', async () => {
    const { confirmImportScan } = useImportScan(vi.fn().mockResolvedValue(undefined))
    h.confirmMock.mockResolvedValue(false)
    await confirmImportScan()
    expect(h.api.importScan).not.toHaveBeenCalled()
  })

  it('confirmImportScan queues a scan and polls to completion', async () => {
    vi.useFakeTimers()
    const onTreeChanged = vi.fn().mockResolvedValue(undefined)
    const { confirmImportScan } = useImportScan(onTreeChanged)
    h.confirmMock.mockResolvedValue(true)
    h.api.importScan.mockResolvedValue({ job_id: 'j1' })
    h.api.getImportScanStatus.mockResolvedValue({
      status: 'complete',
      result: { photos_imported: 2, folders_created: 1, skipped: 0 },
    })
    await confirmImportScan()
    expect(h.api.importScan).toHaveBeenCalled()
    expect(h.msg.info).toHaveBeenCalledWith('photos.import.queued')
    await vi.advanceTimersByTimeAsync(2000)
    expect(h.api.getImportScanStatus).toHaveBeenCalledWith('j1')
    expect(onTreeChanged).toHaveBeenCalled()
    expect(h.msg.success).toHaveBeenCalled()
  })

  it('confirmImportScan reports a queue failure', async () => {
    const { confirmImportScan } = useImportScan(vi.fn())
    h.confirmMock.mockResolvedValue(true)
    h.api.importScan.mockRejectedValue(new Error('e'))
    await confirmImportScan()
    expect(h.msg.error).toHaveBeenCalledWith('errors.generic')
  })
})
