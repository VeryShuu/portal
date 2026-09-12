import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { useFilesSelection } from '../../src/composables/useFilesSelection'

function file(name: string, path: string, mime = 'text/plain') {
  return {
    name,
    nc_path: path,
    is_dir: false,
    size_bytes: 1,
    mime_type: mime,
    last_modified: null,
    etag: null,
    uploaded_at: null,
    uploaded_by: null,
  }
}

function dir(name: string, path: string) {
  return {
    ...file(name, path),
    is_dir: true,
  }
}

function clickEvent(opts: Partial<MouseEvent> = {}) {
  return {
    shiftKey: false,
    ctrlKey: false,
    metaKey: false,
    preventDefault: vi.fn(),
    ...opts,
  } as unknown as MouseEvent
}

describe('useFilesSelection', () => {
  it('computes selected filenames only for selected non-directories', () => {
    const items = ref([file('a.txt', '/a.txt'), dir('folder', '/folder'), file('b.txt', '/b.txt')])
    const folderId = ref<string | null>('root')
    const api = useFilesSelection(items, folderId)

    api.selectedKeys.value = ['/a.txt', '/folder']

    expect(api.selectedFilenames.value).toEqual(['a.txt'])
  })

  it('clears selection when folderId changes and clearSelection resets state', async () => {
    const items = ref([file('a.txt', '/a.txt')])
    const folderId = ref<string | null>('root')
    const api = useFilesSelection(items, folderId)

    api.selectedKeys.value = ['/a.txt']
    api.lastSelectedIndex.value = 2

    api.clearSelection()
    expect(api.selectedKeys.value).toEqual([])
    expect(api.lastSelectedIndex.value).toBe(null)

    api.selectedKeys.value = ['/a.txt']
    api.lastSelectedIndex.value = 0
    folderId.value = 'other'
    await nextTick()

    expect(api.selectedKeys.value).toEqual([])
    expect(api.lastSelectedIndex.value).toBe(null)
  })

  it('opens directory only without modifiers and returns early for dir rows', () => {
    const onOpenDir = vi.fn()
    const onPreview = vi.fn()
    const items = ref([dir('docs', '/docs')])
    const folderId = ref<string | null>('root')
    const api = useFilesSelection(items, folderId, { onOpenDir, onPreview })

    api.onRowClick(items.value[0], 0, clickEvent())
    expect(onOpenDir).toHaveBeenCalledTimes(1)

    api.onRowClick(items.value[0], 0, clickEvent({ ctrlKey: true }))
    api.onRowClick(items.value[0], 0, clickEvent({ shiftKey: true }))
    api.onRowClick(items.value[0], 0, clickEvent({ metaKey: true }))

    expect(onOpenDir).toHaveBeenCalledTimes(1)
    expect(onPreview).not.toHaveBeenCalled()
  })

  it('selects range on shift when lastSelectedIndex exists', () => {
    const items = ref([
      file('a.jpg', '/a.jpg', 'image/jpeg'),
      dir('folder', '/folder'),
      file('b.pdf', '/b.pdf', 'application/pdf'),
      file('c.txt', '/c.txt'),
    ])
    const folderId = ref<string | null>('root')
    const api = useFilesSelection(items, folderId)

    api.selectedKeys.value = ['/a.jpg']
    api.lastSelectedIndex.value = 0
    const e = clickEvent({ shiftKey: true })

    api.onRowClick(items.value[3], 3, e)

    expect((e.preventDefault as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1)
    expect(api.selectedKeys.value.sort()).toEqual(['/a.jpg', '/b.pdf', '/c.txt'].sort())
  })

  it('ctrl/meta toggles selected keys and updates lastSelectedIndex', () => {
    const items = ref([file('a.txt', '/a.txt'), file('b.txt', '/b.txt')])
    const folderId = ref<string | null>('root')
    const api = useFilesSelection(items, folderId)

    const ctrlE = clickEvent({ ctrlKey: true })
    api.onRowClick(items.value[0], 0, ctrlE)
    expect(api.selectedKeys.value).toEqual(['/a.txt'])
    expect(api.lastSelectedIndex.value).toBe(0)

    const metaE = clickEvent({ metaKey: true })
    api.onRowClick(items.value[0], 0, metaE)
    expect(api.selectedKeys.value).toEqual([])
    expect(api.lastSelectedIndex.value).toBe(0)
  })

  it('single click sets last index and previews only when selection is empty and file previewable', () => {
    const onPreview = vi.fn()
    const items = ref([
      file('pic.jpg', '/pic.jpg', 'image/jpeg'),
      file('doc.pdf', '/doc.pdf', 'application/pdf'),
      file('note.txt', '/note.txt', 'text/plain'),
    ])
    const folderId = ref<string | null>('root')
    const api = useFilesSelection(items, folderId, { onPreview })

    api.onRowClick(items.value[0], 0, clickEvent())
    expect(api.lastSelectedIndex.value).toBe(0)
    expect(onPreview).toHaveBeenCalledTimes(1)

    api.onRowClick(items.value[1], 1, clickEvent())
    expect(onPreview).toHaveBeenCalledTimes(2)

    api.onRowClick(items.value[2], 2, clickEvent())
    expect(onPreview).toHaveBeenCalledTimes(2)

    api.selectedKeys.value = ['/note.txt']
    api.onRowClick(items.value[0], 0, clickEvent())
    expect(onPreview).toHaveBeenCalledTimes(2)
  })
})
