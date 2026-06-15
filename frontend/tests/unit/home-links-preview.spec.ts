import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const mockFetchLinks = vi.fn()

vi.mock('../../src/api/links', () => ({
  fetchLinks: mockFetchLinks,
  fetchBookmarks: vi.fn(),
  createBookmark: vi.fn(),
  deleteBookmark: vi.fn(),
  reorderBookmarks: vi.fn(),
  reorderLinks: vi.fn(),
}))

vi.mock('../../src/utils/url', () => ({
  isSafeHttpUrl: (url: string) => url.startsWith('http://') || url.startsWith('https://'),
  isInternalLinkUrl: (url: string) => url.startsWith('/') && !url.startsWith('//'),
}))

function makeLink(i: number, showOnHome: boolean) {
  return {
    id: String(i),
    title: `L${i}`,
    url: `https://l${i}.com`,
    category: null,
    supports_sso: false,
    is_active: true,
    show_on_home: showOnHome,
    sort_order: i,
  }
}

async function mountWithLinks(links: unknown[]) {
  const { useHomeLinksPreview } = await import('../../src/pages/composables/useHomeLinksPreview')
  let api!: ReturnType<typeof useHomeLinksPreview>
  const Comp = defineComponent({
    setup() {
      api = useHomeLinksPreview()
      return () => null
    },
  })
  mockFetchLinks.mockResolvedValue({ items: links, total: links.length })
  const wrapper = mount(Comp)
  api.linksStore.links = links as never
  await wrapper.vm.$nextTick()
  return api
}

describe('useHomeLinksPreview.topLinks', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('shows only links flagged show_on_home', async () => {
    const links = [
      makeLink(1, false),
      makeLink(2, true),
      makeLink(3, false),
      makeLink(4, true),
    ]
    const api = await mountWithLinks(links)
    expect(api.topLinks.value.map((l) => l.id)).toEqual(['2', '4'])
  })

  it('caps featured links at 6', async () => {
    const links = Array.from({ length: 8 }, (_, i) => makeLink(i, true))
    const api = await mountWithLinks(links)
    expect(api.topLinks.value).toHaveLength(6)
    expect(api.topLinks.value.map((l) => l.id)).toEqual(['0', '1', '2', '3', '4', '5'])
  })

  it('falls back to first 6 links when none are flagged', async () => {
    const links = Array.from({ length: 8 }, (_, i) => makeLink(i, false))
    const api = await mountWithLinks(links)
    expect(api.topLinks.value).toHaveLength(6)
    expect(api.topLinks.value.map((l) => l.id)).toEqual(['0', '1', '2', '3', '4', '5'])
  })
})
