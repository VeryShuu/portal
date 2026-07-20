import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref, nextTick } from 'vue'

const articlesQueryDataRef = ref<any>(null)
const articlesQueryLoadingRef = ref(false)
const tagsQueryDataRef = ref<any>(null)

vi.mock('../../src/queries/kb', () => ({
  useKbArticlesQuery: () => ({ data: articlesQueryDataRef, isLoading: articlesQueryLoadingRef }),
  useKbTagsQuery: () => ({ data: tagsQueryDataRef }),
}))

vi.mock('../../src/composables/useDebounceFn', () => ({
  useDebounceFn: (fn: (...args: any[]) => void) => {
    function debounced(...args: any[]) {
      fn(...args)
    }
    debounced.cancel = () => {}
    debounced.flush = () => {}
    return debounced
  },
}))

import { useKbArticleListing } from '../../src/composables/useKbArticleListing'

describe('useKbArticleListing (src/composables)', () => {
  beforeEach(() => {
    articlesQueryDataRef.value = null
    articlesQueryLoadingRef.value = false
    tagsQueryDataRef.value = null
  })

  it('applies default page size and debounce when options are omitted', () => {
    const state = useKbArticleListing({ selectedSection: ref(null) })
    expect(state.pageSize).toBe(20)
  })

  it('honours explicit pageSize/debounceMs overrides', () => {
    const state = useKbArticleListing({ selectedSection: ref(null), pageSize: 50, debounceMs: 100 })
    expect(state.pageSize).toBe(50)
  })

  it('resets page to 1 when selectedSection changes', async () => {
    const selectedSection = ref<string | null>('s1')
    const state = useKbArticleListing({ selectedSection })
    state.page.value = 5

    selectedSection.value = 's2'
    await nextTick()
    expect(state.page.value).toBe(1)
  })

  it('resets page to 1 when statusFilter changes', async () => {
    const state = useKbArticleListing({ selectedSection: ref(null) })
    state.page.value = 3
    state.statusFilter.value = 'draft'
    await nextTick()
    expect(state.page.value).toBe(1)
  })

  it('resets page to 1 when tagFilter changes', async () => {
    const state = useKbArticleListing({ selectedSection: ref(null) })
    state.page.value = 7
    state.tagFilter.value = 'slug-1'
    await nextTick()
    expect(state.page.value).toBe(1)
  })

  it('maps articles data items/total onto computed values', () => {
    articlesQueryDataRef.value = { items: [{ id: 'a1' }, { id: 'a2' }], total: 2 }
    const state = useKbArticleListing({ selectedSection: ref(null) })
    expect(state.articles.value).toHaveLength(2)
    expect(state.total.value).toBe(2)
  })

  it('reflects the loading flag from the underlying query', () => {
    articlesQueryLoadingRef.value = true
    const state = useKbArticleListing({ selectedSection: ref(null) })
    expect(state.loading.value).toBe(true)
  })

  it('builds tagOptions from allTags with name/slug pairs', () => {
    tagsQueryDataRef.value = [{ name: 'Vue', slug: 'vue' }, { name: 'Go', slug: 'go' }]
    const state = useKbArticleListing({ selectedSection: ref(null) })
    expect(state.tagOptions.value).toEqual([
      { label: 'Vue', value: 'vue' },
      { label: 'Go', value: 'go' },
    ])
  })

  it('selectTag toggles tagFilter between slug and null and resets page', () => {
    const state = useKbArticleListing({ selectedSection: ref(null) })
    state.page.value = 4

    state.selectTag('vue')
    expect(state.tagFilter.value).toBe('vue')
    expect(state.page.value).toBe(1)

    state.selectTag('vue')
    expect(state.tagFilter.value).toBe(null)
  })

  it('onSearchInput triggers the (synchronously-stubbed) debounced search and resets page', () => {
    const state = useKbArticleListing({ selectedSection: ref(null) })
    state.page.value = 4
    state.searchQuery.value = 'hello'
    state.onSearchInput()

    // debouncedQuery is internal; assert side effect on page via the stubbed debounce.
    expect(state.page.value).toBe(1)
  })
})
