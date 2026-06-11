import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const mockFetchLinks = vi.fn()
const mockFetchBookmarks = vi.fn()
const mockCreateBookmark = vi.fn()
const mockDeleteBookmark = vi.fn()
const mockReorderBookmarks = vi.fn()

vi.mock('../../src/api/links', () => ({
  fetchLinks: mockFetchLinks,
  fetchBookmarks: mockFetchBookmarks,
  createBookmark: mockCreateBookmark,
  deleteBookmark: mockDeleteBookmark,
  reorderBookmarks: mockReorderBookmarks,
}))

vi.mock('../../src/utils/url', () => ({
  isSafeHttpUrl: (url: string) => url.startsWith('http://') || url.startsWith('https://'),
  isInternalLinkUrl: (url: string) => url.startsWith('/') && !url.startsWith('//'),
}))

const mockRouterPush = vi.fn()
vi.mock('../../src/router', () => ({
  router: { push: (...args: unknown[]) => mockRouterPush(...args) },
}))

const mockWindowOpen = vi.fn()
vi.stubGlobal('open', mockWindowOpen)

describe('useLinksStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('groupedLinks', () => {
    it('groups links by category', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      const store = useLinksStore()
      store.links = [
        { id: '1', title: 'A', url: 'https://a.com', category: 'Tools', supports_sso: false, sort_order: 0 },
        { id: '2', title: 'B', url: 'https://b.com', category: 'Tools', supports_sso: false, sort_order: 1 },
        { id: '3', title: 'C', url: 'https://c.com', category: 'Docs', supports_sso: false, sort_order: 2 },
      ] as any
      expect(store.groupedLinks['Tools']).toHaveLength(2)
      expect(store.groupedLinks['Docs']).toHaveLength(1)
    })

    it('groups null category as "Другое"', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      const store = useLinksStore()
      store.links = [
        { id: '1', title: 'X', url: 'https://x.com', category: null, supports_sso: false, sort_order: 0 },
      ] as any
      expect(store.groupedLinks['Другое']).toHaveLength(1)
    })
  })

  describe('loadLinks()', () => {
    it('populates links from api', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      const link = { id: '1', title: 'Link', url: 'https://l.com', category: null, supports_sso: false, sort_order: 0 }
      mockFetchLinks.mockResolvedValueOnce({ items: [link] })
      const store = useLinksStore()
      await store.loadLinks()
      expect(store.links).toHaveLength(1)
      expect(store.loadingLinks).toBe(false)
    })

    it('resets loadingLinks to false and sets errorLinks on error', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      mockFetchLinks.mockRejectedValueOnce(new Error('fail'))
      const store = useLinksStore()
      await store.loadLinks()
      expect(store.loadingLinks).toBe(false)
      expect(store.errorLinks).toBe('network')
    })
  })

  describe('loadBookmarks()', () => {
    it('populates bookmarks from api', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      const bm = { id: 'b1', title: 'BM', url: 'https://bm.com', sort_order: 0 }
      mockFetchBookmarks.mockResolvedValueOnce({ items: [bm] })
      const store = useLinksStore()
      await store.loadBookmarks()
      expect(store.bookmarks).toHaveLength(1)
      expect(store.loadingBookmarks).toBe(false)
    })
  })

  describe('addBookmark()', () => {
    it('appends bookmark to list', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      const bm = { id: 'new', title: 'New', url: 'https://new.com', sort_order: 99 }
      mockCreateBookmark.mockResolvedValueOnce(bm)
      const store = useLinksStore()
      await store.addBookmark({ title: 'New', url: 'https://new.com' } as any)
      expect(store.bookmarks).toContainEqual(bm)
    })
  })

  describe('removeBookmark()', () => {
    it('removes bookmark by id', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      mockDeleteBookmark.mockResolvedValueOnce(undefined)
      const store = useLinksStore()
      store.bookmarks = [
        { id: 'b1', title: 'Keep', url: 'https://k.com', sort_order: 0 },
        { id: 'b2', title: 'Delete', url: 'https://d.com', sort_order: 1 },
      ] as any
      await store.removeBookmark('b2')
      expect(store.bookmarks).toHaveLength(1)
      expect(store.bookmarks[0].id).toBe('b1')
    })
  })

  describe('reorder()', () => {
    it('updates sort_order and sorts', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      mockReorderBookmarks.mockResolvedValueOnce(undefined)
      const store = useLinksStore()
      store.bookmarks = [
        { id: 'b1', title: 'A', url: 'https://a.com', sort_order: 2 },
        { id: 'b2', title: 'B', url: 'https://b.com', sort_order: 1 },
      ] as any
      await store.reorder([
        { id: 'b1', sort_order: 0 },
        { id: 'b2', sort_order: 1 },
      ])
      expect(store.bookmarks[0].id).toBe('b1')
      expect(store.bookmarks[0].sort_order).toBe(0)
    })
  })

  describe('openLink()', () => {
    it('opens non-SSO link in new tab', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      const store = useLinksStore()
      const link = { id: '1', title: 'X', url: 'https://x.com', supports_sso: false, category: null, sort_order: 0 }
      await store.openLink(link as any)
      expect(mockWindowOpen).toHaveBeenCalledWith('https://x.com', '_blank', 'noopener,noreferrer')
    })

    it('opens SSO link via sso-redirect endpoint', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      const store = useLinksStore()
      const link = { id: '2', title: 'SSO', url: 'https://svc.com', supports_sso: true, category: null, sort_order: 0 }
      await store.openLink(link as any)
      expect(mockWindowOpen).toHaveBeenCalledWith(
        expect.stringContaining('/links/2/sso-redirect'),
        '_blank',
        'noopener,noreferrer',
      )
    })

    it('does not open unsafe non-SSO url', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      const store = useLinksStore()
      const link = { id: '3', title: 'Evil', url: 'javascript:alert(1)', supports_sso: false, category: null, sort_order: 0 }
      await store.openLink(link as any)
      expect(mockWindowOpen).not.toHaveBeenCalled()
    })

    it('navigates internal link via router (same tab)', async () => {
      const { useLinksStore } = await import('../../src/stores/links')
      const store = useLinksStore()
      const link = { id: '4', title: 'Signature', url: '/signature', supports_sso: false, category: null, sort_order: 0 }
      await store.openLink(link as any)
      expect(mockRouterPush).toHaveBeenCalledWith('/signature')
      expect(mockWindowOpen).not.toHaveBeenCalled()
    })
  })
})
