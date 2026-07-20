/* eslint-disable vue/one-component-per-file -- тестовые компоненты-заглушки объявляются в одном файле */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()

vi.mock('naive-ui', () => ({
  NTabs: {
    name: 'NTabs',
    template: '<div class="n-tabs"><slot /></div>',
    props: ['value', 'type', 'animated', 'displayDirective', 'size'],
    emits: ['update:value'],
  },
  NTabPane: {
    name: 'NTabPane',
    template: '<div class="n-tab-pane" v-if="!displayDirective || displayDirective === \'if\' || shown"><slot /></div>',
    props: ['name', 'tab', 'displayDirective'],
    setup(props) {
      return { shown: true, name: props.name }
    },
  },
  NSkeleton: { name: 'NSkeleton', template: '<div class="n-skeleton" />', props: ['text', 'repeat', 'height'] },
  NButton: {
    name: 'NButton',
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'disabled', 'loading', 'quaternary', 'secondary', 'ghost'],
    emits: ['click'],
  },
  NIcon: { name: 'NIcon', template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  useMessage: () => ({ success: mockMessageSuccess, error: mockMessageError, warning: vi.fn(), info: vi.fn() }),
}))

const mockRouterPush = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({
    push: (...args: unknown[]) => mockRouterPush(...args),
  })),
  useRoute: vi.fn(() => ({ params: { id: 'art-1' }, query: {}, path: '/kb/art-1', name: 'kb-article' })),
}))

vi.mock('@vicons/ionicons5', () => ({
  ChevronBackOutline: { template: '<span />' },
}))

const mockConfirm = vi.fn()
vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: vi.fn(() => ({ confirm: (...args: unknown[]) => mockConfirm(...args) })),
}))

const mockSetQueryData = vi.fn()
const mockInvalidateQueries = vi.fn()
vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: vi.fn(() => ({
    invalidateQueries: (...args: unknown[]) => mockInvalidateQueries(...args),
    removeQueries: vi.fn(),
    setQueryData: (...args: unknown[]) => mockSetQueryData(...args),
  })),
}))

vi.mock('@/utils/sanitize', () => ({
  sanitizeKbHtml: vi.fn((s: string) => `sanitized[${s}]`),
}))

vi.mock('@/utils/markdown', () => ({
  mdUnsafe: { render: vi.fn((s: string) => `md[${s}]`) },
}))

vi.mock('../../src/composables/useLayoutHeader', () => ({
  useLayoutHeader: vi.fn(() => ({ setHeader: vi.fn(), clearHeader: vi.fn() })),
}))

const mockExportPdf = vi.fn()
const mockExportDocx = vi.fn()

vi.mock('../../src/api/kb', () => ({
  exportArticlePdf: (...args: unknown[]) => mockExportPdf(...args),
  exportArticleDocx: (...args: unknown[]) => mockExportDocx(...args),
}))

const mockArticleState = {
  data: ref<unknown>(undefined),
  isLoading: ref(false),
}

const mockDeleteMutateAsync = vi.fn()
const mockFeedbackMutateAsync = vi.fn()

vi.mock('../../src/queries/kb', () => ({
  useKbArticleQuery: vi.fn(() => mockArticleState),
  useDeleteKbArticleMutation: vi.fn(() => ({ mutateAsync: (...args: unknown[]) => mockDeleteMutateAsync(...args) })),
  useSubmitKbFeedbackMutation: vi.fn(() => ({ mutateAsync: (...args: unknown[]) => mockFeedbackMutateAsync(...args) })),
}))

vi.mock('../../src/queries/keys', () => ({
  queryKeys: { kb: { article: (id: string) => ['kb', 'article', id] } },
}))

const KbArticleHeaderStub = defineComponent({
  name: 'KbArticleHeader',
  props: { article: { type: Object, default: null } },
  emits: ['edit', 'manage-perms', 'delete', 'export'],
  template: '<div class="kb-article-header-stub"><button class="hdr-edit" @click="$emit(\'edit\')" /><button class="hdr-perms" @click="$emit(\'manage-perms\')" /><button class="hdr-delete" @click="$emit(\'delete\')" /><button class="hdr-export-pdf" @click="$emit(\'export\', \'pdf\')" /><button class="hdr-export-docx" @click="$emit(\'export\', \'docx\')" /><button class="hdr-export-md" @click="$emit(\'export\', \'md\')" /></div>',
})

const KbArticleFeedbackStub = defineComponent({
  name: 'KbArticleFeedback',
  props: {
    helpfulCount: { type: Number, default: 0 },
    notHelpfulCount: { type: Number, default: 0 },
    userFeedback: { type: String, default: null as string | null },
  },
  emits: ['feedback'],
  template: '<div class="kb-article-feedback-stub"><button class="fb-helpful" @click="$emit(\'feedback\', true)" /><button class="fb-not-helpful" @click="$emit(\'feedback\', false)" /></div>',
})

const KbArticleCommentsTabStub = defineComponent({
  name: 'KbArticleCommentsTab',
  props: { articleId: { type: String, default: '' } },
  emits: ['count-changed'],
  template: '<div class="kb-comments-tab-stub" />',
})

const KbArticleVersionsTabStub = defineComponent({
  name: 'KbArticleVersionsTab',
  props: {
    articleId: { type: String, default: '' },
    currentVersion: { type: Number, default: 1 },
    canRestore: { type: Boolean, default: false },
  },
  emits: ['diff'],
  template: '<div class="kb-versions-tab-stub"><button class="ver-diff" @click="$emit(\'diff\', 1, 2)" /></div>',
})

const KbArticleSuggestTabStub = defineComponent({
  name: 'KbArticleSuggestTab',
  props: { articleId: { type: String, default: '' } },
  template: '<div class="kb-suggest-tab-stub" />',
})

const KbAttachmentsPanelStub = defineComponent({
  name: 'KbAttachmentsPanel',
  props: {
    articleId: { type: String, default: '' },
    canUpload: { type: Boolean, default: false },
  },
  emits: ['files-loaded'],
  template: '<div class="kb-attachments-stub" />',
})

const KbPermissionsModalStub = defineComponent({
  name: 'KbPermissionsModal',
  props: {
    modelValue: { type: Boolean, default: false },
    resourceType: { type: String, default: '' },
    resourceId: { type: String, default: '' },
    inheritPermissions: { type: Boolean, default: true },
  },
  emits: ['update:modelValue', 'inherit-changed'],
  template: '<div v-if="modelValue" class="kb-perms-modal-stub" />',
})

const KbVersionDiffModalStub = defineComponent({
  name: 'KbVersionDiffModal',
  props: {
    modelValue: { type: Boolean, default: false },
    articleId: { type: String, default: '' },
    v1: { type: Number, default: 1 },
    v2: { type: Number, default: 1 },
  },
  emits: ['update:modelValue'],
  template: '<div v-if="modelValue" class="kb-version-diff-modal-stub" />',
})

const EmptyStateStub = defineComponent({
  name: 'EmptyState',
  props: {
    variant: { type: String, default: 'default' },
    title: { type: String, default: '' },
    description: { type: String, default: '' },
  },
  template: '<div class="empty-state-stub" :data-variant="variant" :data-title="title" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    KbArticleHeader: KbArticleHeaderStub,
    KbArticleFeedback: KbArticleFeedbackStub,
    KbArticleCommentsTab: KbArticleCommentsTabStub,
    KbArticleVersionsTab: KbArticleVersionsTabStub,
    KbArticleSuggestTab: KbArticleSuggestTabStub,
    KbAttachmentsPanel: KbAttachmentsPanelStub,
    KbPermissionsModal: KbPermissionsModalStub,
    KbVersionDiffModal: KbVersionDiffModalStub,
    EmptyState: EmptyStateStub,
  },
}

const sampleArticle = {
  id: 'art-1',
  section_id: 'sec-9',
  title: 'Sample KB article',
  body: '# Hello',
  version: 3,
  helpful_count: 4,
  not_helpful_count: 1,
  user_feedback: 'helpful' as string | null,
  user_permission: 'editor',
  inherit_permissions: true,
}

async function mountPage() {
  const KbArticlePage = (await import('../../src/pages/KbArticlePage.vue')).default
  const wrapper = mount(KbArticlePage, { global: globalOptions })
  await flushPromises()
  return wrapper
}

describe('KbArticlePage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())

    mockRouterPush.mockClear()
    mockMessageSuccess.mockClear()
    mockMessageError.mockClear()
    mockConfirm.mockReset()
    mockConfirm.mockResolvedValue(true)

    mockSetQueryData.mockClear()
    mockInvalidateQueries.mockClear()

    mockExportPdf.mockClear()
    mockExportDocx.mockClear()

    mockDeleteMutateAsync.mockClear()
    mockDeleteMutateAsync.mockResolvedValue(undefined)
    mockFeedbackMutateAsync.mockClear()
    mockFeedbackMutateAsync.mockResolvedValue({
      helpful_count: 5,
      not_helpful_count: 1,
      user_feedback: 'helpful',
    })

    mockArticleState.data.value = undefined
    mockArticleState.isLoading.value = false

    vi.stubGlobal('open', vi.fn())
  })

  it('renders skeleton placeholders while loading and no article body', async () => {
    mockArticleState.isLoading.value = true

    const wrapper = await mountPage()

    expect(wrapper.find('.article-wrap .n-skeleton').exists()).toBe(true)
    expect(wrapper.find('.kb-article-header-stub').exists()).toBe(false)
    expect(wrapper.find('.empty-state-stub').exists()).toBe(false)
  })

  it('renders not-found empty state when not loading and article is undefined', async () => {
    mockArticleState.isLoading.value = false
    mockArticleState.data.value = undefined

    const wrapper = await mountPage()

    const empty = wrapper.find('.article-wrap .empty-state-stub')
    expect(empty.exists()).toBe(true)
    expect(empty.attributes('data-title')).toBe('kb.notFound')
  })

  it('renders article body through md + sanitize pipeline', async () => {
    mockArticleState.data.value = sampleArticle

    const wrapper = await mountPage()

    const body = wrapper.find('.article-body')
    expect(body.exists()).toBe(true)
    expect(body.html()).toContain('sanitized[md[# Hello]]')
  })

  it('passes article, helpful/not-helpful counts and user feedback to feedback component', async () => {
    mockArticleState.data.value = sampleArticle

    const wrapper = await mountPage()

    const feedback = wrapper.findComponent(KbArticleFeedbackStub)
    expect(feedback.props('helpfulCount')).toBe(4)
    expect(feedback.props('notHelpfulCount')).toBe(1)
    expect(feedback.props('userFeedback')).toBe('helpful')
  })

  it('shows versions tab only when article version > 1 and passes canRestore derived from user_permission', async () => {
    mockArticleState.data.value = { ...sampleArticle, version: 1, user_permission: 'editor' }
    const wrapperV1 = await mountPage()
    expect(wrapperV1.findComponent(KbArticleVersionsTabStub).exists()).toBe(false)

    mockArticleState.data.value = { ...sampleArticle, version: 3, user_permission: 'editor' }
    const wrapperV3 = await mountPage()
    const versions = wrapperV3.findComponent(KbArticleVersionsTabStub)
    expect(versions.exists()).toBe(true)
    expect(versions.props('currentVersion')).toBe(3)
    expect(versions.props('canRestore')).toBe(true)
  })

  it('shows suggest-edit tab when user lacks editor/manager permission', async () => {
    mockArticleState.data.value = { ...sampleArticle, user_permission: 'viewer' }

    const wrapper = await mountPage()

    expect(wrapper.findComponent(KbArticleSuggestTabStub).exists()).toBe(true)
  })

  it('hides suggest-edit tab and shows versions tab when user is editor', async () => {
    mockArticleState.data.value = { ...sampleArticle, version: 3, user_permission: 'editor' }

    const wrapper = await mountPage()

    expect(wrapper.findComponent(KbArticleSuggestTabStub).exists()).toBe(false)
    expect(wrapper.findComponent(KbArticleVersionsTabStub).exists()).toBe(true)
  })

  it('hides attachments sidebar for non-editors when files-loaded count is 0, shows when count > 0', async () => {
    mockArticleState.data.value = { ...sampleArticle, user_permission: 'viewer' }

    const wrapper = await mountPage()
    // v-show sets display:none when sidebar hidden
    const sidebarHidden = wrapper.find('.article-sidebar')
    expect(sidebarHidden.attributes('style') || '').toMatch(/display:\s*none/)

    wrapper.findComponent(KbAttachmentsPanelStub).vm.$emit('files-loaded', 2)
    await flushPromises()
    await wrapper.vm.$nextTick()

    const sidebarShown = wrapper.find('.article-sidebar')
    expect(sidebarShown.attributes('style') || '').not.toMatch(/display:\s*none/)
  })

  it('always shows attachments sidebar for editors', async () => {
    mockArticleState.data.value = { ...sampleArticle, user_permission: 'editor' }

    const wrapper = await mountPage()
    const sidebar = wrapper.find('.article-sidebar')
    expect(sidebar.exists()).toBe(true)
    expect(sidebar.attributes('style') || '').not.toMatch(/display:\s*none/)
  })

  it('navigates back to /kb with section query when back button clicked', async () => {
    mockArticleState.data.value = sampleArticle

    const wrapper = await mountPage()
    await wrapper.find('.back-btn').trigger('click')

    expect(mockRouterPush).toHaveBeenCalledWith({ path: '/kb', query: { section: 'sec-9' } })
  })

  it('routes header edit event to the edit URL', async () => {
    mockArticleState.data.value = sampleArticle

    const wrapper = await mountPage()
    await wrapper.find('.hdr-edit').trigger('click')

    expect(mockRouterPush).toHaveBeenCalledWith('/kb/articles/art-1/edit')
  })

  it('opens permissions modal on header manage-perms event', async () => {
    mockArticleState.data.value = sampleArticle

    const wrapper = await mountPage()
    await wrapper.find('.hdr-perms').trigger('click')

    expect(wrapper.findComponent(KbPermissionsModalStub).props('modelValue')).toBe(true)
    expect(wrapper.findComponent(KbPermissionsModalStub).props('resourceId')).toBe('art-1')
  })

  it('deletes article only after confirm, then navigates back; shows error on failure', async () => {
    mockArticleState.data.value = sampleArticle

    const wrapper = await mountPage()

    // Cancel confirmation → no delete
    mockConfirm.mockResolvedValueOnce(false)
    await wrapper.find('.hdr-delete').trigger('click')
    await flushPromises()
    expect(mockDeleteMutateAsync).not.toHaveBeenCalled()

    // Confirm → delete succeeds → navigate back
    await wrapper.find('.hdr-delete').trigger('click')
    await flushPromises()
    expect(mockDeleteMutateAsync).toHaveBeenCalledWith('art-1')
    expect(mockRouterPush).toHaveBeenCalledWith({ path: '/kb', query: { section: 'sec-9' } })

    // Failure path → error toast
    mockDeleteMutateAsync.mockRejectedValueOnce(new Error('boom'))
    await wrapper.find('.hdr-delete').trigger('click')
    await flushPromises()
    expect(mockMessageError).toHaveBeenCalled()
  })

  it('exports article via api for pdf/docx and window.open for md', async () => {
    mockArticleState.data.value = sampleArticle

    const wrapper = await mountPage()

    await wrapper.find('.hdr-export-pdf').trigger('click')
    expect(mockExportPdf).toHaveBeenCalledWith('art-1')

    await wrapper.find('.hdr-export-docx').trigger('click')
    expect(mockExportDocx).toHaveBeenCalledWith('art-1')

    await wrapper.find('.hdr-export-md').trigger('click')
    expect(window.open).toHaveBeenCalledWith('/api/v1/kb/articles/art-1/export/md', '_blank', 'noopener,noreferrer')
  })

  it('submits helpful feedback via mutation and shows success toast; shows error on failure', async () => {
    mockArticleState.data.value = sampleArticle

    const wrapper = await mountPage()

    await wrapper.find('.fb-helpful').trigger('click')
    await flushPromises()

    expect(mockFeedbackMutateAsync).toHaveBeenCalledWith({ articleId: 'art-1', isHelpful: true })
    expect(mockMessageSuccess).toHaveBeenCalled()

    // Failure path
    mockFeedbackMutateAsync.mockRejectedValueOnce(new Error('boom'))
    await wrapper.find('.fb-not-helpful').trigger('click')
    await flushPromises()
    expect(mockMessageError).toHaveBeenCalled()
  })

  it('opens version diff modal with v1/v2 when versions tab emits diff', async () => {
    mockArticleState.data.value = { ...sampleArticle, version: 3, user_permission: 'editor' }

    const wrapper = await mountPage()

    await wrapper.find('.ver-diff').trigger('click')
    await flushPromises()

    const modal = wrapper.findComponent(KbVersionDiffModalStub)
    expect(modal.exists()).toBe(true)
    expect(modal.props('v1')).toBe(1)
    expect(modal.props('v2')).toBe(2)
    expect(modal.props('articleId')).toBe('art-1')
  })

  it('updates query cache when permissions modal emits inherit-changed', async () => {
    mockArticleState.data.value = sampleArticle

    const wrapper = await mountPage()
    await wrapper.find('.hdr-perms').trigger('click')

    await wrapper.findComponent(KbPermissionsModalStub).vm.$emit('inherit-changed', false)
    await flushPromises()

    expect(mockSetQueryData).toHaveBeenCalled()
  })
})
