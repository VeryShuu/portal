import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

const messageMock = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }
vi.mock('naive-ui', () => ({
  useMessage: () => messageMock,
}))

const apiUploadMock = vi.fn()
const apiMock = vi.fn()
vi.mock('@/api', () => ({
  apiUpload: (...args: unknown[]) => apiUploadMock(...args),
  api: (...args: unknown[]) => apiMock(...args),
}))

import { useEditorImageUpload } from '@/components/editor/useEditorImageUpload'
import type { Editor } from '@tiptap/vue-3'

interface ChainRecord {
  calls: Array<[string, ...unknown[]]>
}

function makeChain(record: ChainRecord) {
  const handler: ProxyHandler<Record<string, unknown>> = {
    get(_t, prop: string) {
      if (prop === 'run') return () => true
      return (...args: unknown[]) => {
        record.calls.push([prop, ...args])
        return proxy
      }
    },
  }
  const proxy = new Proxy({}, handler)
  return proxy
}

function createFakeEditor(opts: { active?: Record<string, boolean>; attrs?: Record<string, unknown> } = {}) {
  const record: ChainRecord = { calls: [] }
  const editor = {
    isActive: vi.fn((name: string) => Boolean(opts.active?.[name])),
    getAttributes: vi.fn(() => opts.attrs ?? {}),
    chain: vi.fn(() => makeChain(record)),
  } as unknown as Editor
  return { editor: ref<Editor | undefined>(editor), record }
}

function imageFile(type = 'image/png') {
  return new File(['x'], 'pic.png', { type })
}

describe('useEditorImageUpload (RE-0 characterizing)', () => {
  beforeEach(() => {
    apiUploadMock.mockReset()
    apiMock.mockReset()
    messageMock.warning.mockReset()
    messageMock.error.mockReset()
  })

  it('triggerImageUpload: clicks hidden input when not on a figure', () => {
    const { editor } = createFakeEditor()
    const u = useEditorImageUpload(editor, ref(undefined))
    const click = vi.fn()
    u.fileInputRef.value = { click } as unknown as HTMLInputElement
    u.triggerImageUpload()
    expect(click).toHaveBeenCalled()
  })

  it('triggerImageUpload: opens edit dialog when figure active', () => {
    const { editor } = createFakeEditor({ active: { figureImage: true }, attrs: { src: 'http://x/y.png', alt: 'a', caption: 'c' } })
    const u = useEditorImageUpload(editor, ref(undefined))
    u.triggerImageUpload()
    expect(u.showImageDialog.value).toBe(true)
    expect(u.imageForm.src).toBe('http://x/y.png')
    expect(u.imageForm.alt).toBe('a')
  })

  it('handleFileInputChange: without uploadEndpoint warns and does not open dialog', async () => {
    const { editor } = createFakeEditor()
    const u = useEditorImageUpload(editor, ref(undefined))
    const input = { files: [imageFile()], value: 'pic.png' } as unknown as HTMLInputElement
    await u.handleFileInputChange({ target: input } as unknown as Event)
    expect(messageMock.warning).toHaveBeenCalledWith('editor.imageUploadDisabled')
    expect(apiUploadMock).not.toHaveBeenCalled()
    expect(u.showImageDialog.value).toBe(false)
  })

  it('handleFileInputChange: uploads and opens dialog with returned url', async () => {
    const { editor } = createFakeEditor()
    apiUploadMock.mockResolvedValue({ url: 'http://cdn/img.png' })
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    const input = { files: [imageFile()], value: 'pic.png' } as unknown as HTMLInputElement
    await u.handleFileInputChange({ target: input } as unknown as Event)
    expect(apiUploadMock).toHaveBeenCalledTimes(1)
    expect(u.imageForm.src).toBe('http://cdn/img.png')
    expect(u.showImageDialog.value).toBe(true)
  })

  it('upload 413 error shows image-too-large message', async () => {
    const { editor } = createFakeEditor()
    apiUploadMock.mockRejectedValue({ response: { status: 413 } })
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    const input = { files: [imageFile()], value: 'pic.png' } as unknown as HTMLInputElement
    await u.handleFileInputChange({ target: input } as unknown as Event)
    expect(messageMock.error).toHaveBeenCalledWith('editor.imageTooLarge')
    expect(u.showImageDialog.value).toBe(false)
  })

  it('upload generic error shows generic message', async () => {
    const { editor } = createFakeEditor()
    apiUploadMock.mockRejectedValue({ status: 500 })
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    const input = { files: [imageFile()], value: 'pic.png' } as unknown as HTMLInputElement
    await u.handleFileInputChange({ target: input } as unknown as Event)
    expect(messageMock.error).toHaveBeenCalledWith('editor.imageUploadError')
  })

  it('handleDrop: picks first image file and opens dialog', async () => {
    const { editor } = createFakeEditor()
    apiUploadMock.mockResolvedValue({ url: 'http://cdn/drop.png' })
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    const event = { dataTransfer: { files: [new File(['t'], 'a.txt', { type: 'text/plain' }), imageFile()] } }
    await u.handleDrop(event as unknown as DragEvent)
    expect(u.imageForm.src).toBe('http://cdn/drop.png')
    expect(u.showImageDialog.value).toBe(true)
  })

  it('handleDrop: no image files and no remote url does nothing', async () => {
    const { editor } = createFakeEditor()
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    const event = {
      dataTransfer: {
        files: [new File(['t'], 'a.txt', { type: 'text/plain' })],
        getData: () => '',
      },
    }
    await u.handleDrop(event as unknown as DragEvent)
    expect(apiUploadMock).not.toHaveBeenCalled()
    expect(apiMock).not.toHaveBeenCalled()
    expect(u.showImageDialog.value).toBe(false)
  })

  it('handlePaste: image item prevents default, uploads, opens dialog', async () => {
    const { editor } = createFakeEditor()
    apiUploadMock.mockResolvedValue({ url: 'http://cdn/paste.png' })
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    const preventDefault = vi.fn()
    const event = {
      preventDefault,
      clipboardData: { items: [{ type: 'image/png', getAsFile: () => imageFile() }] },
    }
    await u.handlePaste(event as unknown as ClipboardEvent)
    expect(preventDefault).toHaveBeenCalled()
    expect(u.imageForm.src).toBe('http://cdn/paste.png')
    expect(u.showImageDialog.value).toBe(true)
  })

  it('handlePaste: no image item and no remote url is a no-op', async () => {
    const { editor } = createFakeEditor()
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    const event = {
      preventDefault: vi.fn(),
      clipboardData: {
        items: [{ type: 'text/plain', getAsFile: () => null }],
        getData: () => '',
      },
    }
    await u.handlePaste(event as unknown as ClipboardEvent)
    expect(apiUploadMock).not.toHaveBeenCalled()
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('submitImageDialog: inserts new figure when no figure active', () => {
    const { editor, record } = createFakeEditor()
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    u.imageForm.src = 'http://x/y.png'
    u.imageForm.alt = 'alt'
    u.submitImageDialog()
    expect(record.calls.some((c) => c[0] === 'setFigureImage')).toBe(true)
    expect(u.showImageDialog.value).toBe(false)
    expect(u.imageForm.src).toBe('')
  })

  it('submitImageDialog: updates existing figure when figure active', () => {
    const { editor, record } = createFakeEditor({ active: { figureImage: true } })
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    u.imageForm.src = 'http://x/y.png'
    u.submitImageDialog()
    expect(record.calls.some((c) => c[0] === 'updateFigureImage')).toBe(true)
  })

  it('cancelImageDialog: closes and resets form', () => {
    const { editor } = createFakeEditor()
    const u = useEditorImageUpload(editor, ref('/api/upload'))
    u.imageForm.src = 'http://x/y.png'
    u.showImageDialog.value = true
    u.cancelImageDialog()
    expect(u.showImageDialog.value).toBe(false)
    expect(u.imageForm.src).toBe('')
  })
})

describe('useEditorImageUpload (remote re-host on paste/drop)', () => {
  const LOCAL_URL = '/api/v1/kb/media/abc/local.png'

  beforeEach(() => {
    apiUploadMock.mockReset()
    apiMock.mockReset()
    messageMock.error.mockReset()
    messageMock.warning.mockReset()
  })

  it('handlePaste: text/html <img> with external src re-hosts via remote endpoint', async () => {
    const { editor } = createFakeEditor()
    apiMock.mockResolvedValue({ url: LOCAL_URL })
    const u = useEditorImageUpload(editor, ref('/api/v1/kb/articles/1/media'))
    const preventDefault = vi.fn()
    const event = {
      preventDefault,
      clipboardData: {
        items: [],
        getData: (kind: string) =>
          kind === 'text/html' ? '<p><img src="https://site.example.com/pic.png"></p>' : '',
      },
    }
    await u.handlePaste(event as unknown as ClipboardEvent)
    expect(preventDefault).toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledWith('/api/v1/kb/articles/1/media/remote', {
      method: 'POST',
      body: { url: 'https://site.example.com/pic.png' },
    })
    expect(u.imageForm.src).toBe(LOCAL_URL)
    expect(u.showImageDialog.value).toBe(true)
  })

  it('handlePaste: bare external URL in text/plain re-hosts', async () => {
    const { editor } = createFakeEditor()
    apiMock.mockResolvedValue({ url: LOCAL_URL })
    const u = useEditorImageUpload(editor, ref('/api/v1/kb/articles/1/media'))
    const event = {
      preventDefault: vi.fn(),
      clipboardData: {
        items: [],
        getData: (kind: string) =>
          kind === 'text/plain' ? 'https://cdn.example.com/x.jpg' : '',
      },
    }
    await u.handlePaste(event as unknown as ClipboardEvent)
    expect(apiMock).toHaveBeenCalledTimes(1)
    expect(u.imageForm.src).toBe(LOCAL_URL)
  })

  it('handlePaste: internal /api/v1/ URL does NOT trigger remote (left to TipTap)', async () => {
    const { editor } = createFakeEditor()
    const u = useEditorImageUpload(editor, ref('/api/v1/kb/articles/1/media'))
    const event = {
      preventDefault: vi.fn(),
      clipboardData: {
        items: [],
        getData: (kind: string) =>
          kind === 'text/html'
            ? '<img src="/api/v1/kb/media/abc/already-local.png">'
            : '',
      },
    }
    await u.handlePaste(event as unknown as ClipboardEvent)
    expect(apiMock).not.toHaveBeenCalled()
    expect(u.showImageDialog.value).toBe(false)
  })

  it('handleDrop: text/html external img re-hosts (drag <img> from another page)', async () => {
    const { editor } = createFakeEditor()
    apiMock.mockResolvedValue({ url: LOCAL_URL })
    const u = useEditorImageUpload(editor, ref('/api/v1/kb/articles/1/media'))
    const event = {
      dataTransfer: {
        files: [],
        getData: (kind: string) =>
          kind === 'text/html' ? '<img src="https://other.example.com/drag.png">' : '',
      },
    }
    await u.handleDrop(event as unknown as DragEvent)
    expect(apiMock).toHaveBeenCalledTimes(1)
    expect(u.imageForm.src).toBe(LOCAL_URL)
  })

  it('handlePaste: remote endpoint failure shows toast and inserts nothing', async () => {
    const { editor } = createFakeEditor()
    apiMock.mockRejectedValue({ response: { status: 422 } })
    const u = useEditorImageUpload(editor, ref('/api/v1/kb/articles/1/media'))
    const event = {
      preventDefault: vi.fn(),
      clipboardData: {
        items: [],
        getData: (kind: string) =>
          kind === 'text/html' ? '<img src="https://unreachable.example.com/x.png">' : '',
      },
    }
    await u.handlePaste(event as unknown as ClipboardEvent)
    expect(messageMock.error).toHaveBeenCalledWith('editor.imageFetchFailed')
    expect(u.showImageDialog.value).toBe(false)
  })

  it('handlePaste: remote 413 shows imageTooLarge', async () => {
    const { editor } = createFakeEditor()
    apiMock.mockRejectedValue({ response: { status: 413 } })
    const u = useEditorImageUpload(editor, ref('/api/v1/kb/articles/1/media'))
    const event = {
      preventDefault: vi.fn(),
      clipboardData: {
        items: [],
        getData: (kind: string) =>
          kind === 'text/html' ? '<img src="https://big.example.com/huge.png">' : '',
      },
    }
    await u.handlePaste(event as unknown as ClipboardEvent)
    expect(messageMock.error).toHaveBeenCalledWith('editor.imageTooLarge')
  })

  it('handlePaste: remote re-host disabled without uploadEndpoint (article not saved)', async () => {
    const { editor } = createFakeEditor()
    const u = useEditorImageUpload(editor, ref(undefined))
    const event = {
      preventDefault: vi.fn(),
      clipboardData: {
        items: [],
        getData: (kind: string) =>
          kind === 'text/html' ? '<img src="https://site.example.com/p.png">' : '',
      },
    }
    await u.handlePaste(event as unknown as ClipboardEvent)
    expect(messageMock.warning).toHaveBeenCalledWith('editor.imageUploadDisabled')
    expect(apiMock).not.toHaveBeenCalled()
  })
})
