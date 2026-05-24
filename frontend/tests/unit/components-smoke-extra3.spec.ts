import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'quaternary', 'circle', 'title', 'ghost', 'attrType'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  NImage: {
    template: '<img :src="src" :alt="alt" class="n-image" />',
    props: ['src', 'alt', 'width', 'height', 'objectFit', 'previewDisabled'],
  },
  NImageGroup: { template: '<div class="n-image-group"><slot /></div>' },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'] },
  NForm: { template: '<form @submit.prevent="$emit(\'submit\')"><slot /></form>', emits: ['submit'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'required'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'rows'],
    emits: ['update:value'],
  },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size'] },
  NDropdown: {
    template: '<div class="n-dropdown"><slot /></div>',
    props: ['options', 'trigger'],
    emits: ['select'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  ChevronBackOutline: { template: '<span />' },
  ChevronForwardOutline: { template: '<span />' },
  FolderOutline: { template: '<span />' },
  AddOutline: { template: '<span />' },
  EllipsisHorizontal: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  ChevronDownOutline: { template: '<span />' },
  ChevronForward: { template: '<span />' },
}))

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
}))

vi.mock('../../src/api/bootstrap', () => ({
  fetchBootstrap: vi.fn(),
}))

vi.mock('../../src/api', () => ({
  api: vi.fn(),
  apiUpload: vi.fn(),
  refreshAuth: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/index', () => ({
  api: vi.fn(),
  apiUpload: vi.fn(),
  refreshAuth: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/kb', () => ({
  suggestEdit: vi.fn(),
  fetchArticles: vi.fn(),
  fetchArticle: vi.fn(),
  fetchSections: vi.fn(),
  fetchTags: vi.fn(),
  fetchComments: vi.fn(),
  createComment: vi.fn(),
  deleteComment: vi.fn(),
  fetchVersions: vi.fn(),
  restoreVersion: vi.fn(),
  createArticle: vi.fn(),
  updateArticle: vi.fn(),
  deleteArticle: vi.fn(),
  createSection: vi.fn(),
  deleteSection: vi.fn(),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false } })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn() })),
}))

vi.mock('../../src/composables/useKbArticleComments', () => ({
  useKbArticleComments: vi.fn(() => ({
    comments: { value: [] },
    total: { value: 0 },
    submitting: { value: false },
    newComment: { value: '' },
    submit: vi.fn(),
    remove: vi.fn(),
  })),
}))

vi.mock('../../src/styles/naive-theme', () => ({
  lightThemeOverrides: {},
  darkThemeOverrides: {},
}))

const MOCK_ARTICLE = {
  id: '00000000-0000-0000-0000-000000000001',
  title: 'Test Article',
  status: 'published' as const,
  user_permission: 'viewer' as const,
  view_count: 42,
  version: 3,
  tags: [{ id: 'tag1', name: 'typescript' }],
  updated_at: '2024-01-15T00:00:00Z',
  created_by: { id: 'u1', full_name: 'Автор Тестов' },
}

describe('KbArticleHeader.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows article title', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Test Article')
  })

  it('shows published status', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.article-status--published').exists()).toBe(true)
  })

  it('shows draft status', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const draft = { ...MOCK_ARTICLE, status: 'draft' as const }
    const wrapper = mount(KbArticleHeader, {
      props: { article: draft as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.article-status--draft').exists()).toBe(true)
  })

  it('shows tags', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('typescript')
  })

  it('shows edit button for editor permission', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const editorArticle = { ...MOCK_ARTICLE, user_permission: 'editor' as const }
    const wrapper = mount(KbArticleHeader, {
      props: { article: editorArticle as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.article-actions').exists()).toBe(true)
  })

  it('shows author name in meta', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Автор Тестов')
  })

  it('shows view count in meta', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('42')
  })

  it('shows delete button for admin', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = { id: 'u2', role: 'admin' } as any

    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    const deleteBtn = wrapper.findAll('button').filter(b => b.text().includes('common.delete'))
    expect(deleteBtn.length).toBe(1)
  })

  it('shows delete button for creator', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = { id: 'u1', role: 'editor' } as any

    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    const deleteBtn = wrapper.findAll('button').filter(b => b.text().includes('common.delete'))
    expect(deleteBtn.length).toBe(1)
  })

  it('hides delete button for non-creator non-admin', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = { id: 'u2', role: 'editor' } as any

    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    const deleteBtn = wrapper.findAll('button').filter(b => b.text().includes('common.delete'))
    expect(deleteBtn.length).toBe(0)
  })
})

describe('KbArticleSuggestTab.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const KbArticleSuggestTab = (await import('../../src/components/KbArticleSuggestTab.vue')).default
    const wrapper = mount(KbArticleSuggestTab, {
      props: { articleId: 'art-1' },
      global: {
        plugins: [i18n],
        stubs: { RichEditor: { template: '<div class="rich-editor" />' } },
      },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('has submit button', async () => {
    const KbArticleSuggestTab = (await import('../../src/components/KbArticleSuggestTab.vue')).default
    const wrapper = mount(KbArticleSuggestTab, {
      props: { articleId: 'art-1' },
      global: {
        plugins: [i18n],
        stubs: { RichEditor: { template: '<div class="rich-editor" />' } },
      },
    })
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('has suggest-form container', async () => {
    const KbArticleSuggestTab = (await import('../../src/components/KbArticleSuggestTab.vue')).default
    const wrapper = mount(KbArticleSuggestTab, {
      props: { articleId: 'art-1' },
      global: {
        plugins: [i18n],
        stubs: { RichEditor: { template: '<div class="rich-editor" />' } },
      },
    })
    expect(wrapper.find('.suggest-form').exists()).toBe(true)
  })
})

describe('KbSectionFormModal.vue', () => {
  it('renders when show=true', async () => {
    const KbSectionFormModal = (await import('../../src/components/KbSectionFormModal.vue')).default
    const wrapper = mount(KbSectionFormModal, {
      props: {
        show: true,
        form: { title: '', description: '', parent_id: null },
        saving: false,
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('hidden when show=false', async () => {
    const KbSectionFormModal = (await import('../../src/components/KbSectionFormModal.vue')).default
    const wrapper = mount(KbSectionFormModal, {
      props: {
        show: false,
        form: { title: '', description: '', parent_id: null },
        saving: false,
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(false)
  })

  it('shows title value from form', async () => {
    const KbSectionFormModal = (await import('../../src/components/KbSectionFormModal.vue')).default
    const wrapper = mount(KbSectionFormModal, {
      props: {
        show: true,
        form: { title: 'My Section', description: 'desc', parent_id: null },
        saving: false,
      },
      global: { plugins: [i18n] },
    })
    const input = wrapper.find('input')
    expect(input.element.value).toBe('My Section')
  })
})

const MOCK_IMAGES = [
  { id: 'img1', url: 'https://example.com/photo1.jpg', original_name: 'photo1.jpg', mime_type: 'image/jpeg', sort_order: 0 },
  { id: 'img2', url: 'https://example.com/photo2.jpg', original_name: 'photo2.jpg', mime_type: 'image/jpeg', sort_order: 1 },
]

describe('NewsGalleryViewer.vue', () => {
  it('renders nothing when images is empty', async () => {
    const NewsGalleryViewer = (await import('../../src/components/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: [] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery').exists()).toBe(false)
  })

  it('renders gallery with images', async () => {
    const NewsGalleryViewer = (await import('../../src/components/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery').exists()).toBe(true)
  })

  it('shows main image', async () => {
    const NewsGalleryViewer = (await import('../../src/components/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery__main').exists()).toBe(true)
  })

  it('shows thumbnails when multiple images', async () => {
    const NewsGalleryViewer = (await import('../../src/components/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery__thumbs').exists()).toBe(true)
  })

  it('shows counter when multiple images', async () => {
    const NewsGalleryViewer = (await import('../../src/components/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery__counter').exists()).toBe(true)
  })

  it('no thumbnails/counter for single image', async () => {
    const NewsGalleryViewer = (await import('../../src/components/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: [MOCK_IMAGES[0]] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.gallery__thumbs').exists()).toBe(false)
    expect(wrapper.find('.gallery__counter').exists()).toBe(false)
  })

  it('clicking prev/next changes activeIdx', async () => {
    const NewsGalleryViewer = (await import('../../src/components/NewsGalleryViewer.vue')).default
    const wrapper = mount(NewsGalleryViewer, {
      props: { images: MOCK_IMAGES },
      global: { plugins: [i18n] },
    })
    await wrapper.find('.gallery__nav--next').trigger('click')
    expect(wrapper.find('.gallery__counter').text()).toContain('2 / 2')
  })
})

describe('FilesSidebar.vue', () => {
  it('renders without errors', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const wrapper = mount(FilesSidebar, {
      props: {
        tree: [],
        loading: false,
        selectedId: null,
        isAdmin: false,
        isEditor: false,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows empty state text when no tree items', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const wrapper = mount(FilesSidebar, {
      props: {
        tree: [],
        loading: false,
        selectedId: null,
        isAdmin: false,
        isEditor: false,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.find('.files-side__empty').exists()).toBe(true)
  })

  it('shows sync button for admin', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const wrapper = mount(FilesSidebar, {
      props: {
        tree: [],
        loading: false,
        selectedId: null,
        isAdmin: true,
        isEditor: true,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.find('.files-side__sync').exists()).toBe(true)
  })

  it('shows loading skeletons when loading=true', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const wrapper = mount(FilesSidebar, {
      props: {
        tree: [],
        loading: true,
        selectedId: null,
        isAdmin: false,
        isEditor: false,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.findAll('.skeleton-card').length).toBeGreaterThan(0)
  })

  it('renders folder tree when tree items present', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const tree = [{ id: 'f1', name: 'Folder 1', children: [], path: '/folder1', nc_path: '/nc/folder1', parent_id: null }]
    const wrapper = mount(FilesSidebar, {
      props: {
        tree,
        loading: false,
        selectedId: null,
        isAdmin: false,
        isEditor: false,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.find('.folder-tree').exists()).toBe(true)
    expect(wrapper.findAll('.folder-node').length).toBe(1)
  })
})

describe('KbArticleCommentsTab.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const KbArticleCommentsTab = (await import('../../src/components/KbArticleCommentsTab.vue')).default
    const wrapper = mount(KbArticleCommentsTab, {
      props: { articleId: 'art-1' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows empty state when no comments', async () => {
    const KbArticleCommentsTab = (await import('../../src/components/KbArticleCommentsTab.vue')).default
    const wrapper = mount(KbArticleCommentsTab, {
      props: { articleId: 'art-1' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.comment-form').exists()).toBe(true)
  })
})
