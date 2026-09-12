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

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'loading'],
    emits: ['click'],
  },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'] },
  NTabs: {
    template: '<div class="n-tabs"><slot /></div>',
    props: ['value', 'type', 'animated', 'displayDirective'],
    emits: ['update:value'],
  },
  NTabPane: {
    template: '<div class="n-tab-pane"><slot /></div>',
    props: ['name', 'tab'],
  },
  NFormItem: { template: '<div><slot /></div>', props: ['label'] },
  NSelect: { template: '<select><slot /></select>', props: ['value', 'options'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn() })),
}))

vi.mock('../../src/api/kb', () => ({
  importMarkdownFile: vi.fn(),
  importVaultZip: vi.fn(),
}))

describe('KbImportModal.vue', () => {
  it('renders when show=true', async () => {
    const KbImportModal = (await import('../../src/components/KbImportModal.vue')).default
    const wrapper = mount(KbImportModal, {
      props: { show: true, sections: [] },
      global: {
        plugins: [i18n],
        stubs: { NUpload: { template: '<div class="n-upload"><slot /></div>' } },
      },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('does not render when show=false', async () => {
    const KbImportModal = (await import('../../src/components/KbImportModal.vue')).default
    const wrapper = mount(KbImportModal, {
      props: { show: false, sections: [] },
      global: {
        plugins: [i18n],
        stubs: { NUpload: { template: '<div class="n-upload"><slot /></div>' } },
      },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(false)
  })
})
