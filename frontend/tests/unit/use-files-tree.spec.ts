import { describe, it, expect, beforeEach, vi } from 'vitest'

const storeMock = {
  tree: [{ id: 'root', children: [] }],
  loadingTree: false,
  selectedFolderId: 'root',
  selectFolder: vi.fn(),
  findNodeById: vi.fn((id: string) => (id === 'root' ? { id: 'root' } : null)),
  findNodeByNcPath: vi.fn((path: string) => (path === '/root' ? { id: 'root' } : null)),
  loadTree: vi.fn().mockResolvedValue(undefined),
}

vi.mock('../../src/composables/useFilesData', () => ({
  useFilesData: () => storeMock,
}))

import { useFilesTree } from '../../src/composables/useFilesTree'

describe('useFilesTree (src/composables)', () => {
  beforeEach(() => {
    storeMock.selectFolder.mockClear()
    storeMock.findNodeById.mockClear()
    storeMock.findNodeByNcPath.mockClear()
    storeMock.loadTree.mockClear()
  })

  it('delegates reactive tree/loading/selected to the underlying store', () => {
    const t = useFilesTree()
    expect(t.tree.value).toEqual([{ id: 'root', children: [] }])
    expect(t.loadingTree.value).toBe(false)
    expect(t.selectedFolderId.value).toBe('root')
  })

  it('selectFolder forwards to store.selectFolder', () => {
    const t = useFilesTree()
    t.selectFolder('abc')
    expect(storeMock.selectFolder).toHaveBeenCalledWith('abc')
  })

  it('selectFolder forwards null to allow clearing', () => {
    const t = useFilesTree()
    t.selectFolder(null)
    expect(storeMock.selectFolder).toHaveBeenCalledWith(null)
  })

  it('findNodeById returns the matching node and null when missing', () => {
    const t = useFilesTree()
    expect(t.findNodeById('root')).toEqual({ id: 'root' })
    expect(t.findNodeById('missing')).toBe(null)
  })

  it('findNodeByNcPath returns the matching node and null when missing', () => {
    const t = useFilesTree()
    expect(t.findNodeByNcPath('/root')).toEqual({ id: 'root' })
    expect(t.findNodeByNcPath('/nope')).toBe(null)
  })

  it('loadTree forwards to store.loadTree and resolves', async () => {
    const t = useFilesTree()
    await expect(t.loadTree()).resolves.toBeUndefined()
    expect(storeMock.loadTree).toHaveBeenCalled()
  })
})
