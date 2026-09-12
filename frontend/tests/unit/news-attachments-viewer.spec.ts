import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  DownloadOutline: { template: '<span />' },
  DocumentOutline: { template: '<span />' },
  ImageOutline: { template: '<span />' },
  VideocamOutline: { template: '<span />' },
  MusicalNotesOutline: { template: '<span />' },
  GridOutline: { template: '<span />' },
  CodeSlashOutline: { template: '<span />' },
}))

const MOCK_ATTACHMENTS = [
  { id: 'a1', original_name: 'document.pdf', file_size: 2048, mime_type: 'application/pdf', download_url: '/api/v1/files/a1' },
  { id: 'a2', original_name: 'image.jpg', file_size: 51200, mime_type: 'image/jpeg', download_url: '/api/v1/files/a2' },
]

describe('NewsAttachmentsViewer.vue', () => {
  it('renders nothing when no attachments', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/news/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: [] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.attachments').exists()).toBe(false)
  })

  it('renders list when attachments present', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/news/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: MOCK_ATTACHMENTS as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.attachments').exists()).toBe(true)
  })

  it('shows file names', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/news/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: MOCK_ATTACHMENTS as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('document.pdf')
    expect(wrapper.text()).toContain('image.jpg')
  })

  it('renders download links', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/news/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: MOCK_ATTACHMENTS as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('a.attachment-item').length).toBe(2)
  })

  it('shows formatted file size', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/news/NewsAttachmentsViewer.vue')).default
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: [MOCK_ATTACHMENTS[0]] as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('2.0 KB')
  })

  it('renders with video attachment', async () => {
    const NewsAttachmentsViewer = (await import('../../src/components/news/NewsAttachmentsViewer.vue')).default
    const videoAtt = [{ id: 'v1', original_name: 'video.mp4', file_size: 1024000, mime_type: 'video/mp4', download_url: '/api/v1/files/v1' }]
    const wrapper = mount(NewsAttachmentsViewer, {
      props: { attachments: videoAtt as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('video.mp4')
  })
})
