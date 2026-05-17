import type { Ref } from 'vue'
import { useRouter } from 'vue-router'
import { useLinksStore } from '../stores/links'
import type { News } from '../api/news'
import type { ServiceLink, Bookmark } from '../api/links'
import type { SearchResultItem } from '../api/kb'
import type { UserPublic } from '../api/users'
import { isSafeHttpUrl } from '../utils/url'
import { ROUTES } from '../router'

interface Command {
  id: string
  action: () => void
}

export interface UseSearchNavigationOptions {
  query: Ref<string>
  isCommandMode: Ref<boolean>
  filteredCommands: Ref<Command[]>
  recent: Ref<string[]>
  newsResults: Ref<News[]>
  linkResults: Ref<ServiceLink[]>
  bookmarkResults: Ref<Bookmark[]>
  kbResults: Ref<SearchResultItem[]>
  userResults: Ref<UserPublic[]>
  offsetLinks: Ref<number>
  offsetBookmarks: Ref<number>
  offsetKb: Ref<number>
  offsetUsers: Ref<number>
  totalCount: Ref<number>
  activeIndex: Ref<number>
  close: () => void
  saveRecent: (q: string) => void
}

function isSafeInternalPath(url: string): boolean {
  return url.startsWith('/') && !url.startsWith('//')
}

export function useSearchNavigation(opts: UseSearchNavigationOptions) {
  const router = useRouter()
  const linksStore = useLinksStore()

  function move(delta: number) {
    if (opts.isCommandMode.value) {
      const n = opts.filteredCommands.value.length
      if (n === 0) return
      opts.activeIndex.value = (opts.activeIndex.value + delta + n) % n
      return
    }
    const n = opts.totalCount.value
    if (n === 0) return
    opts.activeIndex.value = (opts.activeIndex.value + delta + n) % n
  }

  function pickRecent(q: string) {
    opts.query.value = q
    opts.activeIndex.value = 0
  }

  function pickNews(n: News) {
    opts.saveRecent(opts.query.value)
    router.push(`${ROUTES.NEWS}/${n.id}`)
    opts.close()
  }

  function pickLink(l: ServiceLink) {
    opts.saveRecent(opts.query.value)
    linksStore.openLink(l)
    opts.close()
  }

  function pickBookmark(b: Bookmark) {
    if (!isSafeHttpUrl(b.url)) return
    opts.saveRecent(opts.query.value)
    window.open(b.url, '_blank', 'noopener,noreferrer')
    opts.close()
  }

  function pickKb(a: SearchResultItem) {
    opts.saveRecent(opts.query.value)
    if (isSafeInternalPath(a.url)) {
      router.push(a.url)
    }
    opts.close()
  }

  function pickUser(u: UserPublic) {
    opts.saveRecent(opts.query.value)
    router.push({ name: 'user-profile', params: { id: u.id } })
    opts.close()
  }

  function pickActive() {
    if (opts.isCommandMode.value) {
      const cmd = opts.filteredCommands.value[opts.activeIndex.value]
      if (cmd) cmd.action()
      return
    }
    const q = opts.query.value.trim()
    if (!q) {
      const r = opts.recent.value[opts.activeIndex.value]
      if (r) pickRecent(r)
      return
    }
    const idx = opts.activeIndex.value
    if (idx < opts.offsetLinks.value) {
      const n = opts.newsResults.value[idx]
      if (n) pickNews(n)
    } else if (idx < opts.offsetBookmarks.value) {
      const l = opts.linkResults.value[idx - opts.offsetLinks.value]
      if (l) pickLink(l)
    } else if (idx < opts.offsetKb.value) {
      const b = opts.bookmarkResults.value[idx - opts.offsetBookmarks.value]
      if (b) pickBookmark(b)
    } else if (idx < opts.offsetUsers.value) {
      const a = opts.kbResults.value[idx - opts.offsetKb.value]
      if (a) pickKb(a)
    } else {
      const u = opts.userResults.value[idx - opts.offsetUsers.value]
      if (u) pickUser(u)
    }
  }

  return { move, pickActive, pickRecent, pickNews, pickLink, pickBookmark, pickKb, pickUser }
}
