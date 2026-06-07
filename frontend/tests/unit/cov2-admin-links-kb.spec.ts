import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'

const {
  useQueryMock,
  useInfiniteQueryMock,
  queryClientMock,
  messageMock,
  confirmMock,
  createLinkMock,
  updateLinkMock,
  deleteLinkMock,
  uploadLinkIconMock,
  deleteLinkIconMock,
  importMarkdownFileMock,
  importVaultZipMock,
  exportKbVaultMock,
  linksStoreMock,
} = vi.hoisted(() => ({
  useQueryMock: vi.fn(),
  useInfiniteQueryMock: vi.fn(),
  queryClientMock: {
    invalidateQueries: vi.fn().mockResolvedValue(undefined),
    removeQueries: vi.fn(),
    setQueryData: vi.fn(),
  },
  messageMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  confirmMock: vi.fn().mockResolvedValue(true),
  createLinkMock: vi.fn(),
  updateLinkMock: vi.fn(),
  deleteLinkMock: vi.fn(),
  uploadLinkIconMock: vi.fn(),
  deleteLinkIconMock: vi.fn(),
  importMarkdownFileMock: vi.fn(),
  importVaultZipMock: vi.fn(),
  exportKbVaultMock: vi.fn(),
  linksStoreMock: {
    addLink: vi.fn(),
    updateLinkItem: vi.fn(),
    removeLink: vi.fn(),
    clearLinkIcon: vi.fn(),
  },
}))

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title'], emits: ['click'] },
  NButtonGroup: { template: '<div><slot /></div>' },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NEmpty: { template: '<div class="n-empty"><slot /></div>', props: ['description'] },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title', 'showIcon', 'closable'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['bordered', 'size', 'title'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'maxlength', 'size', 'clearable'],
    emits: ['update:value'],
  },
  NSelect: {
    template: '<select :value="value" @change="$emit(\'update:value\', $event.target.value)"><option v-for="o in options || []" :key="o.value" :value="o.value">{{ o.label }}</option></select>',
    props: ['value', 'options', 'placeholder', 'multiple', 'clearable'],
    emits: ['update:value'],
  },
  NPagination: { template: '<div class="n-pagination" />', props: ['page', 'pageCount', 'pageSize'], emits: ['update:page'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value', 'label'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'], emits: ['update:show'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NCheckbox: { template: '<input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', !checked)" />', props: ['checked'], emits: ['update:checked'] },
  NSwitch: { template: '<input type="checkbox" :checked="value" @change="$emit(\'update:value\', !value)" />', props: ['value'], emits: ['update:value'] },
  NDataTable: { template: '<div class="n-data-table" />', props: ['data', 'columns', 'pagination', 'loading'] },
  NSpace: { template: '<div><slot /></div>', props: ['justify', 'align', 'size', 'vertical'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'closable', 'bordered'] },
  NTooltip: { template: '<div><slot /><slot name="trigger" /></div>' },
  NPopconfirm: { template: '<div><slot /><slot name="trigger" /></div>' },
  NDivider: { template: '<hr />' },
  NText: { template: '<span><slot /></span>', props: ['depth', 'type'] },
  NDynamicTags: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NUpload: { template: '<div><slot /></div>', props: ['multiple', 'showFileList', 'fileList', 'customRequest'], emits: ['change'] },
  NColorPicker: { template: '<input type="color" />', props: ['value'], emits: ['update:value'] },
  NInputNumber: { template: '<input type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />', props: ['value', 'min', 'max'], emits: ['update:value'] },
  NScrollbar: { template: '<div><slot /></div>' },
  NCollapse: { template: '<div><slot /></div>' },
  NCollapseItem: { template: '<div><slot /></div>', props: ['title', 'name'] },
  NCode: { template: '<pre><slot /></pre>', props: ['code', 'language'] },
  NDatePicker: { template: '<input type="date" />', props: ['value', 'type', 'placeholder'], emits: ['update:value'] },
  NSkeleton: { template: '<div class="n-skeleton" />', props: ['text', 'repeat'] },
  NTimePicker: { template: '<input type="time" />', props: ['value'], emits: ['update:value'] },
  NList: { template: '<ul><slot /></ul>' },
  NListItem: { template: '<li><slot /></li>' },
  NThing: { template: '<div><slot /></div>', props: ['title', 'description'] },
  NAvatar: { template: '<div class="n-avatar" />', props: ['src', 'size', 'round'] },
  NBadge: { template: '<div><slot /></div>', props: ['value', 'max'] },
  NDescriptions: { template: '<div><slot /></div>', props: ['column', 'bordered'] },
  NDescriptionsItem: { template: '<div><slot /></div>', props: ['label'] },
  NProgress: { template: '<div class="n-progress"><slot /></div>', props: ['type', 'percentage', 'status', 'processing', 'indicatorPlacement'] },
  useMessage: () => messageMock,
  useDialog: () => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }),
  useLoadingBar: () => ({ start: vi.fn(), finish: vi.fn(), error: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/admin', name: 'admin' })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: useQueryMock,
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => queryClientMock),
  useInfiniteQuery: useInfiniteQueryMock,
  keepPreviousData: undefined,
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ data: {} }),
  apiUpload: vi.fn().mockResolvedValue({ data: {} }),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: confirmMock }),
}))

vi.mock('../../src/stores/links', () => ({
  useLinksStore: () => linksStoreMock,
}))

vi.mock('../../src/api/links', () => ({
  createLink: createLinkMock,
  updateLink: updateLinkMock,
  deleteLink: deleteLinkMock,
  uploadLinkIcon: uploadLinkIconMock,
  deleteLinkIcon: deleteLinkIconMock,
}))

vi.mock('../../src/api/kb', () => ({
  importMarkdownFile: importMarkdownFileMock,
  importVaultZip: importVaultZipMock,
  exportKbVault: exportKbVaultMock,
}))

vi.mock('@vicons/ionicons5', () => ({
  SearchOutline: { template: '<span />' },
  AddOutline: { template: '<span />' },
  CreateOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  ShieldCheckmarkOutline: { template: '<span />' },
}))
vi.mock('@vicons/fluent', () => ({}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
  },
}

function qResult(data: unknown, options?: { isLoading?: boolean; isError?: boolean }) {
  return {
    data: ref(data),
    isLoading: ref(options?.isLoading ?? false),
    isFetching: ref(false),
    isError: ref(options?.isError ?? false),
    error: ref(null),
    refetch: vi.fn(),
  }
}

describe('cov2 admin tabs: links + kb', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useInfiniteQueryMock.mockReturnValue({ data: ref({ pages: [] }), isLoading: ref(false), fetchNextPage: vi.fn(), hasNextPage: ref(false) })
  })

  it('LinksTab mounts in loading state', async () => {
    useQueryMock.mockReturnValueOnce(qResult(undefined, { isLoading: true }))

    const Component = (await import('../../src/pages/admin/tabs/LinksTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
  })

  it('LinksTab opens add modal and submits create branch', async () => {
    useQueryMock.mockReturnValueOnce(qResult({
      items: [{ id: '1', title: 'Portal', url: 'https://portal.local', category: 'Work', supports_sso: true, is_active: true, sort_order: 1, description: null, icon_url: null }],
    }))

    createLinkMock.mockResolvedValue({ id: '2', title: 'New', url: 'https://new.local', category: null, supports_sso: false, is_active: true, sort_order: 0, description: null, icon_url: null })

    const Component = (await import('../../src/pages/admin/tabs/LinksTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    const buttons = wrapper.findAll('button')
    await buttons[0].trigger('click')
    await flushPromises()

    expect(wrapper.find('.n-modal').exists()).toBe(true)

    const modalButtons = wrapper.findAll('.modal-footer button')
    await modalButtons[1].trigger('click')
    await flushPromises()

    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('KbTab shows import result for default vault tab scenario', async () => {
    importVaultZipMock.mockResolvedValue({ created: 2, updated: 1, skipped: 0, errors: [] })

    const Component = (await import('../../src/pages/admin/tabs/KbTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    const tabPanes = wrapper.findAll('.n-tab-pane')
    expect(tabPanes.length).toBeGreaterThan(0)

    const zipInput = wrapper.find('input[accept=".zip"]')
    const zipFile = new File(['zip'], 'vault.zip', { type: 'application/zip' })
    Object.defineProperty(zipInput.element, 'files', { value: [zipFile], configurable: true })
    await zipInput.trigger('change')
    await flushPromises()

    const importButton = wrapper.findAll('button').at(-1)
    expect(importButton).toBeDefined()
    await importButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('2')
    expect(importVaultZipMock).toHaveBeenCalled()
  })

  it('KbTab handles vault import error branch and export action', async () => {
    importVaultZipMock.mockRejectedValue(new Error('boom'))

    const Component = (await import('../../src/pages/admin/tabs/KbTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    const zipInput = wrapper.find('input[accept=".zip"]')
    const zipFile = new File(['abc'], 'vault.zip', { type: 'application/zip' })
    Object.defineProperty(zipInput.element, 'files', { value: [zipFile], configurable: true })
    await zipInput.trigger('change')
    await flushPromises()

    const buttons = wrapper.findAll('button')
    await buttons[0].trigger('click')
    await flushPromises()
    expect(exportKbVaultMock).toHaveBeenCalled()

    const runBtn = buttons.at(-1)
    await runBtn!.trigger('click')
    await flushPromises()

    expect(messageMock.error).toHaveBeenCalled()
  })
})
