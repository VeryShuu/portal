/* eslint-disable vue/one-component-per-file -- тестовые компоненты-заглушки объявляются в одном файле */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, type Component } from 'vue'
import { NDialogProvider } from 'naive-ui'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return { ...actual, useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }
})

const mockRouteState: { params: Record<string, string>; query: Record<string, string> } = {
  params: {},
  query: {},
}

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() })),
  useRoute: vi.fn(() => mockRouteState),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
  onBeforeRouteLeave: vi.fn(),
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

vi.mock('../../src/api/kb', () => ({
  fetchSections: vi.fn().mockResolvedValue({ items: [] }),
  fetchArticle: vi.fn().mockResolvedValue({
    id: 'art-1',
    title: 'Existing Title',
    body: '<p>Existing body</p>',
    section_id: null,
    status: 'draft',
    tags: [],
    version: 2,
  }),
  saveDraft: vi.fn().mockResolvedValue({ id: 'art-1', version: 3 }),
}))

vi.mock('../../src/queries/kb', () => ({
  useCreateKbArticleMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useUpdateKbArticleMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({ user: { id: 'user-1' }, isAdmin: false })),
}))

vi.mock('@/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'generic error'),
  getErrorStatus: (err: unknown) => (err as { response?: { status?: number } } | null)?.response?.status,
}))

const RichEditorStub = defineComponent({
  name: 'RichEditor',
  props: { modelValue: { type: String, default: '' }, placeholder: { type: String, default: '' }, uploadEndpoint: { type: String, default: undefined } },
  emits: ['update:modelValue'],
  template: '<div class="rich-editor-stub" />',
})

const KbAttachmentsPanelStub = defineComponent({
  name: 'KbAttachmentsPanel',
  props: { articleId: { type: String, default: undefined }, canUpload: { type: Boolean, default: false } },
  template: '<div class="attachments-panel-stub" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    RichEditor: RichEditorStub,
    KbAttachmentsPanel: KbAttachmentsPanelStub,
  },
}

describe('KbArticleFormPage.vue — real layout renders form fields', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockRouteState.params = {}
    mockRouteState.query = {}
  })

  function mountWithProviders(page: Component) {
    const Host = defineComponent({
      render: () => h(NDialogProvider, null, { default: () => h(page) }),
    })
    return mount(Host, { global: globalOptions })
  }

  it('renders the title input alongside the action buttons (regression: grid must not swallow section components)', async () => {
    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mountWithProviders(KbArticleFormPage)
    await flushPromises()

    expect(wrapper.find('.form-actions').exists()).toBe(true)
    expect(wrapper.find('input').exists()).toBe(true)
    expect(wrapper.findComponent(RichEditorStub).exists()).toBe(true)
  })

  it('renders form fields in edit mode too', async () => {
    mockRouteState.params = { id: 'art-1' }
    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mountWithProviders(KbArticleFormPage)
    await flushPromises()

    expect(wrapper.find('input').exists()).toBe(true)
    expect(wrapper.findComponent(RichEditorStub).exists()).toBe(true)
    expect(wrapper.findComponent(KbAttachmentsPanelStub).exists()).toBe(true)
  })
})
