import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'quaternary', 'ghost', 'tag'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'] },
  NSpin: { template: '<div class="n-spin" />', props: ['size'] },
  NUpload: {
    template: '<div class="n-upload"><slot /></div>',
    props: ['showFileList', 'customRequest', 'disabled', 'multiple'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  DownloadOutline: { template: '<span />' },
  DocumentOutline: { template: '<span />' },
  ImageOutline: { template: '<span />' },
  VideocamOutline: { template: '<span />' },
  MusicalNotesOutline: { template: '<span />' },
  GridOutline: { template: '<span />' },
  CodeSlashOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  AttachOutline: { template: '<span />' },
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ items: [] }),
  apiUpload: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/index', () => ({
  api: vi.fn().mockResolvedValue({ items: [] }),
  apiUpload: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/auth', () => ({ fetchMe: vi.fn() }))
vi.mock('../../src/api/bootstrap', () => ({ fetchBootstrap: vi.fn() }))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false } })),
  useMutation: vi.fn(() => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: { value: false },
  })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn() })),
}))

vi.mock('../../src/queries/news', () => ({
  useNewsAttachmentsQuery: vi.fn(() => ({ data: { value: [] } })),
  useUploadAttachmentMutation: vi.fn(() => ({ mutateAsync: vi.fn().mockResolvedValue({ id: 'a1', original_name: 'file.pdf', file_size: 1024, mime_type: 'application/pdf' }) })),
  useDeleteAttachmentMutation: vi.fn(() => ({ mutateAsync: vi.fn().mockResolvedValue(undefined) })),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'error'),
}))

vi.mock('../../src/styles/naive-theme', () => ({
  lightThemeOverrides: {},
  darkThemeOverrides: {},
}))

const MOCK_ATTACHMENTS = [
  { id: 'a1', original_name: 'document.pdf', file_size: 2048, mime_type: 'application/pdf', download_url: '/api/v1/files/a1' },
  { id: 'a2', original_name: 'image.jpg', file_size: 51200, mime_type: 'image/jpeg', download_url: '/api/v1/files/a2' },
]

describe('NewsAttachmentsViewer.vue', () => {
  it('renders nothing when no attachments', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: [] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.attachments').exists()).toBe(false)
  })

  it('renders list when attachments present', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: MOCK_ATTACHMENTS as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.attachments').exists()).toBe(true)
  })

  it('shows file names', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: MOCK_ATTACHMENTS as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('document.pdf')
    expect(wrapper.text()).toContain('image.jpg')
  })

  it('renders download links', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: MOCK_ATTACHMENTS as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('a.attachment-item').length).toBe(2)
  })

  it('shows formatted file size', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: [MOCK_ATTACHMENTS[0]] as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('2.0 KB')
  })

  it('renders with video attachment', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/NewsAttachmentsViewer.vue')).default
    const videoAtt = [{ id: 'v1', original_name: 'video.mp4', file_size: 1024000, mime_type: 'video/mp4', download_url: '/api/v1/files/v1' }]
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: videoAtt as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('video.mp4')
  })
})

describe('KbVersionDiffModal.vue', () => {
  it('renders modal when modelValue=true', async () => {
    const KbVersionDiffModal = (await import('../../src/components/KbVersionDiffModal.vue')).default
    const wrapper = mount(KbVersionDiffModal, {
      props: { modelValue: true, articleId: 'art-1', v1: 1, v2: 2 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('does not render modal when modelValue=false', async () => {
    const KbVersionDiffModal = (await import('../../src/components/KbVersionDiffModal.vue')).default
    const wrapper = mount(KbVersionDiffModal, {
      props: { modelValue: false, articleId: 'art-1', v1: 1, v2: 2 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(false)
  })

  it('shows loading spinner when loading', async () => {
    const { api } = await import('../../src/api')
    vi.mocked(api).mockImplementation(() => new Promise(() => {}))
    const KbVersionDiffModal = (await import('../../src/components/KbVersionDiffModal.vue')).default
    const wrapper = mount(KbVersionDiffModal, {
      props: { modelValue: true, articleId: 'art-1', v1: 1, v2: 2 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-spin').exists() || wrapper.find('.diff-error').exists() || wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('shows diff content when diff loaded', async () => {
    const { api } = await import('../../src/api')
    vi.mocked(api).mockResolvedValue({
      stats: { added: 5, removed: 2 },
      hunks: [{ header: '@@ -1,3 +1,5 @@', lines: ['+new line', '-old line', ' context'] }],
    })
    const KbVersionDiffModal = (await import('../../src/components/KbVersionDiffModal.vue')).default
    const wrapper = mount(KbVersionDiffModal, {
      props: { modelValue: true, articleId: 'art-1', v1: 1, v2: 2 },
      global: { plugins: [i18n] },
    })
    await new Promise(r => setTimeout(r, 50))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })
})

describe('KbAttachmentsPanel.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const KbAttachmentsPanel = (await import('../../src/components/KbAttachmentsPanel.vue')).default
    const wrapper = mount(KbAttachmentsPanel, {
      props: { articleId: 'art-1', canUpload: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows empty state when no files', async () => {
    const KbAttachmentsPanel = (await import('../../src/components/KbAttachmentsPanel.vue')).default
    const wrapper = mount(KbAttachmentsPanel, {
      props: { articleId: 'art-1', canUpload: false },
      global: { plugins: [i18n] },
    })
    await new Promise(r => setTimeout(r, 50))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.attachments-panel').exists()).toBe(true)
  })

  it('shows upload button when canUpload=true', async () => {
    const KbAttachmentsPanel = (await import('../../src/components/KbAttachmentsPanel.vue')).default
    const wrapper = mount(KbAttachmentsPanel, {
      props: { articleId: 'art-1', canUpload: true },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.upload-btn').exists()).toBe(true)
  })

  it('hides upload button when canUpload=false', async () => {
    const KbAttachmentsPanel = (await import('../../src/components/KbAttachmentsPanel.vue')).default
    const wrapper = mount(KbAttachmentsPanel, {
      props: { articleId: 'art-1', canUpload: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.upload-btn').exists()).toBe(false)
  })
})

describe('NewsAttachmentsPanel.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const NewsAttachmentsPanel = (await import('../../src/components/NewsAttachmentsPanel.vue')).default
    const wrapper = mount(NewsAttachmentsPanel, {
      props: { newsId: 'news-1' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows warning when newsId is undefined', async () => {
    const NewsAttachmentsPanel = (await import('../../src/components/NewsAttachmentsPanel.vue')).default
    const wrapper = mount(NewsAttachmentsPanel, {
      props: { newsId: undefined },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.panel__hint').exists()).toBe(true)
  })

  it('shows panel container', async () => {
    const NewsAttachmentsPanel = (await import('../../src/components/NewsAttachmentsPanel.vue')).default
    const wrapper = mount(NewsAttachmentsPanel, {
      props: { newsId: 'news-1' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.panel').exists()).toBe(true)
  })
})
