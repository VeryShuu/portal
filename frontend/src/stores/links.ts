import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  fetchLinks,
  fetchBookmarks,
  createBookmark,
  deleteBookmark,
  reorderBookmarks,
  type ServiceLink,
  type Bookmark,
  type CreateBookmarkDto,
  type BookmarkReorderItem,
} from '../api/links'
import { isSafeHttpUrl } from '../utils/url'
import { BASE_URL } from '../api'

export const useLinksStore = defineStore('links', () => {
  const links = ref<ServiceLink[]>([])
  const bookmarks = ref<Bookmark[]>([])
  const loadingLinks = ref(false)
  const loadingBookmarks = ref(false)

  const groupedLinks = computed(() => {
    const groups: Record<string, ServiceLink[]> = {}
    for (const link of links.value) {
      const key = link.category ?? 'Другое' // TODO(i18n): replace with t('links.other') when i18n is available in store context
      if (!groups[key]) groups[key] = []
      groups[key].push(link)
    }
    return groups
  })

  async function loadLinks() {
    loadingLinks.value = true
    try {
      const res = await fetchLinks()
      links.value = res.items
    } finally {
      loadingLinks.value = false
    }
  }

  async function loadBookmarks() {
    loadingBookmarks.value = true
    try {
      const res = await fetchBookmarks()
      bookmarks.value = res.items
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

  async function openLink(link: ServiceLink) {
    if (link.supports_sso) {
      window.open(`${BASE_URL}/links/${link.id}/sso-redirect`, '_blank', 'noopener,noreferrer')
    } else {
      if (!isSafeHttpUrl(link.url)) return
      window.open(link.url, '_blank', 'noopener,noreferrer')
    }
  }

  return {
    links,
    bookmarks,
    loadingLinks,
    loadingBookmarks,
    groupedLinks,
    loadLinks,
    loadBookmarks,
    addBookmark,
    removeBookmark,
    reorder,
    openLink,
  }
})
