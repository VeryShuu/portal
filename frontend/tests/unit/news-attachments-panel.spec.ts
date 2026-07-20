import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'quaternary', 'ghost', 'tag'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  NUpload: {
    template: '<div class="n-upload"><slot /></div>',
    props: ['showFileList', 'customRequest', 'disabled', 'multiple'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  TrashOutline: { template: '<span />' },
  AttachOutline: { template: '<span />' },
}))

vi.mock('../../src/queries/news', () => ({
  useNewsAttachmentsQuery: vi.fn(() => ({ data: { value: [] } })),
  useUploadAttachmentMutation: vi.fn(() => ({ mutateAsync: vi.fn().mockResolvedValue({ id: 'a1', original_name: 'file.pdf', file_size: 1024, mime_type: 'application/pdf' }) })),
  useDeleteAttachmentMutation: vi.fn(() => ({ mutateAsync: vi.fn().mockResolvedValue(undefined) })),
}))

describe('NewsAttachmentsPanel.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const NewsAttachmentsPanel = (await import('../../src/components/news/NewsAttachmentsPanel.vue')).default
    const wrapper = mount(NewsAttachmentsPanel, {
      props: { newsId: 'news-1' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows warning when newsId is undefined', async () => {
    const NewsAttachmentsPanel = (await import('../../src/components/news/NewsAttachmentsPanel.vue')).default
    const wrapper = mount(NewsAttachmentsPanel, {
      props: { newsId: undefined },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.u-panel__hint').exists()).toBe(true)
  })

  it('shows panel container', async () => {
    const NewsAttachmentsPanel = (await import('../../src/components/news/NewsAttachmentsPanel.vue')).default
    const wrapper = mount(NewsAttachmentsPanel, {
      props: { newsId: 'news-1' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.u-panel').exists()).toBe(true)
  })
})
