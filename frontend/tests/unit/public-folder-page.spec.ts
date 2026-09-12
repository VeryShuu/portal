import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { token: 'tok' } }),
}))

const ofetchMock = vi.fn()
vi.mock('ofetch', () => ({
  ofetch: (...args: unknown[]) => ofetchMock(...args),
}))

vi.mock('@/api/photos', () => ({
  publicFolderInfoUrl: (t: string) => `info:${t}`,
  publicFolderPhotosUrl: (t: string, p: number, pp: number) => `photos:${t}:${p}:${pp}`,
  publicFolderThumbUrl: () => 'thumb',
  publicFolderAvifUrl: () => 'avif',
}))

vi.mock('@/stores/branding', () => ({
  useBrandingStore: () => ({ settings: { portal_name: 'P' }, load: vi.fn() }),
}))

vi.mock('@/composables/useLightboxView', () => ({
  useLightboxView: () => ({
    zoom: { value: 1 },
    imgStyle: { value: {} },
    resetView: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    rotateLeft: vi.fn(),
    rotateRight: vi.fn(),
    onLightboxWheel: vi.fn(),
  }),
}))

import PublicFolderPage from '../../src/pages/photos/PublicFolderPage.vue'

function photoPagesRequested(): number[] {
  return ofetchMock.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.startsWith('photos:'))
    .map((u) => Number(u.split(':')[2]))
}

describe('PublicFolderPage — loadMore page does not skip on failure (B3)', () => {
  beforeEach(() => ofetchMock.mockReset())

  it('retries the same page after a failed loadMore', async () => {
    let page2Failed = false
    ofetchMock.mockImplementation((url?: string) => {
      const u = String(url ?? "")
      if (u.startsWith("info:")) return Promise.resolve({ id: "f", title: "F" })
      const page = Number(u.split(":")[2])
      if (page === 2 && !page2Failed) {
        page2Failed = true
        return Promise.reject(new Error('network'))
      }
      return Promise.resolve({ items: [{ id: `p${page}` }], total: 100 })
    })

    const wrapper = mount(PublicFolderPage, {
      global: {
        stubs: { PhotosGridBase: true, PhotoThumb: true, LightboxBase: true },
      },
    })
    await flushPromises()

    const btn = wrapper.find('button')
    expect(btn.exists()).toBe(true)

    await btn.trigger('click')
    await flushPromises()

    await btn.trigger('click')
    await flushPromises()

    expect(photoPagesRequested()).toEqual([1, 2, 2])
  })
})
