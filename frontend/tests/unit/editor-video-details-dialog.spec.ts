import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

const messageMock = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }
vi.mock('naive-ui', () => ({
  useMessage: () => messageMock,
}))

import { useEditorVideoDialog } from '@/components/editor/useEditorVideoDialog'
import { useEditorDetailsDialog } from '@/components/editor/useEditorDetailsDialog'
import type { Editor } from '@tiptap/vue-3'

interface ChainRecord {
  calls: Array<[string, ...unknown[]]>
}

function makeChain(record: ChainRecord) {
  const handler: ProxyHandler<Record<string, unknown>> = {
    get(_t, prop: string) {
      if (prop === 'run') return () => true
      if (prop === 'command') {
        return (fn: (p: { tr: unknown }) => boolean) => {
          record.calls.push(['command'])
          fn({ tr: { setNodeMarkup: (...a: unknown[]) => record.calls.push(['setNodeMarkup', ...a]) } })
          return proxy
        }
      }
      return (...args: unknown[]) => {
        record.calls.push([prop, ...args])
        return proxy
      }
    },
  }
  const proxy = new Proxy({}, handler)
  return proxy
}

describe('useEditorVideoDialog (RE-0 characterizing)', () => {
  beforeEach(() => {
    messageMock.error.mockReset()
  })

  it('insertVideo: extracts src from iframe embed and inserts', () => {
    const setIframe = vi.fn(() => true)
    const editor = ref<Editor | undefined>({ commands: { setIframe } } as unknown as Editor)
    const v = useEditorVideoDialog(editor)
    v.videoUrl.value = '<iframe src="https://youtube.com/embed/abc"></iframe>'
    v.insertVideo()
    expect(setIframe).toHaveBeenCalledWith({ src: 'https://youtube.com/embed/abc', title: '' })
    expect(v.showVideoDialog.value).toBe(false)
    expect(v.videoUrl.value).toBe('')
  })

  it('insertVideo: plain URL passed through as src', () => {
    const setIframe = vi.fn(() => true)
    const editor = ref<Editor | undefined>({ commands: { setIframe } } as unknown as Editor)
    const v = useEditorVideoDialog(editor)
    v.videoUrl.value = '  https://vimeo.com/123  '
    v.insertVideo()
    expect(setIframe).toHaveBeenCalledWith({ src: 'https://vimeo.com/123', title: '' })
  })

  it('insertVideo: empty url is a no-op', () => {
    const setIframe = vi.fn(() => true)
    const editor = ref<Editor | undefined>({ commands: { setIframe } } as unknown as Editor)
    const v = useEditorVideoDialog(editor)
    v.videoUrl.value = '   '
    v.insertVideo()
    expect(setIframe).not.toHaveBeenCalled()
  })

  it('insertVideo: invalid url (setIframe false) shows error and keeps dialog', () => {
    const setIframe = vi.fn(() => false)
    const editor = ref<Editor | undefined>({ commands: { setIframe } } as unknown as Editor)
    const v = useEditorVideoDialog(editor)
    v.showVideoDialog.value = true
    v.videoUrl.value = 'not-a-video'
    v.insertVideo()
    expect(messageMock.error).toHaveBeenCalledWith('editor.invalidVideoUrl')
    expect(v.showVideoDialog.value).toBe(true)
  })
})

describe('useEditorDetailsDialog (RE-0 characterizing)', () => {
  it('openDetailsDialog: clears summary and opens', () => {
    const editor = ref<Editor | undefined>(undefined)
    const d = useEditorDetailsDialog(editor)
    d.detailsSummary.value = 'old'
    d.openDetailsDialog()
    expect(d.detailsSummary.value).toBe('')
    expect(d.showDetailsDialog.value).toBe(true)
  })

  it('insertDetails: inserts trimmed summary and closes', () => {
    const record: ChainRecord = { calls: [] }
    const editor = ref<Editor | undefined>({ chain: () => makeChain(record) } as unknown as Editor)
    const d = useEditorDetailsDialog(editor)
    d.detailsSummary.value = '  Spoiler  '
    d.showDetailsDialog.value = true
    d.insertDetails()
    const insert = record.calls.find((c) => c[0] === 'insertDetails')
    expect(insert).toEqual(['insertDetails', 'Spoiler'])
    expect(d.showDetailsDialog.value).toBe(false)
    expect(d.detailsSummary.value).toBe('')
  })

  it('preventDetailsToggle: no summary ancestor is a no-op', () => {
    const editor = ref<Editor | undefined>(undefined)
    const d = useEditorDetailsDialog(editor)
    const preventDefault = vi.fn()
    d.preventDetailsToggle({ target: { closest: () => null }, preventDefault } as unknown as MouseEvent)
    expect(preventDefault).not.toHaveBeenCalled()
  })

  it('preventDetailsToggle: summary without details element is a no-op', () => {
    const editor = ref<Editor | undefined>(undefined)
    const d = useEditorDetailsDialog(editor)
    const preventDefault = vi.fn()
    const summary = { closest: () => null }
    const target = { closest: (sel: string) => (sel === 'summary' ? summary : null) }
    d.preventDetailsToggle({ target, preventDefault } as unknown as MouseEvent)
    expect(preventDefault).not.toHaveBeenCalled()
  })

  it('preventDetailsToggle: toggles open attribute of details node', () => {
    const record: ChainRecord = { calls: [] }
    const detailsEl = {}
    const summary = { closest: () => detailsEl }
    const target = { closest: (sel: string) => (sel === 'summary' ? summary : null) }

    const node = { type: { name: 'details' }, attrs: { open: false } }
    const resolved = {
      depth: 1,
      node: (_d: number) => node,
      before: (_d: number) => 5,
    }
    const editor = ref<Editor | undefined>({
      view: { posAtDOM: () => 5 },
      state: { doc: { resolve: () => resolved } },
      chain: () => makeChain(record),
    } as unknown as Editor)

    const d = useEditorDetailsDialog(editor)
    const preventDefault = vi.fn()
    d.preventDetailsToggle({ target, preventDefault } as unknown as MouseEvent)
    expect(preventDefault).toHaveBeenCalled()
    const setMarkup = record.calls.find((c) => c[0] === 'setNodeMarkup')
    expect(setMarkup).toBeTruthy()
    expect(setMarkup![3]).toEqual({ open: true })
  })
})
