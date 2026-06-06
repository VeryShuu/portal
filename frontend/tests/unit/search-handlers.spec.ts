import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, computed } from 'vue'

const h = vi.hoisted(() => ({
  push: vi.fn(),
  openLink: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: h.push }) }))
vi.mock('@/stores/links', () => ({ useLinksStore: () => ({ openLink: h.openLink }) }))
vi.mock('@/router', () => ({ ROUTES: { NEWS: '/news' } }))

import { useSearchNavigation } from '@/composables/useSearchNavigation'
import { useSearchRecent } from '@/composables/useSearchRecent'

function setup(over: Record<string, unknown> = {}) {
  const newsResults = ref(over.newsResults ?? [])
  const linkResults = ref(over.linkResults ?? [])
  const bookmarkResults = ref(over.bookmarkResults ?? [])
  const kbResults = ref(over.kbResults ?? [])
  const userResults = ref(over.userResults ?? [])
  const offsetLinks = computed(() => (newsResults.value as unknown[]).length)
  const offsetBookmarks = computed(
    () => (newsResults.value as unknown[]).length + (linkResults.value as unknown[]).length,
  )
  const offsetKb = computed(
    () =>
      (newsResults.value as unknown[]).length +
      (linkResults.value as unknown[]).length +
      (bookmarkResults.value as unknown[]).length,
  )
  const offsetUsers = computed(
    () =>
      (newsResults.value as unknown[]).length +
      (linkResults.value as unknown[]).length +
      (bookmarkResults.value as unknown[]).length +
      (kbResults.value as unknown[]).length,
  )
  const totalCount = computed(
    () =>
      (newsResults.value as unknown[]).length +
      (linkResults.value as unknown[]).length +
      (bookmarkResults.value as unknown[]).length +
      (kbResults.value as unknown[]).length +
      (userResults.value as unknown[]).length,
  )
  const ctx = {
    query: ref((over.query as string) ?? ''),
    isCommandMode: ref((over.isCommandMode as boolean) ?? false),
    filteredCommands: ref(over.filteredCommands ?? []),
    recent: ref(over.recent ?? []),
    newsResults,
    linkResults,
    bookmarkResults,
    kbResults,
    userResults,
    offsetLinks,
    offsetBookmarks,
    offsetKb,
    offsetUsers,
    totalCount,
    activeIndex: ref((over.activeIndex as number) ?? 0),
    close: vi.fn(),
    saveRecent: vi.fn(),
  }
  return { ctx, nav: useSearchNavigation(ctx as never) }
}

beforeEach(() => vi.clearAllMocks())

describe('useSearchNavigation.move', () => {
  it('wraps within commands in command mode', () => {
    const { ctx, nav } = setup({
      isCommandMode: true,
      filteredCommands: [{ id: 'a', action: vi.fn() }, { id: 'b', action: vi.fn() }],
    })
    nav.move(1)
    expect(ctx.activeIndex.value).toBe(1)
    nav.move(1)
    expect(ctx.activeIndex.value).toBe(0)
    nav.move(-1)
    expect(ctx.activeIndex.value).toBe(1)
  })

  it('does nothing in command mode with no commands', () => {
    const { ctx, nav } = setup({ isCommandMode: true, filteredCommands: [] })
    nav.move(1)
    expect(ctx.activeIndex.value).toBe(0)
  })

  it('wraps within total result count', () => {
    const { ctx, nav } = setup({ query: 'x', newsResults: [{ id: 'n1' }, { id: 'n2' }] })
    nav.move(-1)
    expect(ctx.activeIndex.value).toBe(1)
  })

  it('does nothing when there are no results', () => {
    const { ctx, nav } = setup({ query: 'x' })
    nav.move(1)
    expect(ctx.activeIndex.value).toBe(0)
  })
})

describe('useSearchNavigation.pick* handlers', () => {
  it('pickRecent fills query and resets index', () => {
    const { ctx, nav } = setup({ activeIndex: 5 })
    nav.pickRecent('hello')
    expect(ctx.query.value).toBe('hello')
    expect(ctx.activeIndex.value).toBe(0)
  })

  it('pickNews saves, navigates and closes', () => {
    const { ctx, nav } = setup({ query: 'q' })
    nav.pickNews({ id: 'n1' } as never)
    expect(ctx.saveRecent).toHaveBeenCalledWith('q')
    expect(h.push).toHaveBeenCalledWith('/news/n1')
    expect(ctx.close).toHaveBeenCalled()
  })

  it('pickLink opens via the links store', () => {
    const { ctx, nav } = setup()
    const link = { id: 'l1', title: 'L' }
    nav.pickLink(link as never)
    expect(h.openLink).toHaveBeenCalledWith(link)
    expect(ctx.close).toHaveBeenCalled()
  })

  it('pickBookmark opens safe http urls in a new tab', () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    const { ctx, nav } = setup()
    nav.pickBookmark({ id: 'b1', url: 'https://example.com' } as never)
    expect(openSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer')
    expect(ctx.close).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('pickBookmark blocks unsafe urls', () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    const { ctx, nav } = setup()
    nav.pickBookmark({ id: 'b1', url: 'javascript:alert(1)' } as never)
    expect(openSpy).not.toHaveBeenCalled()
    expect(ctx.close).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('pickKb routes only to internal paths', () => {
    const { nav } = setup()
    nav.pickKb({ id: 'a1', url: '/kb/article/1', title: 'A' } as never)
    expect(h.push).toHaveBeenCalledWith('/kb/article/1')
  })

  it('pickKb ignores external urls but still closes', () => {
    const { ctx, nav } = setup()
    nav.pickKb({ id: 'a1', url: 'https://evil.com', title: 'A' } as never)
    expect(h.push).not.toHaveBeenCalled()
    expect(ctx.close).toHaveBeenCalled()
  })

  it('pickUser navigates to the profile route', () => {
    const { nav } = setup()
    nav.pickUser({ id: 'u1', full_name: 'U' } as never)
    expect(h.push).toHaveBeenCalledWith({ name: 'user-profile', params: { id: 'u1' } })
  })
})

describe('useSearchNavigation.pickActive', () => {
  it('runs the active command in command mode', () => {
    const action = vi.fn()
    const { nav } = setup({
      isCommandMode: true,
      filteredCommands: [{ id: 'a', action }],
      activeIndex: 0,
    })
    nav.pickActive()
    expect(action).toHaveBeenCalled()
  })

  it('picks the highlighted recent query when input is empty', () => {
    const { ctx, nav } = setup({ recent: ['foo', 'bar'], activeIndex: 1 })
    nav.pickActive()
    expect(ctx.query.value).toBe('bar')
  })

  it('routes to news for an index in the news range', () => {
    const { nav } = setup({ query: 'q', newsResults: [{ id: 'n1' }], activeIndex: 0 })
    nav.pickActive()
    expect(h.push).toHaveBeenCalledWith('/news/n1')
  })

  it('routes to a link for an index in the links range', () => {
    const { nav } = setup({
      query: 'q',
      newsResults: [{ id: 'n1' }],
      linkResults: [{ id: 'l1' }],
      activeIndex: 1,
    })
    nav.pickActive()
    expect(h.openLink).toHaveBeenCalledWith({ id: 'l1' })
  })

  it('opens a bookmark for an index in the bookmarks range', () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    const { nav } = setup({
      query: 'q',
      bookmarkResults: [{ id: 'b1', url: 'https://ok.com' }],
      activeIndex: 0,
    })
    nav.pickActive()
    expect(openSpy).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('routes to kb for an index in the kb range', () => {
    const { nav } = setup({
      query: 'q',
      kbResults: [{ id: 'a1', url: '/kb/1', title: 'A' }],
      activeIndex: 0,
    })
    nav.pickActive()
    expect(h.push).toHaveBeenCalledWith('/kb/1')
  })

  it('routes to a user for an index in the users range', () => {
    const { nav } = setup({
      query: 'q',
      userResults: [{ id: 'u1', full_name: 'U' }],
      activeIndex: 0,
    })
    nav.pickActive()
    expect(h.push).toHaveBeenCalledWith({ name: 'user-profile', params: { id: 'u1' } })
  })
})

describe('useSearchRecent', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('starts empty when storage is empty', () => {
    const { recent } = useSearchRecent()
    expect(recent.value).toEqual([])
  })

  it('reads existing list from storage, filtering non-strings', () => {
    localStorage.setItem('gs-recent', JSON.stringify(['a', 1, 'b', null]))
    const { recent } = useSearchRecent()
    expect(recent.value).toEqual(['a', 'b'])
  })

  it('returns empty on malformed storage', () => {
    localStorage.setItem('gs-recent', '{not json')
    const { recent } = useSearchRecent()
    expect(recent.value).toEqual([])
  })

  it('saveRecent ignores blank queries', () => {
    const { recent, saveRecent } = useSearchRecent()
    saveRecent('   ')
    expect(recent.value).toEqual([])
  })

  it('saveRecent prepends, de-duplicates and caps at 8', () => {
    const { recent, saveRecent } = useSearchRecent()
    for (const q of ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i']) saveRecent(q)
    expect(recent.value).toHaveLength(8)
    expect(recent.value[0]).toBe('i')
    saveRecent('a')
    expect(recent.value[0]).toBe('a')
    expect(recent.value.filter(x => x === 'a')).toHaveLength(1)
  })
})
