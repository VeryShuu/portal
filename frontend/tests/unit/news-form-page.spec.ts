/* eslint-disable vue/one-component-per-file -- тестовые компоненты-заглушки объявляются в одном файле */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const H = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  saveDraft: vi.fn(),
  msgSuccess: vi.fn(),
  msgError: vi.fn(),
  dialogWarning: vi.fn(),
  routeLeaveGuard: undefined as unknown as () => unknown,
  validateShouldFail: false,
  // refs assigned inside the queries mock factory
  editData: undefined as unknown as { value: unknown },
  isLoading: undefined as unknown as { value: boolean },
  categories: undefined as unknown as { value: unknown[] },
  uploadLimits: undefined as unknown as { value: unknown },
}))

vi.mock('naive-ui', () => ({
  NForm: {
    template: '<form><slot /></form>',
    props: ['model', 'rules', 'labelPlacement'],
    methods: {
      validate() {
        return H.validateShouldFail ? Promise.reject(new Error('invalid')) : Promise.resolve()
      },
    },
  },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label', 'path'] },
  NInput: {
    template: '<input class="n-input" :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'size'],
    emits: ['update:value'],
  },
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'block', 'text', 'loading'],
    emits: ['click'],
  },
  NSpin: { template: '<div class="n-spin" />' },
  NSelect: { template: '<div class="n-select" />', props: ['value', 'options', 'multiple'] },
  NCheckbox: { template: '<div class="n-checkbox"><slot /></div>', props: ['checked'] },
  NDatePicker: { template: '<div class="n-date" />', props: ['value', 'type'] },
  NIcon: { template: '<i class="n-icon"><slot /></i>', props: ['size'] },
  useMessage: () => ({ success: H.msgSuccess, error: H.msgError, warning: vi.fn() }),
  useDialog: () => ({ warning: (...args: unknown[]) => H.dialogWarning(...args) }),
}))

const mockRouteState: { params: Record<string, string> } = { params: {} }
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
  onBeforeRouteLeave: (fn: () => unknown) => { H.routeLeaveGuard = fn },
}))

vi.mock('@vicons/ionicons5', () => ({
  StarOutline: { template: '<span />' },
  CheckmarkCircleOutline: { template: '<span />' },
}))

vi.mock('../../src/api/news', () => ({
  saveDraft: (...args: unknown[]) => H.saveDraft(...args),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'generic error'),
}))

vi.mock('../../src/queries/news', async () => {
  const { ref } = await import('vue')
  H.editData = ref(undefined)
  H.isLoading = ref(false)
  H.categories = ref([])
  H.uploadLimits = ref({ news_attachment_max_size_mb: 50 })
  return {
    useNewsCategoriesQuery: () => ({ data: H.categories }),
    useNewsUploadLimitsQuery: () => ({ data: H.uploadLimits }),
    useNewsDetailQuery: () => ({ data: H.editData, isLoading: H.isLoading }),
    useCreateNewsMutation: () => ({ mutateAsync: H.create }),
    useUpdateNewsMutation: () => ({ mutateAsync: H.update }),
  }
})

const RichEditorStub = defineComponent({
  name: 'RichEditor',
  props: { modelValue: { type: String, default: '' }, placeholder: { type: String, default: '' }, uploadEndpoint: { type: String, default: undefined } },
  emits: ['update:modelValue'],
  template: '<div class="rich-editor-stub" />',
})
const NewsCoverUploadStub = defineComponent({
  name: 'NewsCoverUpload',
  props: { newsId: { type: String, default: undefined }, isEdit: { type: Boolean, default: false }, coverImageUrl: { type: String, default: null }, focalX: { type: Number, default: null }, focalY: { type: Number, default: null }, focalZoom: { type: Number, default: null }, maxSizeMb: { type: Number, default: 0 } },
  emits: ['update:cover-image-url', 'update:focal-x', 'update:focal-y', 'update:focal-zoom'],
  template: '<div class="cover-upload-stub" />',
})
const NewsGalleryPanelStub = defineComponent({
  name: 'NewsGalleryPanel',
  props: { newsId: { type: String, default: undefined } },
  template: '<div class="gallery-panel-stub" />',
})
const NewsAttachmentsPanelStub = defineComponent({
  name: 'NewsAttachmentsPanel',
  props: { newsId: { type: String, default: undefined } },
  template: '<div class="attachments-panel-stub" />',
})
const NewsPollPanelStub = defineComponent({
  name: 'NewsPollPanel',
  props: { newsId: { type: String, default: undefined }, hasPoll: { type: Boolean, default: undefined } },
  template: '<div class="poll-panel-stub" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    RichEditor: RichEditorStub,
    NewsCoverUpload: NewsCoverUploadStub,
    NewsGalleryPanel: NewsGalleryPanelStub,
    NewsAttachmentsPanel: NewsAttachmentsPanelStub,
    NewsPollPanel: NewsPollPanelStub,
  },
}

function sampleNews(overrides: Record<string, unknown> = {}) {
  return {
    id: 'n-1',
    title: 'Existing Title',
    body: '<p>Existing body</p>',
    status: 'draft',
    is_pinned: false,
    categories: ['cat-a'],
    publish_at: null,
    published_at: null,
    cover_focal_x: null,
    cover_focal_y: null,
    cover_focal_zoom: null,
    cover_image_url: 'http://x/cover.jpg',
    has_poll: false,
    ...overrides,
  }
}

async function mountPage(opts: { id?: string; editData?: Record<string, unknown> } = {}) {
  mockRouteState.params = opts.id ? { id: opts.id } : {}
  const NewsFormPage = (await import('../../src/pages/NewsFormPage.vue')).default
  if (opts.editData !== undefined) H.editData.value = opts.editData
  const wrapper = mount(NewsFormPage, { global: globalOptions })
  await flushPromises()
  return wrapper
}

describe('NewsFormPage.vue (NF-0 characterizing)', () => {
  beforeEach(() => {
    mockRouteState.params = {}
    mockRouterPush.mockClear()
    mockRouterBack.mockClear()
    mockRouterReplace.mockClear()
    H.create.mockReset().mockResolvedValue({ id: 'new-1' })
    H.update.mockReset().mockResolvedValue({ id: 'n-1' })
    H.saveDraft.mockReset().mockResolvedValue(undefined)
    H.msgSuccess.mockClear()
    H.msgError.mockClear()
    H.dialogWarning.mockClear()
    H.routeLeaveGuard = undefined as unknown as () => unknown
    H.validateShouldFail = false
    if (H.editData) H.editData.value = undefined
    if (H.isLoading) H.isLoading.value = false
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders create heading in create mode', async () => {
    const wrapper = await mountPage()
    expect(wrapper.find('h1').text()).toContain('news.create.title')
  })

  it('renders edit heading and fetches/populates form in edit mode', async () => {
    const wrapper = await mountPage({ id: 'n-1', editData: sampleNews() })
    expect(wrapper.find('h1').text()).toContain('news.edit.title')
    const title = wrapper.find('.n-input').element as HTMLInputElement
    expect(title.value).toBe('Existing Title')
  })

  it('shows spinner while loading and hides the form', async () => {
    mockRouteState.params = { id: 'n-1' }
    const NewsFormPage = (await import('../../src/pages/NewsFormPage.vue')).default
    H.isLoading.value = true
    const wrapper = mount(NewsFormPage, { global: globalOptions })
    await flushPromises()
    expect(wrapper.find('.n-spin').exists()).toBe(true)
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('draft-create: creates news as draft and replaces route to edit', async () => {
    const wrapper = await mountPage()
    await wrapper.find('.n-input').setValue('My Title')
    await wrapper.findAll('.side-actions .n-button')[0].trigger('click')
    await flushPromises()

    expect(H.create).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'My Title', status: 'draft' }),
    )
    expect(mockRouterReplace).toHaveBeenCalledWith('/news/new-1/edit')
    expect(mockRouterPush).not.toHaveBeenCalled()
  })

  it('draft-edit: updates existing news as draft without navigating', async () => {
    const wrapper = await mountPage({ id: 'n-1', editData: sampleNews() })
    await wrapper.findAll('.side-actions .n-button')[0].trigger('click')
    await flushPromises()

    expect(H.update).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'n-1', dto: expect.objectContaining({ status: 'draft' }) }),
    )
    expect(mockRouterReplace).not.toHaveBeenCalled()
    expect(mockRouterPush).not.toHaveBeenCalled()
  })

  it('publish-create: creates news as published and pushes to /news', async () => {
    const wrapper = await mountPage()
    await wrapper.find('.n-input').setValue('Fresh')
    await wrapper.findAll('.side-actions .n-button')[1].trigger('click')
    await flushPromises()

    expect(H.create).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Fresh', status: 'published' }),
    )
    expect(mockRouterPush).toHaveBeenCalledWith('/news')
  })

  it('publish-edit: updates existing news as published and pushes to /news', async () => {
    const wrapper = await mountPage({ id: 'n-1', editData: sampleNews() })
    await wrapper.findAll('.side-actions .n-button')[1].trigger('click')
    await flushPromises()

    expect(H.update).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'n-1', dto: expect.objectContaining({ status: 'published' }) }),
    )
    expect(mockRouterPush).toHaveBeenCalledWith('/news')
  })

  it('does not call mutations when validation fails', async () => {
    H.validateShouldFail = true
    const wrapper = await mountPage()
    await wrapper.findAll('.side-actions .n-button')[1].trigger('click')
    await flushPromises()

    expect(H.create).not.toHaveBeenCalled()
    expect(H.update).not.toHaveBeenCalled()
    expect(mockRouterPush).not.toHaveBeenCalled()
  })

  it('shows error message when submit mutation rejects', async () => {
    H.create.mockRejectedValue(new Error('boom'))
    const wrapper = await mountPage()
    await wrapper.findAll('.side-actions .n-button')[1].trigger('click')
    await flushPromises()

    expect(H.msgError).toHaveBeenCalledWith('generic error')
    expect(mockRouterPush).not.toHaveBeenCalled()
  })

  it('cancel button calls router.back', async () => {
    const wrapper = await mountPage()
    await wrapper.findAll('.side-actions .n-button')[2].trigger('click')
    expect(mockRouterBack).toHaveBeenCalled()
  })

  it('passes newsId to child panels in edit mode', async () => {
    const wrapper = await mountPage({ id: 'n-1', editData: sampleNews() })
    expect(wrapper.findComponent(NewsGalleryPanelStub).props('newsId')).toBe('n-1')
    expect(wrapper.findComponent(NewsAttachmentsPanelStub).props('newsId')).toBe('n-1')
    expect(wrapper.findComponent(NewsPollPanelStub).props('newsId')).toBe('n-1')
    expect(wrapper.findComponent(RichEditorStub).props('uploadEndpoint')).toBe('/api/v1/news/n-1/inline-media')
  })

  it('does not pass an upload endpoint to RichEditor in create mode', async () => {
    const wrapper = await mountPage()
    expect(wrapper.findComponent(RichEditorStub).props('uploadEndpoint')).toBeUndefined()
  })

  it('autosave: in edit+draft sends only {title, body} after the interval', async () => {
    vi.useFakeTimers()
    mockRouteState.params = { id: 'n-1' }
    const NewsFormPage = (await import('../../src/pages/NewsFormPage.vue')).default
    H.editData.value = sampleNews()
    const wrapper = mount(NewsFormPage, { global: globalOptions })
    await flushPromises()
    expect(wrapper.exists()).toBe(true)

    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()

    expect(H.saveDraft).toHaveBeenCalledWith('n-1', { title: 'Existing Title', body: '<p>Existing body</p>' })
  })

  it('autosave: does not run in create mode', async () => {
    vi.useFakeTimers()
    const NewsFormPage = (await import('../../src/pages/NewsFormPage.vue')).default
    mount(NewsFormPage, { global: globalOptions })
    await flushPromises()

    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()

    expect(H.saveDraft).not.toHaveBeenCalled()
  })

  it('autosave: does not run when status is published', async () => {
    vi.useFakeTimers()
    mockRouteState.params = { id: 'n-1' }
    const NewsFormPage = (await import('../../src/pages/NewsFormPage.vue')).default
    H.editData.value = sampleNews({ status: 'published' })
    mount(NewsFormPage, { global: globalOptions })
    await flushPromises()

    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()

    expect(H.saveDraft).not.toHaveBeenCalled()
  })

  it('autosave: swallows errors and does not set lastSaved', async () => {
    vi.useFakeTimers()
    H.saveDraft.mockRejectedValue(new Error('net'))
    mockRouteState.params = { id: 'n-1' }
    const NewsFormPage = (await import('../../src/pages/NewsFormPage.vue')).default
    H.editData.value = sampleNews()
    const wrapper = mount(NewsFormPage, { global: globalOptions })
    await flushPromises()

    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()

    expect(H.saveDraft).toHaveBeenCalled()
    expect(wrapper.find('.autosave-hint').exists()).toBe(false)
  })

  it('passes autofocus to main fields in create mode but not in edit mode', async () => {
    const NewsFormMainFields = (await import('../../src/components/news/NewsFormMainFields.vue')).default
    const createWrapper = await mountPage()
    expect(createWrapper.findComponent(NewsFormMainFields).props('autofocus')).toBe(true)

    const editWrapper = await mountPage({ id: 'n-1', editData: sampleNews() })
    expect(editWrapper.findComponent(NewsFormMainFields).props('autofocus')).toBe(false)
  })

  it('leave guard: allows navigation when form is pristine', async () => {
    await mountPage()
    expect(H.routeLeaveGuard()).toBe(true)
    expect(H.dialogWarning).not.toHaveBeenCalled()
  })

  it('leave guard: prompts and resolves false on cancel when form is dirty', async () => {
    const wrapper = await mountPage()
    await wrapper.find('.n-input').setValue('Dirty title')
    await nextTick()

    const result = H.routeLeaveGuard() as Promise<boolean>
    expect(H.dialogWarning).toHaveBeenCalledTimes(1)
    const opts = H.dialogWarning.mock.calls[0][0] as { onNegativeClick: () => void }
    opts.onNegativeClick()
    await expect(result).resolves.toBe(false)
  })

  it('leave guard: resolves true on confirm when form is dirty', async () => {
    const wrapper = await mountPage()
    await wrapper.find('.n-input').setValue('Dirty title')
    await nextTick()

    const result = H.routeLeaveGuard() as Promise<boolean>
    const opts = H.dialogWarning.mock.calls[0][0] as { onPositiveClick: () => void }
    opts.onPositiveClick()
    await expect(result).resolves.toBe(true)
  })

  it('leave guard: allows navigation after a successful save', async () => {
    const wrapper = await mountPage({ id: 'n-1', editData: sampleNews() })
    await wrapper.find('.n-input').setValue('Changed title')
    await nextTick()
    await wrapper.findAll('.side-actions .n-button')[0].trigger('click')
    await flushPromises()

    expect(H.routeLeaveGuard()).toBe(true)
  })
})

describe('isBodyEmpty', () => {
  it('treats whitespace, empty tags and nbsp as empty', async () => {
    const { isBodyEmpty } = await import('../../src/pages/composables/newsFormMappers')
    expect(isBodyEmpty('')).toBe(true)
    expect(isBodyEmpty('   ')).toBe(true)
    expect(isBodyEmpty('<p></p>')).toBe(true)
    expect(isBodyEmpty('<p>&nbsp;</p>')).toBe(true)
  })

  it('detects real content', async () => {
    const { isBodyEmpty } = await import('../../src/pages/composables/newsFormMappers')
    expect(isBodyEmpty('<p>Hello</p>')).toBe(false)
    expect(isBodyEmpty('text')).toBe(false)
  })
})
