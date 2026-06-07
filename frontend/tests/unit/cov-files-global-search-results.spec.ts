import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick, ref, type Ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'

const mockRunGlobalSearch = vi.fn()
const mockCancel = vi.fn()

const mockLinksStore = {
  links: [] as Array<{ title: string; description?: string | null; category?: string | null }>,
  bookmarks: [] as Array<{ title: string; url: string }>,
  loadLinks: vi.fn(),
  loadBookmarks: vi.fn(),
}

vi.mock('../../src/composables/useDebounceFn', () => ({
  useDebounceFn: (fn: (...args: any[]) => Promise<void>) => {
    const wrapped = ((...args: any[]) => fn(...args)) as ((...args: any[]) => Promise<void>) & { cancel: () => void }
    wrapped.cancel = mockCancel
    return wrapped
  },
}))

vi.mock('../../src/composables/useGlobalSearch', () => ({
  runGlobalSearch: mockRunGlobalSearch,
}))

vi.mock('../../src/stores/links', () => ({
  useLinksStore: () => mockLinksStore,
}))

type ResultsApi = Awaited<ReturnType<typeof setupHost>>['api']

async function flush() {
  await Promise.resolve()
  await nextTick()
}

async function setupHost(initialQuery = ''): Promise<{
  api: ResultsApi
  query: Ref<string>
  wrapper: VueWrapper
}> {
  const query = ref(initialQuery)
  const { useGlobalSearchResults } = await import('../../src/composables/useGlobalSearchResults')

  let api: any = null
  const Host = defineComponent({
    setup() {
      api = useGlobalSearchResults(query)
      return () => h('div')
    },
  })

  const wrapper = mount(Host)

  return {
    api,
    query,
    wrapper,
  }
}

describe('useGlobalSearchResults', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLinksStore.links = []
    mockLinksStore.bookmarks = []
  })

  it('computes link/bookmark results and handles empty query', async () => {
    mockLinksStore.links = [
      { title: 'Portal', description: 'Main dashboard', category: 'Internal' },
      { title: 'News room', description: null, category: 'Media' },
    ]
    mockLinksStore.bookmarks = [
      { title: 'Portal Home', url: 'https://portal.local' },
      { title: 'External', url: 'https://example.com' },
    ]

    mockRunGlobalSearch.mockResolvedValueOnce({ news: [], kb: [], users: [] })

    const { api, query } = await setupHost('')
    expect(api.linkResults.value).toEqual([])
    expect(api.bookmarkResults.value).toEqual([])

    query.value = 'port'
    await flush()

    expect(api.linkResults.value.map((x) => x.title)).toEqual(['Portal'])
    expect(api.bookmarkResults.value.map((x) => x.title)).toEqual(['Portal Home'])
  })

  it('runs search when query is non-empty and stores results', async () => {
    mockRunGlobalSearch.mockResolvedValueOnce({
      news: [{ id: 'n1' }],
      kb: [{ id: 'k1', type: 'article' }],
      users: [{ id: 'u1' }],
    })

    const { api, query } = await setupHost('')

    query.value = 'start'
    await flush()

    expect(api.loading.value).toBe(false)
    expect(api.newsResults.value).toHaveLength(1)
    expect(api.kbResults.value).toHaveLength(1)
    expect(api.userResults.value).toHaveLength(1)
    expect(mockRunGlobalSearch).toHaveBeenCalledTimes(1)

    const [, opts] = mockRunGlobalSearch.mock.calls[0]
    expect(opts.newsLimit).toBe(6)
    expect(opts.kbLimit).toBe(6)
    expect(opts.userLimit).toBe(5)
    expect(opts.signal).toBeInstanceOf(AbortSignal)

    query.value = '   '
    await flush()

    expect(mockCancel).toHaveBeenCalledTimes(1)
    expect(api.newsResults.value).toEqual([])
    expect(api.kbResults.value).toEqual([])
    expect(api.userResults.value).toEqual([])
    expect(api.loading.value).toBe(false)
  })

  it('aborts in-flight request on query change and ignores AbortError', async () => {
    const signals: AbortSignal[] = []
    let resolveFirst: ((value: any) => void) | null = null

    mockRunGlobalSearch
      .mockImplementationOnce((_q: string, opts: { signal: AbortSignal }) => {
        signals.push(opts.signal)
        return new Promise((resolve) => {
          resolveFirst = resolve
        })
      })
      .mockResolvedValueOnce({ news: [], kb: [], users: [] })

    const { query } = await setupHost('')

    query.value = 'alpha'
    await flush()

    query.value = 'beta'
    await flush()

    expect(signals[0].aborted).toBe(true)

    resolveFirst?.({ news: [{ id: 'late' }], kb: [{ id: 'late' }], users: [{ id: 'late' }] })
    await flush()
  })

  it('warns on non-abort search error and ignores abort-like errors', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    mockRunGlobalSearch.mockRejectedValueOnce({ name: 'AbortError' })
    const { query } = await setupHost('')

    query.value = 'one'
    await flush()

    expect(warnSpy).not.toHaveBeenCalled()

    mockRunGlobalSearch.mockRejectedValueOnce(new Error('network'))
    query.value = 'two'
    await flush()

    expect(warnSpy).toHaveBeenCalledTimes(1)
    warnSpy.mockRestore()
  })

  it('ensureCatalogLoaded loads only empty catalogs and unmount cancels/aborts', async () => {
    const signals: AbortSignal[] = []

    mockLinksStore.links = []
    mockLinksStore.bookmarks = [{ title: 'Saved', url: 'https://saved.local' }]

    mockRunGlobalSearch.mockImplementationOnce((_q: string, opts: { signal: AbortSignal }) => {
      signals.push(opts.signal)
      return new Promise(() => {})
    })

    const { api, wrapper, query } = await setupHost('')

    query.value = 'qq'
    await flush()

    api.ensureCatalogLoaded()
    expect(mockLinksStore.loadLinks).toHaveBeenCalledTimes(1)
    expect(mockLinksStore.loadBookmarks).not.toHaveBeenCalled()

    wrapper.unmount()

    expect(mockCancel).toHaveBeenCalled()
    expect(signals[0].aborted).toBe(true)
  })
})
