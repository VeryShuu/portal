import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NImage: {
    template: '<img :src="src" :alt="alt" class="n-image" />',
    props: ['src', 'alt', 'width', 'height', 'objectFit', 'previewDisabled'],
  },
  NImageGroup: { template: '<div class="n-image-group"><slot /></div>' },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  ChevronBackOutline: { template: '<span />' },
  ChevronForwardOutline: { template: '<span />' },
}))

const MOCK_IMAGES = [
  { id: 'img1', url: 'https://example.com/photo1.jpg', original_name: 'photo1.jpg', mime_type: 'image/jpeg', sort_order: 0 },
  { id: 'img2', url: 'https://example.com/photo2.jpg', original_name: 'photo2.jpg', mime_type: 'image/jpeg', sort_order: 1 },
]

describe('NewsGalleryViewer.vue', () => {
  it('renders nothing when images is empty', async () => {
    const NewsGalleryViewer = (await import('../../src/components/news/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: [] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery').exists()).toBe(false)
  })

  it('renders gallery with images', async () => {
    const NewsGalleryViewer = (await import('../../src/components/news/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery').exists()).toBe(true)
  })

  it('shows main image', async () => {
    const NewsGalleryViewer = (await import('../../src/components/news/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery__main').exists()).toBe(true)
  })

  it('shows thumbnails when multiple images', async () => {
    const NewsGalleryViewer = (await import('../../src/components/news/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery__thumbs').exists()).toBe(true)
  })

  it('shows counter when multiple images', async () => {
    const NewsGalleryViewer = (await import('../../src/components/news/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery__counter').exists()).toBe(true)
  })

  it('no thumbnails/counter for single image', async () => {
    const NewsGalleryViewer = (await import('../../src/components/news/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: [MOCK_IMAGES[0]] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery__thumbs').exists()).toBe(false)
    expect(wrapper.find('.gallery__counter').exists()).toBe(false)
  })

  it('clicking prev/next changes activeIdx', async () => {
    const NewsGalleryViewer = (await import('../../src/components/news/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    await wrapper.find('.gallery__nav--next').trigger('click')
    expect(wrapper.find('.gallery__counter').text()).toContain('2 / 2')
  })
})
