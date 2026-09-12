import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  fetchLinks,
  fetchBookmarks,
  createBookmark,
  deleteBookmark,
  reorderBookmarks,
  reorderLinks,
  recordLinkClick,
  type ServiceLink,
  type Bookmark,
  type CreateBookmarkDto,
  type BookmarkReorderItem,
  type LinkReorderItem,
} from '../api/links'
import { isSafeHttpUrl, isInternalLinkUrl } from '../utils/url'
import { BASE_URL } from '../api'
import { i18n } from '../i18n'

export const useLinksStore = defineStore('links', () => {
  const links = ref<ServiceLink[]>([])
  const bookmarks = ref<Bookmark[]>([])
  const loadingLinks = ref(false)
  const loadingBookmarks = ref(false)
  const errorLinks = ref<string | null>(null)
  const errorBookmarks = ref<string | null>(null)

  const groupedLinks = computed(() => {
    const groups: Record<string, ServiceLink[]> = {}
    for (const link of links.value) {
      const key = link.category ?? i18n.global.t('links.other')
      if (!groups[key]) groups[key] = []
      groups[key].push(link)
    }
    return groups
  })

  async function loadLinks() {
    loadingLinks.value = true
    errorLinks.value = null
    try {
      const res = await fetchLinks()
      links.value = res.items
    } catch {
      errorLinks.value = 'network'
    } finally {
      loadingLinks.value = false
    }
  }

  async function loadBookmarks() {
    loadingBookmarks.value = true
    errorBookmarks.value = null
    try {
      const res = await fetchBookmarks()
      bookmarks.value = res.items
    } catch {
      errorBookmarks.value = 'network'
    } finally {
      loadingBookmarks.value = false
    }
  }

  async function addBookmark(dto: CreateBookmarkDto) {
    const bm = await createBookmark(dto)
    bookmarks.value.push(bm)
    return bm
  }

  async function removeBookmark(id: string) {
    await deleteBookmark(id)
    bookmarks.value = bookmarks.value.filter((b) => b.id !== id)
  }

  async function reorder(items: BookmarkReorderItem[]) {
    await reorderBookmarks(items)
    for (const item of items) {
      const bm = bookmarks.value.find((b) => b.id === item.id)
      if (bm) bm.sort_order = item.sort_order
    }
    bookmarks.value.sort((a, b) => a.sort_order - b.sort_order)
  }

  async function reorderLinksAction(items: LinkReorderItem[]) {
    await reorderLinks(items)
    for (const item of items) {
      const lnk = links.value.find((l) => l.id === item.id)
      if (lnk) lnk.sort_order = item.sort_order
    }
    links.value.sort(
      (a, b) => a.sort_order - b.sort_order || a.title.localeCompare(b.title),
    )
  }

  function addLink(link: ServiceLink): void {
    links.value.unshift(link)
  }

  function updateLinkItem(updated: ServiceLink): void {
    const idx = links.value.findIndex((l) => l.id === updated.id)
    if (idx !== -1) links.value.splice(idx, 1, updated)
  }

  function clearLinkIcon(id: string): void {
    const idx = links.value.findIndex((l) => l.id === id)
    if (idx !== -1) links.value.splice(idx, 1, { ...links.value[idx], icon_url: null })
  }

  function removeLink(id: string): void {
    links.value = links.value.filter((l) => l.id !== id)
  }

  function setLinks(newLinks: ServiceLink[]): void {
    links.value.splice(0, links.value.length, ...newLinks)
  }

  async function openLink(link: ServiceLink) {
    if (link.supports_sso) {
      window.open(`${BASE_URL}/links/${link.id}/sso-redirect`, '_blank', 'noopener,noreferrer')
    } else if (isInternalLinkUrl(link.url)) {
      void recordLinkClick(link.id)
      const { router } = await import('../router')
      void router.push(link.url)
    } else {
      if (!isSafeHttpUrl(link.url)) return
      void recordLinkClick(link.id)
      window.open(link.url, '_blank', 'noopener,noreferrer')
    }
  }

  return {
    links,
    bookmarks,
    loadingLinks,
    loadingBookmarks,
    errorLinks,
    errorBookmarks,
    groupedLinks,
    loadLinks,
    loadBookmarks,
    addBookmark,
    removeBookmark,
    reorder,
    reorderLinks: reorderLinksAction,
    openLink,
    addLink,
    updateLinkItem,
    clearLinkIcon,
    removeLink,
    setLinks,
  }
})
