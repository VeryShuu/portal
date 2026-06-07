import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, defineComponent, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const routeState = { params: { id: 'art-1' as string } }
const routerPush = vi.fn()

const kbTrashData = {
  items: [] as any[],
  total: 0,
  purge_due_count: 0,
  retention_days: 30,
}
const fetchTrashArticles = vi.fn()
const restoreTrashArticle = vi.fn()
const purgeTrashArticle = vi.fn()
const purgeAllTrash = vi.fn()
const updateTrashRetention = vi.fn()

const dialogWarning = vi.fn()
const messageSuccess = vi.fn()
const messageError = vi.fn()

const articleState = {
  data: null as any,
  loading: false,
}

const confirmFn = vi.fn(async () => true)
const deleteMutateAsync = vi.fn(async () => undefined)
const submitFeedbackMutateAsync = vi.fn(async () => undefined)
const setHeader = vi.fn()
const clearHeader = vi.fn()
const exportPdf = vi.fn()
const exportDocx = vi.fn()
const setQueryData = vi.fn()

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'disabled', 'quaternary', 'text', 'tertiary'],
    emits: ['click'],
  },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['size'] },
  NDataTable: { template: '<div class="n-data-table" />', props: ['columns', 'data', 'loading', 'pagination', 'remote', 'bordered', 'size'] },
  NInputNumber: {
    template: '<input class="n-input-number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />',
    props: ['value', 'min', 'max', 'disabled'],
    emits: ['update:value'],
  },
  NPopconfirm: { template: '<div class="n-popconfirm"><slot /><slot name="trigger" /></div>', props: ['positiveText', 'negativeText'], emits: ['positive-click'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['size', 'bordered'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NSkeleton: { template: '<div class="n-skeleton" />', props: ['text', 'repeat'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  useDialog: () => ({ warning: dialogWarning }),
  useMessage: () => ({ success: messageSuccess, error: messageError, warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: routerPush, replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => routeState),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false } })),
  useMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useQueryClient: vi.fn(() => ({ setQueryData })),
  keepPreviousData: undefined,
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ data: {} }),
  apiUpload: vi.fn().mockResolvedValue({ data: {} }),
  BASE_URL: '/api/v1',
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

vi.mock('../../src/api/kb', () => ({
  fetchTrashArticles: (...args: unknown[]) => fetchTrashArticles(...args),
  restoreTrashArticle: (...args: unknown[]) => restoreTrashArticle(...args),
  purgeTrashArticle: (...args: unknown[]) => purgeTrashArticle(...args),
  purgeAllTrash: (...args: unknown[]) => purgeAllTrash(...args),
  updateTrashRetention: (...args: unknown[]) => updateTrashRetention(...args),
  exportArticlePdf: (...args: unknown[]) => exportPdf(...args),
  exportArticleDocx: (...args: unknown[]) => exportDocx(...args),
}))

vi.mock('../../src/queries/kb', () => ({
  useKbArticleQuery: vi.fn(() => ({ data: ref(articleState.data), isLoading: ref(articleState.loading) })),
  useDeleteKbArticleMutation: vi.fn(() => ({ mutateAsync: deleteMutateAsync })),
  useSubmitKbFeedbackMutation: vi.fn(() => ({ mutateAsync: submitFeedbackMutateAsync })),
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: vi.fn(() => ({ confirm: (...args: unknown[]) => confirmFn(...args) })),
}))

vi.mock('../../src/composables/useLayoutHeader', () => ({
  useLayoutHeader: vi.fn(() => ({ setHeader, clearHeader })),
}))

vi.mock('@/utils/sanitize', () => ({
  sanitizeKbHtml: vi.fn((v: string) => v),
}))

vi.mock('@/utils/markdown', () => ({
  mdUnsafe: { render: (v: string) => `<p>${v}</p>` },
}))

vi.mock('../../src/queries/keys', () => ({
  queryKeys: {
    kb: {
      article: (id: string) => ['kb', 'article', id],
    },
  },
}))

vi.mock('../../src/components/EmptyState.vue', () => ({
  default: defineComponent({ name: 'EmptyState', template: '<div class="empty-state" />', props: ['variant', 'title', 'description'] }),
}))

vi.mock('../../src/components/KbArticleHeader.vue', () => ({
  default: defineComponent({
    name: 'KbArticleHeader',
    props: ['article'],
    emits: ['edit', 'manage-perms', 'delete', 'export'],
    template: '<div class="kb-header"><button class="h-edit" @click="$emit(\'edit\')" /><button class="h-perms" @click="$emit(\'manage-perms\')" /><button class="h-delete" @click="$emit(\'delete\')" /><button class="h-export-pdf" @click="$emit(\'export\', \'pdf\')" /><button class="h-export-docx" @click="$emit(\'export\', \'docx\')" /><button class="h-export-md" @click="$emit(\'export\', \'md\')" /></div>',
  }),
}))

vi.mock('../../src/components/KbArticleFeedback.vue', () => ({
  default: defineComponent({
    name: 'KbArticleFeedback',
    props: ['helpfulCount', 'notHelpfulCount', 'userFeedback'],
    emits: ['feedback'],
    template: '<div class="kb-feedback"><button class="fb-yes" @click="$emit(\'feedback\', true)" /><button class="fb-no" @click="$emit(\'feedback\', false)" /></div>',
  }),
}))

vi.mock('../../src/components/KbArticleCommentsTab.vue', () => ({
  default: defineComponent({ name: 'KbArticleCommentsTab', props: ['articleId'], emits: ['count-changed'], template: '<div class="comments-tab" />' }),
}))

vi.mock('../../src/components/KbArticleVersionsTab.vue', () => ({
  default: defineComponent({ name: 'KbArticleVersionsTab', props: ['articleId', 'currentVersion', 'canRestore'], emits: ['diff'], template: '<div class="versions-tab"><button class="open-diff" @click="$emit(\'diff\', 1, 2)" /></div>' }),
}))

vi.mock('../../src/components/KbArticleSuggestTab.vue', () => ({
  default: defineComponent({ name: 'KbArticleSuggestTab', props: ['articleId'], template: '<div class="suggest-tab" />' }),
}))

vi.mock('../../src/components/KbAttachmentsPanel.vue', () => ({
  default: defineComponent({ name: 'KbAttachmentsPanel', props: ['articleId', 'canUpload'], emits: ['files-loaded'], template: '<div class="attachments-panel"><button class="files-loaded" @click="$emit(\'files-loaded\', 2)" /></div>' }),
}))

vi.mock('../../src/components/KbPermissionsModal.vue', () => ({
  default: defineComponent({
    name: 'KbPermissionsModal',
    props: ['modelValue', 'resourceType', 'resourceId', 'inheritPermissions'],
    emits: ['update:modelValue', 'inherit-changed'],
    template: '<div class="permissions-modal"><button class="inh" @click="$emit(\'inherit-changed\', false)" /></div>',
  }),
}))

vi.mock('../../src/components/KbVersionDiffModal.vue', () => ({
  default: defineComponent({ name: 'KbVersionDiffModal', props: ['modelValue', 'articleId', 'v1', 'v2'], emits: ['update:modelValue'], template: '<div class="diff-modal" />' }),
}))

describe('cov2 KbTrashPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    fetchTrashArticles.mockReset()
    updateTrashRetention.mockReset()
    purgeAllTrash.mockReset()
    restoreTrashArticle.mockReset()
    purgeTrashArticle.mockReset()
    dialogWarning.mockReset()
    messageSuccess.mockReset()
    messageError.mockReset()

    fetchTrashArticles.mockResolvedValue({
      items: [{ id: 't1', title: 'A', deleted_at: '2026-01-01', files_bytes: 0, media_bytes: 0, files_count: 0, children: [] }],
      total: 1,
      purge_due_count: 2,
      retention_days: 30,
    })
    updateTrashRetention.mockResolvedValue({})
    purgeAllTrash.mockResolvedValue({ purged: 3 })
  })

  it('mounts with loaded data and triggers bulk purge actions', async () => {
    const Cmp = (await import('../../src/pages/KbTrashPage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.exists()).toBe(true)
    expect(fetchTrashArticles).toHaveBeenCalled()

    const buttons = w.findAll('button.n-button')
    await buttons[2].trigger('click')
    expect(dialogWarning).toHaveBeenCalled()
    const opts1 = dialogWarning.mock.calls[0][0]
    await opts1.onPositiveClick()
    expect(purgeAllTrash).toHaveBeenCalledWith(30)

    await buttons[3].trigger('click')
    const opts2 = dialogWarning.mock.calls[1][0]
    await opts2.onPositiveClick()
    expect(purgeAllTrash).toHaveBeenCalledWith(null)
  })

  it('handles retention save validation and success/error branches', async () => {
    const Cmp = (await import('../../src/pages/KbTrashPage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    const input = w.find('.n-input-number')
    await input.setValue('-1')
    const saveBtn = w.findAll('button.n-button').find((b) => b.text().includes('common.save'))!
    await saveBtn.trigger('click')
    expect(messageError).toHaveBeenCalled()

    await input.setValue('50')
    await saveBtn.trigger('click')
    await flushPromises()
    expect(updateTrashRetention).toHaveBeenCalledWith(50)
    expect(messageSuccess).toHaveBeenCalled()

    updateTrashRetention.mockRejectedValueOnce(new Error('x'))
    await input.setValue('60')
    await saveBtn.trigger('click')
    await flushPromises()
    expect(messageError).toHaveBeenCalled()
  })
})

describe('cov2 KbArticlePage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routeState.params.id = 'art-1'
    articleState.loading = false
    articleState.data = {
      id: 'art-1',
      title: 'Article one',
      body: 'Body',
      helpful_count: 1,
      not_helpful_count: 0,
      user_feedback: null,
      version: 2,
      user_permission: 'editor',
      inherit_permissions: true,
    }
    confirmFn.mockReset()
    confirmFn.mockResolvedValue(true)
    deleteMutateAsync.mockReset()
    deleteMutateAsync.mockResolvedValue(undefined)
    submitFeedbackMutateAsync.mockReset()
    submitFeedbackMutateAsync.mockResolvedValue(undefined)
    messageSuccess.mockReset()
    messageError.mockReset()
    routerPush.mockReset()
    exportPdf.mockReset()
    exportDocx.mockReset()
    setQueryData.mockReset()
  })

  it('renders loading, article, and empty states', async () => {
    const Cmp = (await import('../../src/pages/KbArticlePage.vue')).default

    articleState.loading = true
    const w1 = mount(Cmp, { global: { plugins: [i18n] } })
    expect(w1.find('.n-skeleton').exists()).toBe(true)

    articleState.loading = false
    articleState.data = null
    const w2 = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w2.find('.empty-state').exists()).toBe(true)

    articleState.data = {
      id: 'art-1', title: 'Article one', body: 'Body', helpful_count: 1, not_helpful_count: 0,
      user_feedback: null, version: 2, user_permission: 'editor', inherit_permissions: true,
    }
    const w3 = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w3.find('.kb-header').exists()).toBe(true)
  })

  it('handles header emits for edit/perms/export and feedback success/error', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const Cmp = (await import('../../src/pages/KbArticlePage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    await w.find('.h-edit').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/kb/articles/art-1/edit')

    await w.find('.h-perms').trigger('click')
    expect(w.find('.permissions-modal').exists()).toBe(true)

    await w.find('.inh').trigger('click')
    expect(setQueryData).toHaveBeenCalled()

    await w.find('.h-export-pdf').trigger('click')
    await w.find('.h-export-docx').trigger('click')
    await w.find('.h-export-md').trigger('click')
    expect(exportPdf).toHaveBeenCalledWith('art-1')
    expect(exportDocx).toHaveBeenCalledWith('art-1')
    expect(openSpy).toHaveBeenCalled()

    await w.find('.fb-yes').trigger('click')
    expect(submitFeedbackMutateAsync).toHaveBeenCalledWith({ articleId: 'art-1', isHelpful: true })

    submitFeedbackMutateAsync.mockRejectedValueOnce(new Error('x'))
    await w.find('.fb-no').trigger('click')
    await flushPromises()
    expect(messageError).toHaveBeenCalled()

    openSpy.mockRestore()
  })

  it('handles delete branches and diff modal opening', async () => {
    const Cmp = (await import('../../src/pages/KbArticlePage.vue')).default
    const w = mount(Cmp, { global: { plugins: [i18n] } })
    await flushPromises()

    confirmFn.mockResolvedValue(false)
    await w.find('.h-delete').trigger('click')
    expect(deleteMutateAsync).not.toHaveBeenCalled()

    confirmFn.mockResolvedValue(true)
    deleteMutateAsync.mockResolvedValueOnce(undefined)
    await w.find('.h-delete').trigger('click')
    await flushPromises()
    expect(deleteMutateAsync).toHaveBeenCalledWith('art-1')
    expect(routerPush).toHaveBeenCalledWith('/kb')

    deleteMutateAsync.mockRejectedValueOnce(new Error('x'))
    await w.find('.h-delete').trigger('click')
    await flushPromises()
    expect(messageError).toHaveBeenCalled()

    await w.find('.open-diff').trigger('click')
    await nextTick()
    expect(w.find('.diff-modal').exists()).toBe(true)
  })
})
