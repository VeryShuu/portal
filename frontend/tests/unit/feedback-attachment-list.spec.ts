import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  DocumentOutline: { template: '<span />' },
}))

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
