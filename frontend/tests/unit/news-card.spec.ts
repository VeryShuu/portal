import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  EyeOutline: { template: '<span />' },
  StarOutline: { template: '<span />' },
  BarChartOutline: { template: '<span />' },
  ChatbubbleOutline: { template: '<span />' },
}))

vi.mock('../../src/components/news/NewsLikeButton.vue', () => ({
  default: { name: 'NewsLikeButton', template: '<button class="news-like" />', props: ['newsId', 'likeCount', 'liked', 'compact'] },
}))

const MOCK_NEWS = {
  id: '550e8400-e29b-41d4-a716-446655440001',
  title: 'Test News',
  body: '<p>Test body content</p>',
  status: 'published' as const,
  is_pinned: false,
  categories: [],
  cover_image_url: null,
  cover_focal_x: null,
  cover_focal_y: null,
  cover_focal_zoom: null,
  cover_dominant_color: null,
  cover_webp_srcset: null,
  cover_avif_srcset: null,
  target_departments: null,
  target_roles: null,
  author_id: null,
  publish_at: null,
  archive_at: null,
  published_at: '2024-01-15T00:00:00Z',
  view_count: 42,
  current_version: 1,
  created_at: '2024-01-10T00:00:00Z',
  updated_at: '2024-01-15T00:00:00Z',
}

describe('NewsCard.vue', () => {
  it('renders with news prop', async () => {
    const { default: NewsCard } = await import('../../src/components/news/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: MOCK_NEWS },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('Test News')
  })

  it('emits click event on click', async () => {
    const { default: NewsCard } = await import('../../src/components/news/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: MOCK_NEWS },
      global: { plugins: [i18n] },
    })
    await wrapper.find('article').trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')![0]).toEqual([MOCK_NEWS.id])
  })

  it('applies pinned class when is_pinned=true', async () => {
    const { default: NewsCard } = await import('../../src/components/news/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: { ...MOCK_NEWS, is_pinned: true } },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('article').classes()).toContain('news-card--pinned')
  })

  it('applies featured class when featured=true', async () => {
    const { default: NewsCard } = await import('../../src/components/news/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: MOCK_NEWS, featured: true },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('article').classes()).toContain('news-card--featured')
  })

  it('renders cover image when cover_image_url is set', async () => {
    const { default: NewsCard } = await import('../../src/components/news/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: { ...MOCK_NEWS, cover_image_url: '/img/cover.jpg' } },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('picture').exists()).toBe(true)
  })

  it('shows view count', async () => {
    const { default: NewsCard } = await import('../../src/components/news/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: { ...MOCK_NEWS, view_count: 123 } },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('123')
  })
})
