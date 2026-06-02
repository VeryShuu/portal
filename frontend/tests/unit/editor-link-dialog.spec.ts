import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

const fetchArticlesMock = vi.fn()
vi.mock('@/api/kb', () => ({
  fetchArticles: (...args: unknown[]) => fetchArticlesMock(...args),
}))

import { useEditorLinkDialog } from '@/components/editor/useEditorLinkDialog'
import type { Editor } from '@tiptap/vue-3'

interface ChainRecord {
  calls: Array<[string, ...unknown[]]>
  ran: boolean
}

function makeChain(record: ChainRecord) {
  const chain: Record<string, unknown> = {}
  const handler: ProxyHandler<Record<string, unknown>> = {
    get(_t, prop: string) {
      if (prop === 'run') {
        return () => {
          record.ran = true
          return true
        }
      }
      return (...args: unknown[]) => {
        record.calls.push([prop, ...args])
        return proxy
      }
    },
  }
  const proxy = new Proxy(chain, handler)
  return proxy
}

function createFakeEditor(opts: {
  active?: Record<string, boolean>
  attrs?: Record<string, unknown>
  selectedText?: string
} = {}) {
  const record: ChainRecord = { calls: [], ran: false }
  const selectedText = opts.selectedText ?? ''
  const from = 0
  const to = selectedText.length
  const editor = {
    isActive: vi.fn((name: string) => Boolean(opts.active?.[name])),
    getAttributes: vi.fn(() => opts.attrs ?? {}),
    chain: vi.fn(() => makeChain(record)),
    state: {
      selection: { from, to },
      doc: { textBetween: vi.fn(() => selectedText) },
    },
  } as unknown as Editor
  return { editor: ref<Editor | undefined>(editor), record }
}

describe('useEditorLinkDialog (RE-0 characterizing)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    fetchArticlesMock.mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('validateUrl: rejects unsupported scheme, accepts http/mailto/tel/relative', () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    d.onLinkUrlChange('javascript:alert(1)')
    expect(d.linkUrlError.value).toBe('editor.link.errorScheme')
    expect(d.linkUrlStatus.value).toBe('error')

    d.onLinkUrlChange('https://example.com')
    expect(d.linkUrlError.value).toBe('')
    d.onLinkUrlChange('mailto:a@b.com')
    expect(d.linkUrlError.value).toBe('')
    d.onLinkUrlChange('/kb/articles/x')
    expect(d.linkUrlError.value).toBe('')
    d.onLinkUrlChange('')
    expect(d.linkUrlError.value).toBe('')
  })

  it('onLinkUrlChange: external URL auto-toggles newTab+nofollow once (new link)', () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    d.onLinkUrlChange('https://external.example.com')
    expect(d.linkForm.newTab).toBe(true)
    expect(d.linkForm.nofollow).toBe(true)

    d.linkForm.newTab = false
    d.linkForm.nofollow = false
    d.onLinkUrlChange('https://another.example.com')
    expect(d.linkForm.newTab).toBe(false)
    expect(d.linkForm.nofollow).toBe(false)
  })

  it('onLinkUrlChange: internal (same-origin) URL does not auto-toggle', () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    d.onLinkUrlChange(`${window.location.origin}/kb/articles/abc`)
    expect(d.linkForm.newTab).toBe(false)
    expect(d.linkForm.nofollow).toBe(false)
  })

  it('canSubmitLink reflects url presence and validity', () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    expect(d.canSubmitLink.value).toBe(false)
    d.linkForm.url = 'https://ok.example.com'
    expect(d.canSubmitLink.value).toBe(true)
    d.onLinkUrlChange('javascript:bad')
    d.linkForm.url = 'javascript:bad'
    expect(d.canSubmitLink.value).toBe(false)
  })

  it('isInternalKbLink matches /kb/articles/<uuid>', () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    expect(d.isInternalKbLink('/kb/articles/123e4567-e89b-12d3-a456-426614174000')).toBe(true)
    expect(d.isInternalKbLink('/kb/articles/not-a-uuid')).toBe(false)
    expect(d.isInternalKbLink('https://example.com')).toBe(false)
  })

  it('openLinkDialog (new, with selection): prefills text, no editing flag', () => {
    const { editor } = createFakeEditor({ selectedText: 'selected words' })
    const d = useEditorLinkDialog(editor)
    d.openLinkDialog()
    expect(d.showLinkDialog.value).toBe(true)
    expect(d.linkEditingExisting.value).toBe(false)
    expect(d.linkForm.text).toBe('selected words')
    expect(d.linkShowTextField.value).toBe(false)
  })

  it('openLinkDialog (existing link): loads href/target/rel into form', () => {
    const { editor } = createFakeEditor({
      active: { link: true },
      attrs: { href: 'https://x.example.com', target: '_blank', rel: 'noopener nofollow' },
      selectedText: 'anchor',
    })
    const d = useEditorLinkDialog(editor)
    d.openLinkDialog()
    expect(d.linkEditingExisting.value).toBe(true)
    expect(d.linkForm.url).toBe('https://x.example.com')
    expect(d.linkForm.newTab).toBe(true)
    expect(d.linkForm.nofollow).toBe(true)
    expect(d.linkDialogTitle.value).toBe('editor.link.edit')
  })

  it('submitLink (new, with selection) sets link with rel/target', () => {
    const { editor, record } = createFakeEditor({ selectedText: 'anchor' })
    const d = useEditorLinkDialog(editor)
    d.openLinkDialog()
    d.linkForm.url = 'example.com'
    d.linkForm.newTab = true
    d.linkForm.nofollow = true
    d.submitLink()
    const setLink = record.calls.find((c) => c[0] === 'setLink')
    expect(setLink).toBeTruthy()
    expect(setLink![1]).toEqual({
      href: 'https://example.com',
      target: '_blank',
      rel: 'noopener noreferrer nofollow',
    })
    expect(d.showLinkDialog.value).toBe(false)
  })

  it('submitLink (new, no selection) inserts content node with link mark', () => {
    const { editor, record } = createFakeEditor({ selectedText: '' })
    const d = useEditorLinkDialog(editor)
    d.openLinkDialog()
    d.linkForm.url = 'https://example.com'
    d.linkForm.text = 'Click'
    d.submitLink()
    const insert = record.calls.find((c) => c[0] === 'insertContent')
    expect(insert).toBeTruthy()
    expect((insert![1] as { text: string }).text).toBe('Click')
  })

  it('submitLink rejects invalid URL and sets error', () => {
    const { editor, record } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    d.openLinkDialog()
    d.linkForm.url = 'javascript:evil'
    d.submitLink()
    expect(d.linkUrlError.value).toBe('editor.link.errorScheme')
    expect(record.ran).toBe(false)
    expect(d.showLinkDialog.value).toBe(true)
  })

  it('removeLink unsets link and closes dialog', () => {
    const { editor, record } = createFakeEditor({ active: { link: true }, attrs: { href: 'https://x.com' } })
    const d = useEditorLinkDialog(editor)
    d.openLinkDialog()
    d.removeLink()
    expect(record.calls.some((c) => c[0] === 'unsetLink')).toBe(true)
    expect(d.showLinkDialog.value).toBe(false)
  })

  it('closing dialog resets form state', async () => {
    const { editor } = createFakeEditor({ selectedText: 'foo' })
    const d = useEditorLinkDialog(editor)
    d.openLinkDialog()
    await nextTick()
    d.linkForm.url = 'https://x.com'
    d.showLinkDialog.value = false
    await nextTick()
    expect(d.linkForm.url).toBe('')
    expect(d.linkForm.text).toBe('')
    expect(d.linkEditingExisting.value).toBe(false)
  })

  it('KB search: debounced, populates results and resets active index', async () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    fetchArticlesMock.mockResolvedValue({ items: [{ id: 'a', title: 'Alpha' }, { id: 'b', title: 'Beta' }] })
    d.onKbSearchInput('al')
    expect(d.kbSearchQuery.value).toBe('al')
    expect(fetchArticlesMock).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(200)
    expect(fetchArticlesMock).toHaveBeenCalledTimes(1)
    expect(d.kbSearchResults.value).toHaveLength(2)
    expect(d.kbActiveIndex.value).toBe(0)
    expect(d.kbSearchLoading.value).toBe(false)
  })

  it('KB search: query below min length clears results without API call', async () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    d.onKbSearchInput('a')
    await vi.advanceTimersByTimeAsync(200)
    expect(fetchArticlesMock).not.toHaveBeenCalled()
    expect(d.kbSearchResults.value).toEqual([])
    expect(d.kbActiveIndex.value).toBe(-1)
  })

  it('KB search: API error clears results', async () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    fetchArticlesMock.mockRejectedValue(new Error('boom'))
    d.onKbSearchInput('query')
    await vi.advanceTimersByTimeAsync(200)
    expect(d.kbSearchResults.value).toEqual([])
    expect(d.kbActiveIndex.value).toBe(-1)
  })

  it('onKbKeydown: ArrowDown/ArrowUp wrap, Enter selects active article', async () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    fetchArticlesMock.mockResolvedValue({ items: [{ id: 'a', title: 'Alpha' }, { id: 'b', title: 'Beta' }] })
    d.onKbSearchInput('al')
    await vi.advanceTimersByTimeAsync(200)

    const prevent = vi.fn()
    d.onKbKeydown({ key: 'ArrowDown', preventDefault: prevent } as unknown as KeyboardEvent)
    expect(d.kbActiveIndex.value).toBe(1)
    d.onKbKeydown({ key: 'ArrowDown', preventDefault: prevent } as unknown as KeyboardEvent)
    expect(d.kbActiveIndex.value).toBe(0)
    d.onKbKeydown({ key: 'ArrowUp', preventDefault: prevent } as unknown as KeyboardEvent)
    expect(d.kbActiveIndex.value).toBe(1)

    d.onKbKeydown({ key: 'Enter', preventDefault: prevent } as unknown as KeyboardEvent)
    expect(d.linkForm.url).toBe('/kb/articles/b')
    expect(d.linkTab.value).toBe('url')
  })

  it('selectKbArticle: fills url + title, switches to url tab, disables auto-toggle', () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    d.selectKbArticle({ id: 'xyz', title: 'My Article' } as never)
    expect(d.linkForm.url).toBe('/kb/articles/xyz')
    expect(d.linkForm.text).toBe('My Article')
    expect(d.linkForm.newTab).toBe(false)
    expect(d.linkTab.value).toBe('url')
  })

  it('highlightKbMatch: splits title into matched/unmatched chunks', () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    d.kbSearchQuery.value = 'pha'
    const chunks = d.highlightKbMatch('Alphabet')
    expect(chunks).toEqual([
      { text: 'Al', match: false },
      { text: 'pha', match: true },
      { text: 'bet', match: false },
    ])
  })

  it('highlightKbMatch: empty query returns whole title unmatched', () => {
    const { editor } = createFakeEditor()
    const d = useEditorLinkDialog(editor)
    d.kbSearchQuery.value = ''
    expect(d.highlightKbMatch('Title')).toEqual([{ text: 'Title', match: false }])
  })
})
