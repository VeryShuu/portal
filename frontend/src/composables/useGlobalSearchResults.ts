import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import { useDebounceFn } from './useDebounceFn'
import { runGlobalSearch } from './useGlobalSearch'
import type { News } from '../api/news'
import type { ServiceLink, Bookmark } from '../api/links'
import type { SearchResultItem } from '../api/kb'
import type { UserPublic } from '../api/users'
import { useLinksStore } from '../stores/links'

const DEBOUNCE_MS = 250
const MAX_NEWS_RESULTS = 6
const MAX_LINK_RESULTS = 6
const MAX_BOOKMARK_RESULTS = 6
const MAX_KB_RESULTS = 6
const MAX_USER_RESULTS = 5

export function useGlobalSearchResults(query: Ref<string>) {
  const linksStore = useLinksStore()

  const loading = ref(false)
  const newsResults = ref<News[]>([])
  const kbResults = ref<SearchResultItem[]>([])
  const userResults = ref<UserPublic[]>([])

  const linkResults = computed<ServiceLink[]>(() => {
    const q = query.value.trim().toLowerCase()
    if (!q) return []
    return linksStore.links
      .filter((l) =>
        l.title.toLowerCase().includes(q) ||
        (l.description ?? '').toLowerCase().includes(q) ||
        (l.category ?? '').toLowerCase().includes(q),
      )
      .slice(0, MAX_LINK_RESULTS)
  })

  const bookmarkResults = computed<Bookmark[]>(() => {
    const q = query.value.trim().toLowerCase()
    if (!q) return []
    return linksStore.bookmarks
      .filter((b) =>
        b.title.toLowerCase().includes(q) ||
        b.url.toLowerCase().includes(q),
      )
      .slice(0, MAX_BOOKMARK_RESULTS)
  })

  let inflight: AbortController | null = null

  const runDebouncedSearch = useDebounceFn(async (q: string) => {
    const ctrl = new AbortController()
    inflight = ctrl
    try {
      const result = await runGlobalSearch(q, {
        newsLimit: MAX_NEWS_RESULTS,
        kbLimit: MAX_KB_RESULTS,
        userLimit: MAX_USER_RESULTS,
        signal: ctrl.signal,
      })
      if (ctrl.signal.aborted) return
      newsResults.value = result.news
      kbResults.value = result.kb
      userResults.value = result.users
    } catch (err) {
      const name = (err as { name?: string })?.name
      if (name === 'AbortError' || ctrl.signal.aborted) return
      console.warn('[GlobalSearch] search failed', err)
    } finally {
      if (inflight === ctrl) {
        inflight = null
        loading.value = false
      }
    }
  }, DEBOUNCE_MS)

  watch(query, (q) => {
    if (inflight) {
      inflight.abort()
      inflight = null
    }
    if (!q.trim()) {
      runDebouncedSearch.cancel()
      newsResults.value = []
      kbResults.value = []
      userResults.value = []
      loading.value = false
      return
    }
    loading.value = true
    runDebouncedSearch(q)
  })

  function ensureCatalogLoaded() {
    if (linksStore.links.length === 0) linksStore.loadLinks()
    if (linksStore.bookmarks.length === 0) linksStore.loadBookmarks()
  }

  onUnmounted(() => {
    runDebouncedSearch.cancel()
    if (inflight) inflight.abort()
  })

  return {
    loading,
    newsResults,
    linkResults,
    bookmarkResults,
    kbResults,
    userResults,
    ensureCatalogLoaded,
  }
}
