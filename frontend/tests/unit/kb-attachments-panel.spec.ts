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
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('../../src/api/kb', () => ({
  fetchAttachments: vi.fn().mockResolvedValue({ items: [] }),
  uploadAttachment: vi.fn(),
  deleteAttachment: vi.fn(),
}))

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
