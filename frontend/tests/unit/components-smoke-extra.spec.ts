import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'iconPlacement'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'clearable', 'size'],
    emits: ['update:value', 'input', 'update:modelValue'],
  },
  NSelect: {
    template: '<select><slot /></select>',
    props: ['value', 'options', 'placeholder', 'clearable', 'size'],
    emits: ['update:value'],
  },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'bordered'] },
  NAvatar: { template: '<div class="n-avatar"><slot /></div>', props: ['src', 'size', 'round'] },
  NDropdown: {
    template: '<div class="n-dropdown"><slot /></div>',
    props: ['options', 'trigger', 'placement'],
    emits: ['select'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  EyeOutline: { template: '<span />' },
  StarOutline: { template: '<span />' },
  DocumentOutline: { template: '<span />' },
  SearchOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  FolderOutline: { template: '<span />' },
  ChevronDownOutline: { template: '<span />' },
  ChevronForwardOutline: { template: '<span />' },
  CreateOutline: { template: '<span />' },
  EllipsisVertical: { template: '<span />' },
  EllipsisHorizontal: { template: '<span />' },
  ChatbubbleOutline: { template: '<span />' },
  Heart: { template: '<span />' },
  HeartOutline: { template: '<span />' },
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
  cover_focal_point: null,
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

describe('EmptyState.vue', () => {
  it('renders with required title prop', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No items found' } })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('No items found')
  })

  it('renders description when provided', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, {
      props: { title: 'Empty', description: 'Try adding something' },
    })
    expect(wrapper.text()).toContain('Try adding something')
  })

  it('applies compact class when compact=true', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'Empty', compact: true } })
    expect(wrapper.find('.empty--compact').exists()).toBe(true)
  })

  it('renders news variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No news', variant: 'news' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders bookmark variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No bookmarks', variant: 'bookmark' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders search variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No results', variant: 'search' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders file variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No files', variant: 'file' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders photo variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No photos', variant: 'photo' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders default variant icon when no variant specified', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'Default' } })
    expect(wrapper.exists()).toBe(true)
  })
})

describe('SkeletonCard.vue', () => {
  it('renders news variant by default', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard)
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.skeleton-card--news').exists()).toBe(true)
  })

  it('renders article variant', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard, { props: { variant: 'article' } })
    expect(wrapper.find('.skeleton-card').exists()).toBe(true)
  })

  it('renders list variant', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard, { props: { variant: 'list' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders file-row variant', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard, { props: { variant: 'file-row' } })
    expect(wrapper.find('.skeleton-file-row').exists()).toBe(true)
  })

  it('renders folder-item variant', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard, { props: { variant: 'folder-item' } })
    expect(wrapper.find('.skeleton-folder-item').exists()).toBe(true)
  })
})

describe('NewsCard.vue', () => {
  it('renders with news prop', async () => {
    const { default: NewsCard } = await import('../../src/components/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: MOCK_NEWS },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('Test News')
  })

  it('emits click event on click', async () => {
    const { default: NewsCard } = await import('../../src/components/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: MOCK_NEWS },
      global: { plugins: [i18n] },
    })
    await wrapper.find('article').trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')![0]).toEqual([MOCK_NEWS.id])
  })

  it('applies pinned class when is_pinned=true', async () => {
    const { default: NewsCard } = await import('../../src/components/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: { ...MOCK_NEWS, is_pinned: true } },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('article').classes()).toContain('news-card--pinned')
  })

  it('applies featured class when featured=true', async () => {
    const { default: NewsCard } = await import('../../src/components/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: MOCK_NEWS, featured: true },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('article').classes()).toContain('news-card--featured')
  })

  it('renders cover image when cover_image_url is set', async () => {
    const { default: NewsCard } = await import('../../src/components/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: { ...MOCK_NEWS, cover_image_url: '/img/cover.jpg' } },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('picture').exists()).toBe(true)
  })

  it('shows view count', async () => {
    const { default: NewsCard } = await import('../../src/components/NewsCard.vue')
    const wrapper = mount(NewsCard, {
      props: { news: { ...MOCK_NEWS, view_count: 123 } },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('123')
  })
})

describe('FeedbackAttachmentList.vue', () => {
  it('renders empty list', async () => {
    const { default: FeedbackAttachmentList } = await import('../../src/components/FeedbackAttachmentList.vue')
    const wrapper = mount(FeedbackAttachmentList, {
      props: { attachments: [] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders attachment items', async () => {
    const { default: FeedbackAttachmentList } = await import('../../src/components/FeedbackAttachmentList.vue')
    const attachments = [
      { id: 'a1', original_name: 'doc.pdf', size_bytes: 1024, mime_type: 'application/pdf', download_url: '/files/doc.pdf', created_at: '' },
    ]
    const wrapper = mount(FeedbackAttachmentList, {
      props: { attachments },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('doc.pdf')
  })

  it('renders image attachment with image tag', async () => {
    const { default: FeedbackAttachmentList } = await import('../../src/components/FeedbackAttachmentList.vue')
    const attachments = [
      { id: 'a2', original_name: 'photo.jpg', size_bytes: 2048, mime_type: 'image/jpeg', download_url: '/files/photo.jpg', created_at: '' },
    ]
    const wrapper = mount(FeedbackAttachmentList, {
      props: { attachments },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('img').exists()).toBe(true)
  })
})

describe('KbListToolbar.vue', () => {
  it('renders without errors', async () => {
    const { default: KbListToolbar } = await import('../../src/components/KbListToolbar.vue')
    const wrapper = mount(KbListToolbar, {
      props: {
        searchQuery: '',
        statusFilter: null,
        tagFilter: null,
        tagOptions: [],
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders with search query', async () => {
    const { default: KbListToolbar } = await import('../../src/components/KbListToolbar.vue')
    const wrapper = mount(KbListToolbar, {
      props: {
        searchQuery: 'vue',
        statusFilter: 'published',
        tagFilter: null,
        tagOptions: [{ label: 'Vue', value: 'vue' }],
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
    const input = wrapper.find('input')
    expect((input.element as HTMLInputElement).value).toBe('vue')
  })
})

describe('KbArticleCard.vue', () => {
  const MOCK_ARTICLE = {
    id: 'art-1',
    title: 'Test Article',
    status: 'published',
    view_count: 10,
    tags: [{ id: 't1', name: 'Vue', slug: 'vue' }],
    section: { id: 's1', title: 'Frontend' },
    updated_at: '2024-01-15T00:00:00Z',
  }

  it('renders article title', async () => {
    const { default: KbArticleCard } = await import('../../src/components/KbArticleCard.vue')
    const wrapper = mount(KbArticleCard, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('Test Article')
  })

  it('emits open event on click', async () => {
    const { default: KbArticleCard } = await import('../../src/components/KbArticleCard.vue')
    const wrapper = mount(KbArticleCard, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    await wrapper.find('.kb-card').trigger('click')
    expect(wrapper.emitted('open')).toBeTruthy()
  })

  it('shows tags from article', async () => {
    const { default: KbArticleCard } = await import('../../src/components/KbArticleCard.vue')
    const wrapper = mount(KbArticleCard, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Vue')
  })

  it('marks active tag', async () => {
    const { default: KbArticleCard } = await import('../../src/components/KbArticleCard.vue')
    const wrapper = mount(KbArticleCard, {
      props: { article: MOCK_ARTICLE as any, activeTag: 'vue' },
      global: { plugins: [i18n] },
    })
    const tag = wrapper.find('.kb-tag--active')
    expect(tag.exists()).toBe(true)
  })
})
