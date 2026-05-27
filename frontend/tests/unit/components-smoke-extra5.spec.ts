import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'ru' } }),
  createI18n: () => ({ global: { t: (k: string) => k, locale: { value: 'ru' } } }),
}))

const i18n = {
  install: (app: any) => {
    app.config.globalProperties.$t = (k: string) => k
    app.config.globalProperties.$i18n = { locale: 'ru' }
  }
}

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'loading'],
    emits: ['click'],
  },
  NResult: {
    template: '<div class="n-result"><slot name="footer" /></div>',
    props: ['status', 'title', 'description'],
  },
  NTabs: {
    template: '<div class="n-tabs"><slot /></div>',
    props: ['value', 'type', 'animated', 'displayDirective'],
    emits: ['update:value'],
  },
  NTabPane: {
    template: '<div class="n-tab-pane"><slot /></div>',
    props: ['name', 'tab'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'] },
  NForm: { template: '<form><slot /></form>' },
  NFormItem: { template: '<div><slot /></div>', props: ['label'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type'],
    emits: ['update:value'],
  },
  NUpload: { template: '<div class="n-upload"><slot /></div>', props: ['showFileList', 'multiple'] },
  NSelect: { template: '<select><slot /></select>', props: ['value', 'options'] },
  NRadioGroup: { template: '<div class="n-radio-group"><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label class="n-radio-button"><slot /></label>', props: ['value', 'label'] },
  NCheckbox: { template: '<input type="checkbox" />', props: ['checked', 'disabled'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {} })),
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({}),
  apiUpload: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/index', () => ({
  api: vi.fn().mockResolvedValue({}),
  apiUpload: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/auth', () => ({ fetchMe: vi.fn() }))
vi.mock('../../src/api/bootstrap', () => ({ fetchBootstrap: vi.fn() }))
vi.mock('../../src/api/kb', () => ({
  suggestEdit: vi.fn(),
  createSection: vi.fn(),
  fetchSections: vi.fn(),
  importMarkdown: vi.fn(),
  importVault: vi.fn(),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false } })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn() })),
}))

vi.mock('../../src/styles/naive-theme', () => ({
  lightThemeOverrides: {},
  darkThemeOverrides: {},
}))

vi.mock('@vicons/ionicons5', () => ({
  CloudUploadOutline: { template: '<span />' },
  CloseOutline: { template: '<span />' },
  CheckmarkOutline: { template: '<span />' },
}))

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

describe('KbArticleFeedback.vue', () => {
  it('renders without errors', async () => {
    const KbArticleFeedback = (await import('../../src/components/KbArticleFeedback.vue')).default
    const wrapper = mount(KbArticleFeedback, {
      props: { helpfulCount: 5, notHelpfulCount: 2, userFeedback: null },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows helpful and not helpful counts', async () => {
    const KbArticleFeedback = (await import('../../src/components/KbArticleFeedback.vue')).default
    const wrapper = mount(KbArticleFeedback, {
      props: { helpfulCount: 10, notHelpfulCount: 3, userFeedback: null },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('10')
    expect(wrapper.text()).toContain('3')
  })

  it('marks active when userFeedback is true', async () => {
    const KbArticleFeedback = (await import('../../src/components/KbArticleFeedback.vue')).default
    const wrapper = mount(KbArticleFeedback, {
      props: { helpfulCount: 5, notHelpfulCount: 2, userFeedback: true },
      global: { plugins: [i18n] },
    })
    const buttons = wrapper.findAll('.feedback-btn')
    expect(buttons[0].classes()).toContain('feedback-btn--active')
  })

  it('emits feedback event on button click', async () => {
    const KbArticleFeedback = (await import('../../src/components/KbArticleFeedback.vue')).default
    const wrapper = mount(KbArticleFeedback, {
      props: { helpfulCount: 5, notHelpfulCount: 2, userFeedback: null },
      global: { plugins: [i18n] },
    })
    await wrapper.findAll('.feedback-btn')[0].trigger('click')
    expect(wrapper.emitted('feedback')).toEqual([[true]])
  })
})

// NotFoundPage.vue describe-блок переехал в tests/unit/not-found-page.spec.ts
// (см. рекомендованный layout «one component per file» в docs/testing.md).

// TrashPage.vue describe-блок переехал в tests/unit/trash-page.spec.ts
// (см. рекомендованный layout «one component per file» в docs/testing.md).

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
