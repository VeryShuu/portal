/* eslint-disable vue/one-component-per-file -- тестовые компоненты-заглушки объявляются в одном файле */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NForm: { template: '<form><slot /></form>', props: ['model', 'labelPlacement'] },
  NGrid: { template: '<div class="n-grid"><slot /></div>', props: ['cols', 'xGap'] },
  NAlert: {
    template: '<div class="n-alert"><slot name="header" /><slot /></div>',
    props: ['type', 'showIcon', 'closable'],
  },
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'disabled'],
    emits: ['click'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
  useDialog: () => ({ warning: vi.fn(), error: vi.fn(), info: vi.fn(), success: vi.fn() }),
}))

const mockRouteState: { params: Record<string, string>; query: Record<string, string> } = {
  params: {},
  query: {},
}
const mockRouterPush = vi.fn()
const mockRouterBack = vi.fn()
const mockRouterReplace = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({
    push: (...args: unknown[]) => mockRouterPush(...args),
    back: (...args: unknown[]) => mockRouterBack(...args),
    replace: (...args: unknown[]) => mockRouterReplace(...args),
  })),
  useRoute: vi.fn(() => mockRouteState),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
  onBeforeRouteLeave: vi.fn(),
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

const mockFetchSections = vi.fn()
const mockFetchArticle = vi.fn()
const mockSaveDraft = vi.fn()

vi.mock('../../src/api/kb', () => ({
  fetchSections: (...args: unknown[]) => mockFetchSections(...args),
  fetchArticle: (...args: unknown[]) => mockFetchArticle(...args),
  saveDraft: (...args: unknown[]) => mockSaveDraft(...args),
}))

const mockCreateMutateAsync = vi.fn()
const mockUpdateMutateAsync = vi.fn()

vi.mock('../../src/queries/kb', () => ({
  useCreateKbArticleMutation: vi.fn(() => ({ mutateAsync: mockCreateMutateAsync })),
  useUpdateKbArticleMutation: vi.fn(() => ({ mutateAsync: mockUpdateMutateAsync })),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({ user: { id: 'user-1' }, isAdmin: false })),
}))

vi.mock('@/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'generic error'),
  getErrorStatus: (err: unknown) => {
    const e = err as {
      status?: number
      statusCode?: number
      response?: { status?: number }
    } | null
    return e?.response?.status ?? e?.status ?? e?.statusCode
  },
}))

const ArticleMetaSectionStub = defineComponent({
  name: 'ArticleMetaSection',
  props: {
    title: { type: String, default: '' },
  },
  emits: ['update:title'],
  template: '<div class="meta-section-stub" />',
})

const ArticleContentSectionStub = defineComponent({
  name: 'ArticleContentSection',
  props: {
    modelValue: { type: String, default: '' },
    uploadEndpoint: { type: String, default: undefined },
  },
  emits: ['update:modelValue'],
  template: '<div class="content-section-stub" />',
})

const ArticleSettingsSectionStub = defineComponent({
  name: 'ArticleSettingsSection',
  props: {
    status: { type: String, default: 'draft' },
    sectionId: { type: String, default: null },
    tags: { type: Array, default: () => [] },
    changeComment: { type: String, default: '' },
    isEdit: { type: Boolean, default: false },
    statusOptions: { type: Array, default: () => [] },
    sectionOptions: { type: Array, default: () => [] },
  },
  emits: ['update:status', 'update:sectionId', 'update:tags', 'update:changeComment'],
  template: '<div class="settings-section-stub" />',
})

const ArticleAttachmentsSectionStub = defineComponent({
  name: 'ArticleAttachmentsSection',
  props: {
    articleId: { type: String, default: undefined },
    isEdit: { type: Boolean, default: false },
  },
  template: '<div class="attachments-section-stub" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    ArticleMetaSection: ArticleMetaSectionStub,
    ArticleContentSection: ArticleContentSectionStub,
    ArticleSettingsSection: ArticleSettingsSectionStub,
    ArticleAttachmentsSection: ArticleAttachmentsSectionStub,
  },
}

const LOCAL_DRAFT_KEY_CREATE = 'kb-draft-new-user-1'

describe('KbArticleFormPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockRouteState.params = {}
    mockRouteState.query = {}
    mockRouterPush.mockClear()
    mockRouterBack.mockClear()
    mockRouterReplace.mockClear()
    mockFetchSections.mockResolvedValue({ items: [] })
    mockFetchArticle.mockResolvedValue({
      id: 'art-1',
      title: 'Existing Title',
      body: '<p>Existing body</p>',
      section_id: null,
      status: 'draft',
      tags: [],
      version: 2,
    })
    mockSaveDraft.mockResolvedValue({ id: 'art-1', version: 3 })
    mockCreateMutateAsync.mockResolvedValue({ id: 'new-art-1' })
    mockUpdateMutateAsync.mockResolvedValue({ id: 'art-1', version: 3 })
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
  })

  it('shows create heading and two action buttons in create mode', async () => {
    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mount(KbArticleFormPage, { global: globalOptions })
    await flushPromises()

    expect(wrapper.find('h1').text()).toContain('kb.createArticle')
    const formButtons = wrapper.findAll('.form-actions .n-button')
    expect(formButtons.length).toBe(2)
  })

  it('shows edit heading and fetches article when route has id', async () => {
    mockRouteState.params = { id: 'art-1' }
    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mount(KbArticleFormPage, { global: globalOptions })
    await flushPromises()

    expect(wrapper.find('h1').text()).toContain('kb.editArticle')
    expect(mockFetchArticle).toHaveBeenCalledWith('art-1')
    const formButtons = wrapper.findAll('.form-actions .n-button')
    expect(formButtons.length).toBe(3)
  })

  it('calls createKbArticleMutation with correct payload and pushes route on submit', async () => {
    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mount(KbArticleFormPage, { global: globalOptions })
    await flushPromises()

    await wrapper.findComponent(ArticleMetaSectionStub).vm.$emit('update:title', 'My New Article')
    await wrapper.findComponent(ArticleContentSectionStub).vm.$emit('update:modelValue', '<p>Body text</p>')
    await nextTick()

    const formButtons = wrapper.findAll('.form-actions .n-button')
    await formButtons[formButtons.length - 1].trigger('click')
    await flushPromises()

    expect(mockCreateMutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'My New Article',
        body: '<p>Body text</p>',
        section_id: null,
        status: 'draft',
      }),
    )
    expect(mockRouterPush).toHaveBeenCalledWith('/kb/articles/new-art-1')
  })

  it('shows draftConflict banner when saveDraft returns 409', async () => {
    mockRouteState.params = { id: 'art-1' }
    mockSaveDraft.mockRejectedValue({ response: { status: 409 } })

    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mount(KbArticleFormPage, { global: globalOptions })
    await flushPromises()

    await wrapper.findComponent(ArticleMetaSectionStub).vm.$emit('update:title', 'Modified Title')
    await nextTick()

    const formButtons = wrapper.findAll('.form-actions .n-button')
    const saveDraftButton = formButtons[1]
    await saveDraftButton.trigger('click')
    await flushPromises()

    expect(wrapper.find('.recovery-banner').exists()).toBe(true)
  })

  it('shows recovery banner when localStorage has a draft that differs from current form', async () => {
    const draft = {
      title: 'Saved Draft Title',
      body: '<p>Saved draft body</p>',
      section_id: null,
      status: 'draft',
      tags: [],
      savedAt: Date.now() - 60_000,
    }
    localStorage.setItem(LOCAL_DRAFT_KEY_CREATE, JSON.stringify(draft))

    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mount(KbArticleFormPage, { global: globalOptions })
    await flushPromises()

    const alerts = wrapper.findAll('.n-alert')
    const recoveryAlert = alerts.find((a) => a.classes().includes('recovery-banner'))
    expect(recoveryAlert).toBeDefined()
    expect(recoveryAlert!.exists()).toBe(true)
  })

  it('hides recovery banner when clicking recover', async () => {
    const draft = {
      title: 'Saved Draft Title',
      body: '<p>Saved draft body</p>',
      section_id: null,
      status: 'draft',
      tags: [],
      savedAt: Date.now() - 60_000,
    }
    localStorage.setItem(LOCAL_DRAFT_KEY_CREATE, JSON.stringify(draft))

    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mount(KbArticleFormPage, { global: globalOptions })
    await flushPromises()

    const recoverButton = wrapper.find('.recovery-banner .n-button')
    await recoverButton.trigger('click')
    await nextTick()

    expect(wrapper.findAll('.n-alert.recovery-banner').length).toBe(0)
  })

  it('clears localStorage when clicking discard', async () => {
    const draft = {
      title: 'Saved Draft Title',
      body: '<p>Saved draft body</p>',
      section_id: null,
      status: 'draft',
      tags: [],
      savedAt: Date.now() - 60_000,
    }
    localStorage.setItem(LOCAL_DRAFT_KEY_CREATE, JSON.stringify(draft))

    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mount(KbArticleFormPage, { global: globalOptions })
    await flushPromises()

    const buttons = wrapper.findAll('.recovery-banner .n-button')
    await buttons[buttons.length - 1].trigger('click')
    await nextTick()

    expect(localStorage.getItem(LOCAL_DRAFT_KEY_CREATE)).toBeNull()
    expect(wrapper.findAll('.n-alert.recovery-banner').length).toBe(0)
  })

  it('passes sectionOptions with children to ArticleSettingsSection', async () => {
    mockFetchSections.mockResolvedValue({
      items: [
        {
          id: 'sec-1',
          title: 'Root Section',
          children: [{ id: 'sec-2', title: 'Child Section', children: [] }],
        },
      ],
    })

    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mount(KbArticleFormPage, { global: globalOptions })
    await flushPromises()

    const settingsSection = wrapper.findComponent(ArticleSettingsSectionStub)
    const opts = settingsSection.props('sectionOptions') as Array<{ key: string; label: string; children?: unknown[] }>
    expect(opts).toHaveLength(1)
    expect(opts[0].key).toBe('sec-1')
    expect(opts[0].label).toBe('Root Section')
    expect(opts[0].children).toHaveLength(1)
    expect((opts[0].children![0] as { key: string }).key).toBe('sec-2')
  })

  it('calls saveDraft after DRAFT_DEBOUNCE_MS when form changes in edit mode', async () => {
    vi.useFakeTimers()
    mockRouteState.params = { id: 'art-1' }

    const KbArticleFormPage = (await import('../../src/pages/KbArticleFormPage.vue')).default
    const wrapper = mount(KbArticleFormPage, { global: globalOptions })
    await flushPromises()

    await wrapper.findComponent(ArticleMetaSectionStub).vm.$emit('update:title', 'Changed Title')
    await nextTick()

    vi.advanceTimersByTime(7001)
    await flushPromises()

    expect(mockSaveDraft).toHaveBeenCalledWith(
      'art-1',
      expect.objectContaining({ title: 'Changed Title' }),
    )
  })
})
