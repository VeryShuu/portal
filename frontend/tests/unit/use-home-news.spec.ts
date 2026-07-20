import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref, nextTick } from 'vue'

const mockPush = vi.fn()

// Refs that the stubbed query composables will expose so tests can mutate them.
const newsDataRef = ref<{ items: any[]; total: number } | null>(null)
const newsLoadingRef = ref(false)
const categoriesDataRef = ref<any[] | null>(null)

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

vi.mock('../../src/queries/news', () => ({
  useNewsListQuery: () => ({
    data: newsDataRef,
    isLoading: newsLoadingRef,
  }),
  useNewsCategoriesQuery: () => ({ data: categoriesDataRef }),
}))

describe('useHomeNews (src/composables)', () => {
  beforeEach(() => {
    mockPush.mockClear()
    newsDataRef.value = null
    newsLoadingRef.value = false
    categoriesDataRef.value = null
  })

  it('reports loading flag and empty defaults when query has no data yet', async () => {
    newsLoadingRef.value = true
    const { useHomeNews } = await import('../../src/composables/useHomeNews')
    const state = useHomeNews()

    expect(state.loadingNews.value).toBe(true)
    expect(state.news.value).toEqual([])
    expect(state.totalNews.value).toBe(0)
    expect(state.pinned.value).toEqual([])
    expect(state.regular.value).toEqual([])
    expect(state.categoriesMap.value).toEqual({})
  })

  it('splits items into pinned (max 1) and regular (max 4) buckets', async () => {
    newsDataRef.value = {
      items: [
        { id: '1', is_pinned: true },
        { id: '2', is_pinned: true },
        { id: '3', is_pinned: false },
        { id: '4', is_pinned: false },
        { id: '5', is_pinned: false },
        { id: '6', is_pinned: false },
        { id: '7', is_pinned: false },
      ],
      total: 7,
    }
    const { useHomeNews } = await import('../../src/composables/useHomeNews')
    const state = useHomeNews()

    expect(state.totalNews.value).toBe(7)
    expect(state.pinned.value.map((n: any) => n.id)).toEqual(['1'])
    expect(state.regular.value.map((n: any) => n.id)).toEqual(['3', '4', '5', '6'])
  })

  it('builds categoriesMap keyed by name with color value', async () => {
    categoriesDataRef.value = [
      { name: 'HR', color: '#ff0000' },
      { name: 'IT', color: '#00aa00' },
    ]
    const { useHomeNews } = await import('../../src/composables/useHomeNews')
    const state = useHomeNews()

    expect(state.categoriesMap.value).toEqual({ HR: '#ff0000', IT: '#00aa00' })
  })

  it('treats null categoriesQuery.data as empty map', async () => {
    categoriesDataRef.value = null
    const { useHomeNews } = await import('../../src/composables/useHomeNews')
    const state = useHomeNews()

    expect(state.categoriesMap.value).toEqual({})
  })

  it('reacts to data changes on the underlying query refs', async () => {
    const { useHomeNews } = await import('../../src/composables/useHomeNews')
    const state = useHomeNews()

    expect(state.news.value).toEqual([])
    newsDataRef.value = { items: [{ id: 'a', is_pinned: false }], total: 1 }
    await nextTick()
    expect(state.news.value).toHaveLength(1)
    expect(state.totalNews.value).toBe(1)
  })

  it('goToNews pushes the news detail route', async () => {
    const { useHomeNews } = await import('../../src/composables/useHomeNews')
    const state = useHomeNews()

    state.goToNews('abc-123')
    expect(mockPush).toHaveBeenCalledWith('/news/abc-123')
  })
})
