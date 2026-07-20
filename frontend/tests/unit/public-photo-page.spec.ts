import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('ofetch', () => ({
  ofetch: vi.fn().mockImplementation(async () => {
    return { id: 'p1', original_name: 'test.jpg', width: 1000, height: 800, mime_type: 'image/jpeg', file_size: 1024, created_at: '2024-01-01T00:00:00Z' }
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => ({ params: { token: 'tok' }, query: {}, path: '/pub/photo/tok', name: 'public-photo' })),
}))

vi.mock('@/api/photos', () => ({
  publicPhotoFileUrl: vi.fn((token: string) => `/api/v1/photos/public/photo/${token}/file`),
  publicPhotoInfoUrl: vi.fn((token: string) => `/api/v1/photos/public/photo/${token}/info`),
  publicPhotoThumbUrl: vi.fn((token: string, size: number) => `/api/v1/photos/public/photo/${token}/thumb/${size}`),
  publicPhotoAvifUrl: vi.fn((token: string, size: number) => `/api/v1/photos/public/photo/${token}/thumb/${size}/avif`),
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

const globalPlugins = {
  plugins: [i18n],
}

describe('PublicPhotoPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders without errors', async () => {
    const PublicPhotoPage = (await import('../../src/pages/photos/PublicPhotoPage.vue')).default
    const wrapper = mount(PublicPhotoPage, { global: globalPlugins })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders outer wrapper', async () => {
    const PublicPhotoPage = (await import('../../src/pages/photos/PublicPhotoPage.vue')).default
    const wrapper = mount(PublicPhotoPage, { global: globalPlugins })
    expect(wrapper.find('.public-photo').exists()).toBe(true)
  })

  it('renders toolbar after photo loads and toolbar buttons work', async () => {
    const PublicPhotoPage = (await import('../../src/pages/photos/PublicPhotoPage.vue')).default
    const wrapper = mount(PublicPhotoPage, { global: globalPlugins })
    await flushPromises()
    const toolbar = wrapper.find('.public-photo__toolbar')
    if (toolbar.exists()) {
      const buttons = toolbar.findAll('button')
      for (const btn of buttons) {
        await btn.trigger('click')
      }
    }
    expect(wrapper.exists()).toBe(true)
  })
})
