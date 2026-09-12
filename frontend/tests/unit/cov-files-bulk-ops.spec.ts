import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, computed, ref } from 'vue'
import { mount } from '@vue/test-utils'

type TreeNode = {
  id: string
  name: string
  permission: 'viewer' | 'editor' | 'manager' | null
  children: TreeNode[]
}

const mockMessage = {
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}

const mockConfirm = vi.fn()
const mockApi = vi.fn()

const mockAuth = {
  isAdmin: false,
}

const mockStore = {
  tree: [] as TreeNode[],
  findNodeById: vi.fn<(id: string) => TreeNode | null>(),
}

vi.mock('../../src/api/index', () => ({
  api: mockApi,
  apiUpload: vi.fn(),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, p?: Record<string, unknown>) => `${k}${p ? JSON.stringify(p) : ''}`,
  }),
}))

vi.mock('naive-ui', () => ({
  useMessage: () => mockMessage,
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: mockConfirm }),
}))

vi.mock('../../src/composables/useFilesData', () => ({
  useFilesData: () => mockStore,
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => mockAuth,
}))

async function setupHost(options?: {
  folderId?: string | null
  selectedFilenames?: string[]
  tree?: TreeNode[]
}) {
  const folderId = ref<string | null>(options?.folderId ?? 'folder-a')
  const selectedNames = ref<string[]>(options?.selectedFilenames ?? ['a.txt'])
  const clearSelection = vi.fn()
  const onAfterMutation = vi.fn(async () => {})

  mockStore.tree = options?.tree ?? []
  mockStore.findNodeById.mockImplementation((id: string) => {
    const walk = (nodes: TreeNode[]): TreeNode | null => {
      for (const node of nodes) {
        if (node.id === id) return node
        const child = walk(node.children)
        if (child) return child
      }
      return null
    }
    return walk(mockStore.tree)
  })

  let api: any = null
  const { useFilesBulkOps } = await import('../../src/composables/useFilesBulkOps')

  const Host = defineComponent({
    setup() {
      api = useFilesBulkOps({
        folderId,
        selectedFilenames: computed(() => selectedNames.value),
        clearSelection,
        onAfterMutation,
      })
      return () => h('div')
    },
  })

  mount(Host)

  return {
    api,
    folderId,
    selectedNames,
    clearSelection,
    onAfterMutation,
  }
}

describe('useFilesBulkOps', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuth.isAdmin = false
  })

  it('canMoveTo allows editor/manager/admin and blocks viewer', async () => {
    const { api } = await setupHost()

    expect(api.canMoveTo({ permission: 'editor' })).toBe(true)
    expect(api.canMoveTo({ permission: 'manager' })).toBe(true)
    expect(api.canMoveTo({ permission: 'viewer' })).toBe(false)

    mockAuth.isAdmin = true
    expect(api.canMoveTo({ permission: 'viewer' })).toBe(true)
  })

  it('moveTreeData filters disabled leaves and keeps allowed descendants', async () => {
    const tree: TreeNode[] = [
      { id: 'same', name: 'same', permission: 'editor', children: [] },
      {
        id: 'blocked-parent',
        name: 'blocked-parent',
        permission: 'viewer',
        children: [{ id: 'child-ok', name: 'child-ok', permission: 'editor', children: [] }],
      },
      { id: 'blocked-leaf', name: 'blocked-leaf', permission: 'viewer', children: [] },
    ]

    const { api } = await setupHost({ folderId: 'same', selectedFilenames: ['f.txt'], tree })

    const serialized = JSON.stringify(api.moveTreeData.value)
    expect(serialized).toContain('blocked-parent')
    expect(serialized).toContain('child-ok')
    expect(serialized).not.toContain('"key":"same"')
    expect(serialized).not.toContain('blocked-leaf')
  })

  it('bulkDownload handles guard clauses and over-limit warning', async () => {
    const { api, folderId, selectedNames } = await setupHost({ selectedFilenames: [] })

    await api.bulkDownload()
    expect(mockMessage.info).not.toHaveBeenCalled()

    folderId.value = null
    selectedNames.value = ['a.txt']
    await api.bulkDownload()
    expect(mockMessage.info).not.toHaveBeenCalled()

    folderId.value = 'folder-a'
    selectedNames.value = Array.from({ length: 21 }, (_, i) => `f-${i}.txt`)
    await api.bulkDownload()
    expect(mockMessage.warning).toHaveBeenCalledTimes(1)
  })

  it('bulkDownload creates anchor downloads for each selected name', async () => {
    const { api } = await setupHost({ folderId: 'folder-a', selectedFilenames: ['a.txt', 'b.txt'] })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    const removeSpy = vi.spyOn(document.body, 'removeChild')

    await api.bulkDownload()

    expect(mockMessage.info).toHaveBeenCalledTimes(1)
    expect(appendSpy).toHaveBeenCalledTimes(2)
    expect(clickSpy).toHaveBeenCalledTimes(2)
    expect(removeSpy).toHaveBeenCalledTimes(2)

    clickSpy.mockRestore()
  })

  it('confirmBulkDelete covers cancel, full success, partial success, and errors', async () => {
    const { api, selectedNames, clearSelection, onAfterMutation } = await setupHost({
      folderId: 'folder-a',
      selectedFilenames: ['x.txt'],
    })

    selectedNames.value = []
    await api.confirmBulkDelete()
    expect(mockConfirm).not.toHaveBeenCalled()

    selectedNames.value = ['x.txt']
    mockConfirm.mockResolvedValueOnce(false)
    await api.confirmBulkDelete()
    expect(mockApi).not.toHaveBeenCalled()

    mockConfirm.mockResolvedValueOnce(true)
    mockApi.mockResolvedValueOnce({ deleted: [{ name: 'x.txt', success: true, error: null }], failed: [] })
    await api.confirmBulkDelete()
    expect(mockMessage.success).toHaveBeenCalledTimes(1)
    expect(clearSelection).toHaveBeenCalledTimes(1)
    expect(onAfterMutation).toHaveBeenCalledTimes(1)
    expect(api.bulkBusy.value).toBe(false)

    mockConfirm.mockResolvedValueOnce(true)
    mockApi.mockResolvedValueOnce({
      deleted: [{ name: 'x.txt', success: true, error: null }],
      failed: [{ name: 'y.txt', success: false, error: 'denied' }],
    })
    await api.confirmBulkDelete()
    expect(mockMessage.warning).toHaveBeenCalled()

    mockConfirm.mockResolvedValueOnce(true)
    mockApi.mockRejectedValueOnce({ status: 409 })
    await api.confirmBulkDelete()
    expect(mockMessage.warning).toHaveBeenCalled()

    mockConfirm.mockResolvedValueOnce(true)
    mockApi.mockRejectedValueOnce({ status: 500 })
    await api.confirmBulkDelete()
    expect(mockMessage.error).toHaveBeenCalledTimes(1)
    expect(api.bulkBusy.value).toBe(false)
  })

  it('openMoveModal and onMoveTargetSelect cover all guards and valid selection', async () => {
    const tree: TreeNode[] = [
      { id: 'folder-a', name: 'A', permission: 'editor', children: [] },
      { id: 'folder-b', name: 'B', permission: 'viewer', children: [] },
      { id: 'folder-c', name: 'C', permission: 'manager', children: [] },
    ]

    const { api, selectedNames } = await setupHost({
      folderId: 'folder-a',
      selectedFilenames: [],
      tree,
    })

    api.openMoveModal()
    expect(api.showMoveModal.value).toBe(false)

    selectedNames.value = ['x.txt']
    api.moveTargetKey.value = 'old'
    api.openMoveModal()
    expect(api.showMoveModal.value).toBe(true)
    expect(api.moveTargetKey.value).toBe(null)

    api.onMoveTargetSelect([])
    expect(api.moveTargetKey.value).toBe(null)

    api.onMoveTargetSelect(['missing'])
    expect(api.moveTargetKey.value).toBe(null)

    api.onMoveTargetSelect(['folder-b'])
    expect(api.moveTargetKey.value).toBe(null)

    api.onMoveTargetSelect(['folder-a'])
    expect(api.moveTargetKey.value).toBe(null)

    api.onMoveTargetSelect(['folder-c'])
    expect(api.moveTargetKey.value).toBe('folder-c')
  })

  it('submitBulkMove covers guards, success, partial, and error branches', async () => {
    const { api, folderId, selectedNames, clearSelection, onAfterMutation } = await setupHost({
      folderId: 'folder-a',
      selectedFilenames: ['x.txt'],
    })

    folderId.value = null
    api.moveTargetKey.value = 'target'
    await api.submitBulkMove()
    expect(mockApi).not.toHaveBeenCalled()

    folderId.value = 'folder-a'
    api.moveTargetKey.value = null
    await api.submitBulkMove()
    expect(mockApi).not.toHaveBeenCalled()

    api.moveTargetKey.value = 'target'
    selectedNames.value = []
    await api.submitBulkMove()
    expect(mockApi).not.toHaveBeenCalled()

    selectedNames.value = ['x.txt']
    api.showMoveModal.value = true
    mockApi.mockResolvedValueOnce({ moved: [{ name: 'x.txt', new_name: null, success: true, error: null }], failed: [] })
    await api.submitBulkMove()
    expect(mockMessage.success).toHaveBeenCalled()
    expect(api.showMoveModal.value).toBe(false)
    expect(clearSelection).toHaveBeenCalledTimes(1)
    expect(onAfterMutation).toHaveBeenCalledTimes(1)

    api.showMoveModal.value = true
    mockApi.mockResolvedValueOnce({
      moved: [{ name: 'x.txt', new_name: null, success: true, error: null }],
      failed: [{ name: 'y.txt', new_name: null, success: false, error: 'denied' }],
    })
    await api.submitBulkMove()
    expect(mockMessage.warning).toHaveBeenCalled()

    api.showMoveModal.value = true
    mockApi.mockRejectedValueOnce({ status: 409 })
    await api.submitBulkMove()
    expect(mockMessage.warning).toHaveBeenCalled()

    api.showMoveModal.value = true
    mockApi.mockRejectedValueOnce({ status: 500 })
    await api.submitBulkMove()
    expect(mockMessage.error).toHaveBeenCalled()
    expect(api.bulkBusy.value).toBe(false)
  })
})
