import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'ru' } }),
  createI18n: () => ({ global: { t: (k: string) => k, locale: { value: 'ru' } } }),
}))

const i18n = {
  install: (app: any) => {
    app.config.globalProperties.$t = (k: string) => k
    app.config.globalProperties.$i18n = { locale: 'ru' }
  },
}

describe('FilesDropZone.vue', () => {
  it('renders nothing when inactive', async () => {
    const FilesDropZone = (await import('../../src/components/files/FilesDropZone.vue')).default
    const wrapper = mount(FilesDropZone, {
      props: { active: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.files-dropzone-overlay').exists()).toBe(false)
  })

  it('shows overlay when active', async () => {
    const FilesDropZone = (await import('../../src/components/files/FilesDropZone.vue')).default
    const wrapper = mount(FilesDropZone, {
      props: { active: true },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.files-dropzone-overlay').exists()).toBe(true)
  })
})
